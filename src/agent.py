"""FastAPI agent core for GarudaAI.

High-performance local AI agent with streaming, session management, tools, and auth.
"""

import asyncio
import json
import os
import re
import secrets
import shlex
import sqlite3
import logging
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Optional, List
from urllib.request import urlopen
from urllib.error import URLError

import httpx

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, HTTPException, Depends, Request, UploadFile, File
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

from .tools.filesystem import FilesystemTool
from .tools.shell import ShellTool
from .tools.system_control import SystemControlTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
_CONFIG_FILE = Path("~/.config/garudaai/config.toml").expanduser()
_config: Dict[str, Any] = {}


_SOUL_FILE = Path("~/.config/garudaai/SOUL.md").expanduser()
_DATA_DIR = Path("~/.local/share/garudaai").expanduser()
_soul_cache: Dict[str, Any] = {"content": "", "loaded_at": 0.0}
_SOUL_CACHE_TTL = 60.0  # seconds


def _load_soul() -> str:
    """Load SOUL.md persona file with a 60-second cache."""
    now = time.monotonic()
    if now - _soul_cache["loaded_at"] < _SOUL_CACHE_TTL:
        return _soul_cache["content"]
    content = _SOUL_FILE.read_text(errors="ignore")[:2000] if _SOUL_FILE.exists() else ""
    _soul_cache["content"] = content
    _soul_cache["loaded_at"] = now
    return content


def _load_config() -> Dict[str, Any]:
    global _config
    if not _CONFIG_FILE.exists():
        return {}
    try:
        import tomli
        with open(_CONFIG_FILE, "rb") as f:
            _config = tomli.load(f)
    except Exception as e:
        logger.warning(f"Could not load config: {e}")
        _config = {}
    return _config


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
# In-memory token store: token -> expiry datetime
_tokens: Dict[str, datetime] = {}
_TOKEN_TTL = timedelta(hours=24)


def _issue_token() -> str:
    token = secrets.token_urlsafe(32)
    _tokens[token] = datetime.utcnow() + _TOKEN_TTL
    return token


def _validate_token(token: str) -> bool:
    expiry = _tokens.get(token)
    if not expiry:
        return False
    if datetime.utcnow() > expiry:
        del _tokens[token]
        return False
    return True


async def require_auth(request: Request):
    """FastAPI dependency: pass if no password configured, else check Bearer token."""
    password_hash = _config.get("auth", {}).get("password_hash", "")
    if not password_hash:
        return  # No password set — open access (dev mode)

    # Check Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if _validate_token(token):
            return
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Check cookie
    cookie_token = request.cookies.get("garudaai_token", "")
    if cookie_token and _validate_token(cookie_token):
        return

    # Check query param (used by WebSocket clients, since WS can't send headers)
    query_token = request.query_params.get("token", "")
    if query_token and _validate_token(query_token):
        return

    raise HTTPException(status_code=401, detail="Authentication required")


# ---------------------------------------------------------------------------
# Session Manager — persistent SQLite connection with WAL mode
# ---------------------------------------------------------------------------

