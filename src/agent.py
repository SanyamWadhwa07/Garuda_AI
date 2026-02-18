"""FastAPI agent core for GarudaAI.

High-performance local AI agent with streaming, session management, and tools.
"""

import asyncio
import json
import sqlite3
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Optional, List
from urllib.request import urlopen
from urllib.error import URLError

from fastapi import FastAPI, WebSocket, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from .tools.filesystem import FilesystemTool
from .tools.shell import ShellTool


logger = logging.getLogger(__name__)


class SessionManager:
    """Manage user sessions and history."""

    def __init__(self, db_path: str = "~/.local/share/garudaai/sessions.db"):
        """Initialize session manager.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                model_name TEXT,
                created_at TEXT,
                last_accessed TEXT,
                summary TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit (
                audit_id TEXT PRIMARY KEY,
                session_id TEXT,
                tool_name TEXT,
                action TEXT,
                params TEXT,
                result TEXT,
                timestamp TEXT
            )
        """)

        conn.commit()
        conn.close()

    def create_session(self, model_name: str) -> str:
        """Create a new session.
        
        Args:
            model_name: Model to use in this session
            
        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (session_id, model_name, created_at, last_accessed) VALUES (?, ?, ?, ?)",
            (session_id, model_name, now, now),
        )
        conn.commit()
        conn.close()

        return session_id

    def add_message(self, session_id: str, role: str, content: str):
        """Add a message to a session.
        
        Args:
            session_id: Session ID
            role: "user" or "assistant"
            content: Message content
        """
        message_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (message_id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            (message_id, session_id, role, content, now),
        )
        cursor.execute(
            "UPDATE sessions SET last_accessed = ? WHERE session_id = ?",
            (now, session_id),
        )
        conn.commit()
        conn.close()

    def get_history(self, session_id: str, limit: int = 50) -> List[Dict[str, str]]:
        """Get message history for a session.
        
        Args:
            session_id: Session ID
            limit: Number of recent messages
            
        Returns:
            List of {role, content} dicts
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List all sessions."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT session_id, model_name, created_at, last_accessed, summary FROM sessions ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT session_id, model_name, created_at, last_accessed, summary FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_session_summary(self, session_id: str, summary: str):
        """Update session summary."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET summary = ? WHERE session_id = ?",
            (summary, session_id),
        )
        conn.commit()
        conn.close()

    def log_audit(self, session_id: str, tool_name: str, action: str, params: Dict, result: str):
        """Log an audit entry.
        
        Args:
            session_id: Session ID
            tool_name: Name of tool used
            action: Action description
            params: Tool parameters
            result: Result summary
        """
        audit_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit (audit_id, session_id, tool_name, action, params, result, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (audit_id, session_id, tool_name, action, json.dumps(params), result, now),
        )
        conn.commit()
        conn.close()


class Agent:
    """Local AI agent with tool integration."""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        session_manager: Optional[SessionManager] = None,
        home_dir: str = "~",
    ):
        """Initialize agent.
        
        Args:
            ollama_url: URL to Ollama API
            session_manager: Optional SessionManager instance
            home_dir: Home directory for filesystem access
        """
        self.ollama_url = ollama_url
        self.session_manager = session_manager or SessionManager()
        self.filesystem = FilesystemTool(home_dir)
        self.shell = ShellTool()
        self.home_dir = home_dir

    def build_system_prompt(self, model_name: str, use_case: str = "general") -> str:
        """Build contextual system prompt based on use case."""
        base = """You are GarudaAI, a helpful, knowledgeable local AI assistant running on Garuda Linux.
You have access to system tools and can read/write files or execute safe commands.

When you need to use a tool, format it on a separate line as:
[tool: filesystem_read, /path/to/file]
[tool: shell, ls, -la, /home]

