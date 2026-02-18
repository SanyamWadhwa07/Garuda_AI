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

    async def stream_chat(
        self,
        model_name: str,
        user_message: str,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response from Ollama.
        
        Args:
            model_name: Model name to use
            user_message: User's message
            session_id: Optional session ID for history
            
        Yields:
            Text tokens as they arrive
        """
        # Create session if needed
        if not session_id:
            session_id = self.session_manager.create_session(model_name)

        # Add user message to history
        self.session_manager.add_message(session_id, "user", user_message)

        # Get context (last 5 messages)
        history = self.session_manager.get_history(session_id, limit=5)

        # Build system prompt
        system_prompt = "You are a helpful AI assistant with access to local tools like filesystem access and command execution. Be concise and helpful."

        # Build messages for Ollama
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # Call Ollama with streaming
        try:
            async_response = await self._call_ollama_streaming(model_name, messages)
            full_response = ""

            async for token in async_response:
                yield token
                full_response += token

            # Add assistant response to history
            self.session_manager.add_message(session_id, "assistant", full_response)

        except Exception as e:
            yield f"\n\nError: {str(e)}"

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

        # Stream response
        async for token in agent.stream_chat(model_name, user_message, session_id):
            await websocket.send_text(token)

        await websocket.send_json({"type": "done"})

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()


@app.get("/")
async def root():
    """Serve index.html for PWA."""
    static_dir = Path(__file__).parent / "static"
    index_file = static_dir / "index.html"

    if index_file.exists():
        return FileResponse(index_file, media_type="text/html")
    else:
        return {"message": "GarudaAI"}


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