class SessionManager:
    """Manage user sessions and history with a persistent DB connection."""

    def __init__(self, db_path: str = "~/.local/share/garudaai/sessions.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                model_name TEXT,
                created_at TEXT,
                last_accessed TEXT,
                summary TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );
            CREATE TABLE IF NOT EXISTS audit (
                audit_id TEXT PRIMARY KEY,
                session_id TEXT,
                tool_name TEXT,
                action TEXT,
                params TEXT,
                result TEXT,
                timestamp TEXT
            );
        """)
        self._conn.commit()

    def create_session(self, model_name: str) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO sessions (session_id, model_name, created_at, last_accessed) VALUES (?, ?, ?, ?)",
            (session_id, model_name, now, now),
        )
        self._conn.commit()
        return session_id

    def add_message(self, session_id: str, role: str, content: str):
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO messages (message_id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, role, content, now),
        )
        self._conn.execute(
            "UPDATE sessions SET last_accessed = ? WHERE session_id = ?",
            (now, session_id),
        )
        self._conn.commit()

    def get_history(self, session_id: str, limit: int = 50) -> List[Dict[str, str]]:
        cursor = self._conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit),
        )
        rows = cursor.fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        self._conn.row_factory = sqlite3.Row
        cursor = self._conn.execute(
            "SELECT session_id, model_name, created_at, last_accessed, summary "
            "FROM sessions ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        self._conn.row_factory = None
        return [dict(r) for r in rows]

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        self._conn.row_factory = sqlite3.Row
        cursor = self._conn.execute(
            "SELECT session_id, model_name, created_at, last_accessed, summary "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        self._conn.row_factory = None
        return dict(row) if row else None

    def update_session_summary(self, session_id: str, summary: str):
        self._conn.execute(
            "UPDATE sessions SET summary = ? WHERE session_id = ?",
            (summary, session_id),
        )
        self._conn.commit()

    def log_audit(self, session_id: str, tool_name: str, action: str, params: Dict, result: str):
        self._conn.execute(
            "INSERT INTO audit (audit_id, session_id, tool_name, action, params, result, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, tool_name, action, json.dumps(params), result[:500], datetime.now().isoformat()),
        )
        self._conn.commit()

    # Async wrappers (all DB ops run in a thread to avoid blocking the event loop)
    async def create_session_async(self, model_name: str) -> str:
        async with self._lock:
            return await asyncio.to_thread(self.create_session, model_name)

    async def add_message_async(self, session_id: str, role: str, content: str):
        async with self._lock:
            await asyncio.to_thread(self.add_message, session_id, role, content)

    async def get_history_async(self, session_id: str, limit: int = 50) -> List[Dict[str, str]]:
        async with self._lock:
            return await asyncio.to_thread(self.get_history, session_id, limit)

    async def list_sessions_async(self, limit: int = 20) -> List[Dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self.list_sessions, limit)

    async def get_session_info_async(self, session_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self.get_session_info, session_id)

    async def log_audit_async(self, session_id: str, tool_name: str, action: str, params: Dict, result: str):
        async with self._lock:
            await asyncio.to_thread(self.log_audit, session_id, tool_name, action, params, result)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Agent:
    """Local AI agent with tool integration and multi-step tool feedback loop."""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        session_manager: Optional[SessionManager] = None,
        home_dir: str = "~",
        full_access: bool = False,
    ):
        self.ollama_url = ollama_url
        self.session_manager = session_manager or SessionManager()
        self.filesystem = FilesystemTool(home_dir, full_access=full_access)
        self.shell = ShellTool(full_access=full_access)
        self.system_control = SystemControlTool()
        self.home_dir = home_dir
        self._rag: Optional[Any] = None

    def _get_rag(self) -> Any:
        """Lazy-load RAGTool (requires chromadb optional dep)."""
        if self._rag is None:
            try:
                from .tools.rag_tool import RAGTool
                self._rag = RAGTool()
            except ImportError:
                raise RuntimeError("RAG not available. Install with: pip install garudaai[rag]")
        return self._rag

    def build_system_prompt(self, model_name: str, use_case: str = "general") -> str:
        base = (
            "You are GarudaAI, a helpful local AI assistant running on the host machine.\n"
            "You have access to system tools. When you need to use a tool, output a line in this format:\n"
            "[tool: filesystem_read, /path/to/file]\n"
            "[tool: shell, ls, -la, /home]\n"
            "[tool: system_control, screenshot]\n"
            "[tool: system_control, volume_set, 50]\n"
            "[tool: system_control, system_info]\n"
            "[tool: system_control, notify, GarudaAI, Hello from your phone!]\n"
            "[tool: system_control, processes]\n"
            "[tool: system_control, lock_screen]\n"
            "[tool: system_control, open_url, https://example.com]\n"
            "[tool: rag, what does the document say about X?]\n"
            "For quoted arguments with spaces: [tool: filesystem_read, \"/path/with spaces/file.txt\"]\n"
            "The system_control tool lets you control the host machine remotely (screenshot, volume, power, etc).\n"
            "The rag tool searches your ingested documents. Use it when asked about uploaded files or documents.\n"
            "Never invent tool output. The system will provide real results and call you again."
        )
        extras = {
            "coding": "\n\nYou are an expert programmer. Help with code, debugging, and technical problems.",
            "research": "\n\nYou are a research assistant. Help find, analyze, and summarize information.",
            "writing": "\n\nYou are a writing assistant. Help with drafting, editing, and improving text.",
        }
        prompt = base + extras.get(use_case, "")
        # Prepend SOUL.md persona if it exists
        soul = _load_soul()
        if soul:
            prompt = soul + "\n\n---\n\n" + prompt
        return prompt

    def parse_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Parse [tool: name, arg1, arg2] calls from text using shlex for robust arg splitting."""
        tool_calls = []
        pattern = r'\[tool:\s*([\w_-]+)(?:,\s*(.+?))?\]'
        for match in re.finditer(pattern, text, re.DOTALL):
            tool_name = match.group(1)
            args_str = (match.group(2) or "").strip()
            try:
                # shlex handles quoted args; strip trailing commas from comma-separated syntax
                args = [a.rstrip(',') for a in shlex.split(args_str)] if args_str else []
            except ValueError:
                args = [a.strip() for a in args_str.split(",")]
            tool_calls.append({
                "tool": tool_name,
                "args": args,
                "span": match.span(),
            })
        return tool_calls

    def _strip_tool_calls(self, text: str, tool_calls: List[Dict]) -> str:
        """Remove [tool: ...] markers from text so they don't appear in the UI."""
        result = text
        for call in reversed(tool_calls):
            start, end = call["span"]
            result = result[:start] + result[end:]
        return result.strip()

    def _is_tool_request(self, user_message: str) -> bool:
        msg = user_message.strip().lower()
        if not msg:
            return False
        if msg.startswith("[tool:"):
            return True
        command_prefixes = tuple(self.shell.allowed_commands)
        if msg.startswith(command_prefixes):
            return True
        for trigger in ("run ", "execute ", "show ", "list "):
            if msg.startswith(trigger):
                for cmd in command_prefixes:
                    if f" {cmd}" in msg:
                        return True
        return False

    async def execute_tool(self, tool_name: str, args: List[str]) -> str:
        """Execute a tool and return its output as a string."""
        try:
            if tool_name == "filesystem_read":
                if not args:
                    return "Error: filesystem_read requires a path"
                content = self.filesystem.read_file(args[0])
                return f"File contents:\n{content}"

            elif tool_name == "shell":
                if not args:
                    return "Error: shell requires a command"
                result = await asyncio.to_thread(self.shell.execute, args[0], *args[1:])
                if not result.get("success"):
                    return f"Error: {result.get('stderr') or 'Command failed'}"
                output = result.get("stdout", "")
                if result.get("stderr"):
                    output = f"{output}\n{result['stderr']}".strip()
                return f"Command output:\n{output}"

            elif tool_name == "system_control":
                if not args:
                    return "Error: system_control requires an action (e.g. screenshot, volume_get, system_info)"
                action = args[0]
                # Build kwargs from remaining args based on action
                kwargs: Dict[str, Any] = {}
                if action == "volume_set" and len(args) > 1:
                    kwargs["level"] = int(args[1])
                elif action == "kill_process":
                    if len(args) > 1:
                        try:
                            kwargs["pid"] = int(args[1])
                        except ValueError:
                            kwargs["name"] = args[1]
                elif action == "notify":
                    kwargs["title"] = args[1] if len(args) > 1 else "GarudaAI"
                    kwargs["message"] = args[2] if len(args) > 2 else ""
                elif action == "open_file" and len(args) > 1:
                    kwargs["path"] = args[1]
                elif action == "open_url" and len(args) > 1:
                    kwargs["url"] = args[1]
                elif action == "processes" and len(args) > 1:
                    kwargs["sort_by"] = args[1]
                elif action in ("shutdown", "restart") and len(args) > 1:
                    try:
                        kwargs["delay_seconds"] = int(args[1])
                    except ValueError:
                        pass
                result = await asyncio.to_thread(self.system_control.execute, action, **kwargs)
                if not result.get("success"):
                    return f"system_control error: {result.get('error', 'Unknown error')}"
                # Format a readable response
                result_copy = {k: v for k, v in result.items() if k != "success"}
                return f"system_control result:\n{json.dumps(result_copy, indent=2)}"

            elif tool_name == "rag":
                if not args:
                    return "Error: rag tool requires a question"
                question = " ".join(args)
                rag = self._get_rag()
                return await asyncio.to_thread(rag.query, question)

            else:
                return f"Error: Unknown tool '{tool_name}'"

        except Exception as e:
            return f"Error executing {tool_name}: {e}"

    async def stream_chat(
        self,
        model_name: str,
        user_message: str,
        session_id: Optional[str] = None,
        use_case: str = "general",
        image_b64: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response. Supports multi-step tool feedback loop (max 3 iterations)."""
        if not session_id:
            session_id = await self.session_manager.create_session_async(model_name)

        await self.session_manager.add_message_async(session_id, "user", user_message)

        history = await self.session_manager.get_history_async(session_id, limit=20)
        system_prompt = self.build_system_prompt(model_name, use_case)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        # Attach image to the last user message if provided
        if image_b64 and messages:
            messages[-1] = dict(messages[-1])
            messages[-1]["images"] = [image_b64]

        # Check if this is an AirLLM model
        try:
            from .models import ModelSuggester
            model_info = ModelSuggester().get_model_by_name(model_name)
            use_airllm = model_info is not None and model_info.airllm
        except Exception:
            use_airllm = False

        if use_airllm:
            yield "⏳ **Slow Mode active** — using layer offloading. Expect 1-3 min response time.\n\n"
            try:
                from .airllm_backend import AirLLMBackend
                prompt_text = "\n".join(
                    f"{m['role'].upper()}: {m['content']}" for m in messages
                )
                backend = AirLLMBackend(model_info.hf_id)
                async for chunk in backend.stream_generate(prompt_text):
                    await self.session_manager.add_message_async(session_id, "assistant", chunk)
                    yield chunk
            except Exception as e:
                yield f"\n\nAirLLM error: {e}"
            return

        try:
            max_depth = 3
            for depth in range(max_depth):
                full_response = ""
                async for token in self._call_ollama_streaming(model_name, messages):
                    full_response += token

                tool_calls = self.parse_tool_calls(full_response)

                if not tool_calls or depth == max_depth - 1:
                    # No tools (or hit iteration limit) — stream visible response
                    visible = self._strip_tool_calls(full_response, tool_calls) if tool_calls else full_response
                    # Yield in smallish chunks for smooth streaming
                    chunk_size = 4
                    for i in range(0, len(visible), chunk_size):
                        yield visible[i:i + chunk_size]
                    await self.session_manager.add_message_async(session_id, "assistant", full_response)
                    break

                # Execute tools and feed results back to model
                messages.append({"role": "assistant", "content": full_response})
                tool_results_parts = []
                for call in tool_calls:
                    result = await self.execute_tool(call["tool"], call["args"])
                    tool_results_parts.append(f"[{call['tool']} result]:\n{result}")
                    await self.session_manager.log_audit_async(
                        session_id, call["tool"], f"execute {call['tool']}",
                        {"args": call["args"]}, result,
                    )

                tool_results_msg = "\n\n".join(tool_results_parts)
                messages.append({"role": "user", "content": f"Tool results:\n{tool_results_msg}"})

                # Emit a brief status to the UI so the user sees something
                yield f"\n_🔧 Executed {len(tool_calls)} tool(s), reasoning..._\n\n"

        except Exception as e:
            yield f"\n\nError: {e}"

    async def _call_ollama_streaming(
        self,
        model_name: str,
        messages: List[Dict],
    ) -> AsyncGenerator[str, None]:
        payload = {"model": model_name, "messages": messages, "stream": True}
        endpoint = f"{self.ollama_url}/api/chat"
        timeout = httpx.Timeout(connect=5.0, read=300.0, write=5.0, pool=5.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", endpoint, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
        except httpx.HTTPError as e:
            logger.error(f"Ollama call failed: {e}")
            yield f"Error contacting Ollama: {e}"

    def list_models(self) -> List[Dict]:
        try:
            response = urlopen(f"{self.ollama_url}/api/tags", timeout=5)
            data = json.loads(response.read().decode())
            return data.get("models", [])
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
agent: Optional[Agent] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, _config
    _config = _load_config()
    ollama_url = _config.get("models", {}).get("ollama_url", "http://localhost:11434")
    home_dir = _config.get("paths", {}).get("home_dir", "~")
    full_access = _config.get("tools", {}).get("full_access", False)
    agent = Agent(ollama_url=ollama_url, home_dir=home_dir, full_access=full_access)
    yield


app = FastAPI(title="GarudaAI", version="0.1.0", lifespan=lifespan)

# Rate limiting (graceful degradation if slowapi not installed)
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    _limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = _limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    _RATE_LIMIT_AVAILABLE = True
except ImportError:
    _RATE_LIMIT_AVAILABLE = False
    _limiter = None


# ---------------------------------------------------------------------------
# Auth endpoints (no auth required on these)
# ---------------------------------------------------------------------------

@app.post("/api/auth/login")
async def login(request: Request):
    """Verify password and issue a session token."""
    password_hash = _config.get("auth", {}).get("password_hash", "")
    if not password_hash:
        # No password configured — return a no-op token
        return {"token": _issue_token()}

    try:
        body = await request.json()
        password = body.get("password", "")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        import bcrypt as _bcrypt
        valid = _bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        valid = False

    if not valid:
        raise HTTPException(status_code=401, detail="Incorrect password")

    return {"token": _issue_token()}


@app.post("/api/auth/update-password", dependencies=[Depends(require_auth)])
async def update_password(request: Request):
    """Change the password (requires current valid token)."""
    try:
        body = await request.json()
        new_password = body.get("new_password", "")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    try:
        import bcrypt as _bcrypt
        new_hash = _bcrypt.hashpw(new_password.encode(), _bcrypt.gensalt()).decode()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to hash password: {e}")

    # Update config file
    try:
        import tomli_w
        if _CONFIG_FILE.exists():
            import tomli
            with open(_CONFIG_FILE, "rb") as f:
                conf = tomli.load(f)
        else:
            conf = {}
        conf.setdefault("auth", {})["password_hash"] = new_hash
        _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "wb") as f:
            tomli_w.dump(conf, f)
        # Reload config into memory
        _config.setdefault("auth", {})["password_hash"] = new_hash
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {e}")

    return {"success": True, "message": "Password updated. All existing tokens remain valid until expiry."}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Protected API routes
# ---------------------------------------------------------------------------

@app.get("/api/models", dependencies=[Depends(require_auth)])
async def list_models(request: Request):
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    models = await asyncio.to_thread(agent.list_models)
    return {"models": models}


@app.get("/api/sessions", dependencies=[Depends(require_auth)])
async def list_sessions():
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    sessions = await agent.session_manager.list_sessions_async()
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}", dependencies=[Depends(require_auth)])
async def get_session(session_id: str):
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    session_info = await agent.session_manager.get_session_info_async(session_id)
    if not session_info:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await agent.session_manager.get_history_async(session_id, limit=100)
    return {"session": session_info, "messages": messages}


@app.post("/api/sessions", dependencies=[Depends(require_auth)])
async def create_session(request: Request):
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    try:
        body = await request.json()
        model_name = body.get("model_name", "llama3.2:3b")
    except Exception:
        model_name = "llama3.2:3b"
    session_id = await agent.session_manager.create_session_async(model_name)
    return {"session_id": session_id}


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, token: Optional[str] = None):
    """WebSocket endpoint for streaming chat (auth via ?token= query param)."""
    # Auth check before accepting
    password_hash = _config.get("auth", {}).get("password_hash", "")
    if password_hash:
        if not token or not _validate_token(token):
            await websocket.close(code=4401, reason="Unauthorized")
            return

    if not agent:
        await websocket.close(code=1011, reason="Agent not initialized")
        return

    await websocket.accept()

    try:
        data = await websocket.receive_json()
        model_name = data.get("model", "llama3.2:3b")
        user_message = data.get("message", "")
        session_id = data.get("session_id")
        use_case = data.get("use_case", "general")
        image_b64 = data.get("image")  # optional base64 image for vision models

        buffer = []
        last_flush = time.monotonic()
        flush_interval = 0.05
        stream_start = time.monotonic()
        char_count = 0

        async for token_text in agent.stream_chat(model_name, user_message, session_id, use_case, image_b64):
            buffer.append(token_text)
            char_count += len(token_text)
            now = time.monotonic()
            if now - last_flush >= flush_interval:
                await websocket.send_text("".join(buffer))
                buffer.clear()
                last_flush = now

        if buffer:
            await websocket.send_text("".join(buffer))

        elapsed = time.monotonic() - stream_start
        approx_tokens = max(1, char_count // 4)
        tps = round(approx_tokens / elapsed, 1) if elapsed > 0.1 else 0
        await websocket.send_json({"type": "done", "stats": {"tokens": approx_tokens, "tps": tps}})

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# SOUL.md persona endpoints
# ---------------------------------------------------------------------------

@app.get("/api/soul", dependencies=[Depends(require_auth)])
async def get_soul():
    """Return current SOUL.md content."""
    content = _SOUL_FILE.read_text(errors="ignore") if _SOUL_FILE.exists() else ""
    return {"content": content}


@app.post("/api/soul", dependencies=[Depends(require_auth)])
async def save_soul(request: Request):
    """Save SOUL.md content and invalidate cache."""
    try:
        body = await request.json()
        content = body.get("content", "")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    _SOUL_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SOUL_FILE.write_text(content, encoding="utf-8")
    # Invalidate cache
    _soul_cache["loaded_at"] = 0.0
    return {"ok": True}


# ---------------------------------------------------------------------------
# RAG endpoints
# ---------------------------------------------------------------------------

@app.post("/api/rag/upload", dependencies=[Depends(require_auth)])
async def rag_upload(file: UploadFile = File(...)):
    """Ingest a document into the RAG vector store."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    upload_dir = _DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / (file.filename or "upload.bin")
    dest.write_bytes(await file.read())
    try:
        rag = agent._get_rag()
        result = await asyncio.to_thread(rag.ingest, dest)
        return {"message": result}
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@app.get("/api/rag/documents", dependencies=[Depends(require_auth)])
async def rag_list_documents():
    """List documents in the RAG store."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    try:
        rag = agent._get_rag()
        sources = await asyncio.to_thread(rag.list_sources)
        return {"sources": sources}
    except RuntimeError:
        return {"sources": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Voice I/O endpoints
# ---------------------------------------------------------------------------

# Lazy-loaded Whisper model (faster-whisper)
_whisper_model: Optional[Any] = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        except ImportError:
            raise RuntimeError("faster-whisper not installed. Run: pip install garudaai[voice]")
    return _whisper_model


@app.post("/api/transcribe", dependencies=[Depends(require_auth)])
async def transcribe_audio(audio: UploadFile = File(...)):
    """Transcribe uploaded audio to text using faster-whisper (local, no cloud)."""
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(await audio.read())
        tmp_path = f.name
    try:
        def _run_whisper():
            model = _get_whisper()
            segments, _ = model.transcribe(tmp_path, beam_size=1)
            return " ".join(s.text for s in segments).strip()
        text = await asyncio.to_thread(_run_whisper)
        return {"text": text}
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.post("/api/speak", dependencies=[Depends(require_auth)])
async def speak_text(request: Request):
    """Convert text to speech using Piper TTS (local, no cloud). Returns WAV audio."""
    try:
        body = await request.json()
        text = str(body.get("text", ""))[:500]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    # Find piper binary
    piper_dir = _DATA_DIR / "piper"
    import sys
    piper_bin = (piper_dir / ("piper.exe" if sys.platform == "win32" else "piper"))
    if not piper_bin.exists():
        # Try system PATH
        import shutil
        found = shutil.which("piper")
        if not found:
            raise HTTPException(status_code=501, detail="Piper TTS not installed. Run: garudaai setup")
        piper_bin = Path(found)

    tts_model = _config.get("voice", {}).get("tts_model", "en_US-lessac-medium")
    tts_model_path = piper_dir / f"{tts_model}.onnx"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name

    try:
        import subprocess
        cmd = [str(piper_bin), "--output_file", wav_path]
        if tts_model_path.exists():
            cmd += ["--model", str(tts_model_path)]
        proc = await asyncio.to_thread(
            subprocess.run, cmd,
            input=text.encode("utf-8"),
            capture_output=True, timeout=30, shell=False,
        )
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail="Piper TTS failed: " + proc.stderr.decode(errors="replace")[:200])
        wav_bytes = Path(wav_path).read_bytes()
        return Response(content=wav_bytes, media_type="audio/wav")
    except FileNotFoundError:
        raise HTTPException(status_code=501, detail="Piper TTS binary not found")
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


# Mount static files AFTER all API routes
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


def run_agent(
    host: str = "0.0.0.0",
    port: int = 8000,
    ssl_keyfile: Optional[str] = None,
    ssl_certfile: Optional[str] = None,
):
    """Run the FastAPI agent server."""
    import logging as _logging
    log_dir = Path("~/.local/share/garudaai").expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "garudaai.log"

    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Suppress noisy Windows asyncio socket-close errors (WinError 10054)
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    uvicorn.run(
        "src.agent:app",
        host=host,
        port=port,
        reload=False,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
        log_level="info",
    )
