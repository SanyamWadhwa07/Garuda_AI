"""Tests for shell tools."""

import pytest
from src.tools.shell import ShellTool


@pytest.fixture
def shell_tool():
    """Create a shell tool instance."""
    return ShellTool()


def test_execute_safe_command(shell_tool):
    """Test executing a whitelisted command."""
    result = shell_tool.execute("echo", "hello")

    assert result["success"]
    assert "hello" in result["stdout"]


def test_execute_unsafe_command(shell_tool):
    """Test that unsafe commands are rejected."""
    with pytest.raises(ValueError):
        shell_tool.execute("rm", "-rf", "/")


def test_command_whitelist(shell_tool):
    """Test whitelist management."""
    assert "ls" in shell_tool.allowed_commands

    shell_tool.add_to_whitelist("custom_cmd")
    assert "custom_cmd" in shell_tool.allowed_commands

    shell_tool.remove_from_whitelist("custom_cmd")
    assert "custom_cmd" not in shell_tool.allowed_commands
