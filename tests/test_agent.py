"""Tests for agent core: parse_tool_calls, is_tool_request, SessionManager, execute_tool."""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from src.agent import Agent, SessionManager


# ---------------------------------------------------------------------------
# parse_tool_calls
# ---------------------------------------------------------------------------

def test_parse_tool_calls_basic():
    agent = Agent.__new__(Agent)
    calls = agent.parse_tool_calls("[tool: shell, ls, -la, /home]")
    assert len(calls) == 1
    assert calls[0]["tool"] == "shell"
    assert calls[0]["args"] == ["ls", "-la", "/home"]


def test_parse_tool_calls_no_args():
    agent = Agent.__new__(Agent)
    calls = agent.parse_tool_calls("[tool: system_info]")
    assert len(calls) == 1
    assert calls[0]["tool"] == "system_info"
    assert calls[0]["args"] == []


def test_parse_tool_calls_quoted_path():
    agent = Agent.__new__(Agent)
    calls = agent.parse_tool_calls('[tool: filesystem_read, "/home/user/my docs/file.txt"]')
    assert len(calls) == 1
    assert calls[0]["args"] == ["/home/user/my docs/file.txt"]


def test_parse_tool_calls_multiple():
    agent = Agent.__new__(Agent)
    text = "Sure!\n[tool: shell, ls]\nAnd also:\n[tool: filesystem_read, /etc/hosts]"
    calls = agent.parse_tool_calls(text)
    assert len(calls) == 2
    assert calls[0]["tool"] == "shell"
    assert calls[1]["tool"] == "filesystem_read"


def test_parse_tool_calls_span_strips_marker():
    agent = Agent.__new__(Agent)
    text = "Hello [tool: shell, echo, hi] world"
    calls = agent.parse_tool_calls(text)
    stripped = agent._strip_tool_calls(text, calls)
    assert "[tool:" not in stripped
    assert "Hello" in stripped
    assert "world" in stripped


def test_parse_tool_calls_no_match():
    agent = Agent.__new__(Agent)
    calls = agent.parse_tool_calls("Just a plain message, no tools here.")
    assert calls == []


# ---------------------------------------------------------------------------
# _is_tool_request
# ---------------------------------------------------------------------------

def _make_agent():
    """Minimal Agent with mocked sub-tools for _is_tool_request tests."""
    agent = Agent.__new__(Agent)
    shell_mock = MagicMock()
    shell_mock.allowed_commands = ["ls", "cat", "echo", "pwd"]
    agent.shell = shell_mock
    return agent


def test_is_tool_request_explicit_tool():
    agent = _make_agent()
    assert agent._is_tool_request("[tool: shell, ls]") is True


def test_is_tool_request_plain_message():
    agent = _make_agent()
    assert agent._is_tool_request("What is the weather today?") is False


def test_is_tool_request_empty():
    agent = _make_agent()
    assert agent._is_tool_request("") is False


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------

@pytest.fixture
def session_mgr(tmp_path):
    db = tmp_path / "test_sessions.db"
    mgr = SessionManager(db_path=str(db))
    return mgr


def test_session_manager_create_get(session_mgr):
    sid = session_mgr.create_session("llama3.2:3b")
    assert sid
    info = session_mgr.get_session_info(sid)
    assert info is not None
    assert info["model_name"] == "llama3.2:3b"
    assert info["session_id"] == sid


def test_session_manager_messages(session_mgr):
    sid = session_mgr.create_session("mistral:7b")
    session_mgr.add_message(sid, "user", "Hello")
    session_mgr.add_message(sid, "assistant", "Hi there!")
    history = session_mgr.get_history(sid)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_session_manager_list(session_mgr):
    session_mgr.create_session("gemma2:2b")
    session_mgr.create_session("phi3.5:3.8b")
    sessions = session_mgr.list_sessions()
    assert len(sessions) == 2


def test_session_manager_summary(session_mgr):
    sid = session_mgr.create_session("qwen2.5:7b")
    session_mgr.update_session_summary(sid, "Discussed Python async patterns")
    info = session_mgr.get_session_info(sid)
    assert info["summary"] == "Discussed Python async patterns"


# ---------------------------------------------------------------------------
# execute_tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_tool_filesystem(tmp_path):
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello world")

    agent = Agent.__new__(Agent)
    from src.tools.filesystem import FilesystemTool
    agent.filesystem = FilesystemTool(str(tmp_path))

    shell_mock = MagicMock()
    agent.shell = shell_mock

    sys_ctrl_mock = MagicMock()
    agent.system_control = sys_ctrl_mock

    result = await agent.execute_tool("filesystem_read", [str(test_file)])
    assert "hello world" in result


@pytest.mark.asyncio
async def test_execute_tool_unknown_returns_error():
    agent = Agent.__new__(Agent)
    result = await agent.execute_tool("nonexistent_tool", [])
    assert "Unknown tool" in result


@pytest.mark.asyncio
async def test_execute_tool_system_control_info():
    agent = Agent.__new__(Agent)
    sys_ctrl_mock = MagicMock()
    sys_ctrl_mock.execute.return_value = {"success": True, "cpu_percent": 10.0, "ram_total_gb": 16.0}
    agent.system_control = sys_ctrl_mock

    result = await agent.execute_tool("system_control", ["system_info"])
    assert "system_control result" in result
    sys_ctrl_mock.execute.assert_called_once_with("system_info")


@pytest.mark.asyncio
async def test_execute_tool_system_control_volume_set():
    agent = Agent.__new__(Agent)
    sys_ctrl_mock = MagicMock()
    sys_ctrl_mock.execute.return_value = {"success": True, "volume": 60}
    agent.system_control = sys_ctrl_mock

    result = await agent.execute_tool("system_control", ["volume_set", "60"])
    assert "system_control result" in result
    sys_ctrl_mock.execute.assert_called_once_with("volume_set", level=60)


@pytest.mark.asyncio
async def test_execute_tool_system_control_error():
    agent = Agent.__new__(Agent)
    sys_ctrl_mock = MagicMock()
    sys_ctrl_mock.execute.return_value = {"success": False, "error": "Platform not supported"}
    agent.system_control = sys_ctrl_mock

    result = await agent.execute_tool("system_control", ["shutdown"])
    assert "system_control error" in result