Always explain what you're doing before calling tools. Be concise and helpful."""

        use_cases = {
            "coding": base + "\n\nYou are an expert programmer. Help with code, debugging, and technical problems. Provide code examples and clear explanations.",
            "research": base + "\n\nYou are a research assistant. Help find, analyze, and summarize information. Use tools to read documents and files.",
            "writing": base + "\n\nYou are a writing assistant. Help with drafting, editing, and improving text.",
            "general": base,
        }
        return use_cases.get(use_case, base)

    def parse_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Parse tool calls from response text. Format: [tool: name, arg1, arg2]"""
        import re
        tool_calls = []
        pattern = r'\[tool:\s*(\w+)(?:,\s*(.+?))?\]'
        matches = re.finditer(pattern, text)
        
        for match in matches:
            tool_name = match.group(1)
            args_str = match.group(2)
            args = [arg.strip() for arg in args_str.split(',')] if args_str else []
            tool_calls.append({"tool": tool_name, "args": args})
        
        return tool_calls

    async def execute_tool(self, tool_name: str, args: List[str]) -> str:
        """Execute a tool and return result."""
        try:
            if tool_name == "filesystem_read":
                if not args:
                    return "Error: filesystem_read requires a path"
                result = self.filesystem.read_file(args[0])
                if not result.get("success"):
                    return f"Error: {result.get('error', 'Failed to read file')}"
                return f"File contents ({result.get('bytes_read', 0)} bytes):\n{result['content']}"
            
            elif tool_name == "shell":
                if not args:
                    return "Error: shell requires a command"
                cmd = args[0]
                cmd_args = args[1:] if len(args) > 1 else []
                result = self.shell.execute(cmd, *cmd_args)
                if not result.get("success"):
                    return f"Error: {result.get('error', 'Command failed')}"
                return f"Command output:\n{result['output']}"
            
            else:
                return f"Error: Unknown tool '{tool_name}'"
        
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    async def stream_chat(
        self,
        model_name: str,
        user_message: str,
        session_id: Optional[str] = None,
        use_case: str = "general",
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response from Ollama.
        
        Args:
            model_name: Model name to use
            user_message: User's message
            session_id: Optional session ID for history
            use_case: Use case for context-aware prompts
            
        Yields:
            Text tokens as they arrive
        """
        # Create session if needed
        if not session_id:
            session_id = self.session_manager.create_session(model_name)

        # Add user message to history
        self.session_manager.add_message(session_id, "user", user_message)

        # Get context (last 10 messages for more context)
        history = self.session_manager.get_history(session_id, limit=10)

        # Build contextual system prompt
        system_prompt = self.build_system_prompt(model_name, use_case)

        # Build messages for Ollama
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # Call Ollama with streaming
        try:
            full_response = ""

            async for token in self._call_ollama_streaming(model_name, messages):
                yield token
                full_response += token

            # Parse and execute tools if present
            tool_calls = self.parse_tool_calls(full_response)
            if tool_calls:
                yield "\n\n_Executing tools..._\n"
                for call in tool_calls:
                    result = await self.execute_tool(call["tool"], call["args"])
                    yield f"\n**{call['tool']}**: {result}\n"
                    
                    # Log audit
                    self.session_manager.log_audit(
                        session_id,
                        call["tool"],
                        f"execute {call['tool']}",
                        {"args": call["args"]},
                        result[:100]
                    )

            # Add assistant response to history
            self.session_manager.add_message(session_id, "assistant", full_response)

        except Exception as e:
            error_msg = f"\n\nError: {str(e)}"
            yield error_msg

    async def _call_ollama_streaming(
        self,
        model_name: str,
        messages: List[Dict],
    ) -> AsyncGenerator[str, None]:
        """Call Ollama API with streaming.
        
        Args:
            model_name: Model name
            messages: Message history
            
        Yields:
            Tokens from the model
        """
        import threading

        def fetch_stream():
            """Fetch response in thread."""
            try:
                payload = json.dumps({
                    "model": model_name,
                    "messages": messages,
                    "stream": True,
                }).encode()

                endpoint = f"{self.ollama_url}/api/chat"
                import urllib.request
                req = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )

                with urlopen(req, timeout=300) as response:
                    for line in response:
                        data = json.loads(line.decode())
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]

            except Exception as e:
                logger.error(f"Ollama call failed: {e}")
                yield f"Error contacting Ollama: {str(e)}"

        # Run fetch in background and yield results
        gen = fetch_stream()
        for chunk in gen:
            yield chunk

    def list_models(self) -> List[Dict]:
        """List available models from Ollama."""
        try:
            response = urlopen(f"{self.ollama_url}/api/tags", timeout=5)
            data = json.loads(response.read().decode())
            return data.get("models", [])
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []


# FastAPI Application
app = FastAPI(title="GarudaAI", version="0.1.0")

# Session management
agent = None


@app.on_event("startup")
async def startup():
    """Initialize agent on startup."""
    global agent
    agent = Agent()


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/models")
async def list_models():
    """List available models."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return {"models": agent.list_models()}


@app.get("/api/sessions")
async def list_sessions():
    """List all sessions."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    sessions = agent.session_manager.list_sessions()
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session info and messages."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    session_info = agent.session_manager.get_session_info(session_id)
    if not session_info:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = agent.session_manager.get_history(session_id, limit=100)
    return {"session": session_info, "messages": messages}


@app.post("/api/sessions")
async def create_session(model_name: str = "neural-chat"):
    """Create a new session."""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    session_id = agent.session_manager.create_session(model_name)
    return {"session_id": session_id}


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for streaming chat."""
    if not agent:
        await websocket.close(code=1011, reason="Agent not initialized")
        return

    await websocket.accept()

    try:
        data = await websocket.receive_json()
        model_name = data.get("model", "neural-chat")
        user_message = data.get("message", "")
        session_id = data.get("session_id")
        use_case = data.get("use_case", "general")

        # Stream response
        async for token in agent.stream_chat(model_name, user_message, session_id, use_case):
            await websocket.send_text(token)

        await websocket.send_json({"type": "done"})

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()


# Mount static files AFTER all API routes are defined
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


def run_agent(
    host: str = "0.0.0.0",
    port: int = 8000,
    ssl_keyfile: Optional[str] = None,
    ssl_certfile: Optional[str] = None,
):
    """Run the FastAPI agent server.
    
    Args:
        host: Host to bind to
        port: Port to bind to
        ssl_keyfile: Path to SSL key file
        ssl_certfile: Path to SSL certificate file
    """
    uvicorn.run(
        "src.agent:app",
        host=host,
        port=port,
        reload=False,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
        log_level="info",
    )
