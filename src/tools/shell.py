"""Shell execution tools for GarudaAI agent.

Provides safe, whitelisted shell command execution.
"""

import subprocess
from typing import List, Dict, Optional, Any


class ShellTool:
    """Safe shell command execution with whitelist."""

    # Commands that are safe to run
    DEFAULT_WHITELIST = {
        "ls", "find", "grep", "pwd", "cat", "head", "tail",
        "file", "stat", "wc", "echo", "date", "whoami",
        "uptime", "free", "df", "which", "type",
    }

    def __init__(self, whitelist: Optional[List[str]] = None, timeout_seconds: int = 30):
        """Initialize shell tool.
        
        Args:
            whitelist: List of allowed commands (default: safe set)
            timeout_seconds: Max time to run a command
        """
        self.whitelist = set(whitelist or self.DEFAULT_WHITELIST)
        self.timeout_seconds = timeout_seconds

    def execute(self, command: str, *args) -> Dict[str, Any]:
        """Execute a shell command safely.
        
        Args:
            command: First part of command (must be whitelisted)
            *args: Arguments to pass
            
        Returns:
            Dict with stdout, stderr, returncode, execution_time_ms
            
        Raises:
            ValueError: If command not in whitelist
        """
        # Check if command is whitelisted
        if command not in self.whitelist:
            raise ValueError(f"Command not allowed: {command}")

        full_command = [command] + list(args)

        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

            return {
                "stdout": result.stdout[:10000],  # Limit output
                "stderr": result.stderr[:10000],
                "returncode": result.returncode,
                "success": result.returncode == 0,
            }

        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Command timed out after {self.timeout_seconds}s",
                "returncode": 124,
                "success": False,
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "returncode": 1,
                "success": False,
            }

    def add_to_whitelist(self, *commands: str):
        """Add commands to the whitelist."""
        self.whitelist.update(commands)

    def remove_from_whitelist(self, *commands: str):
        """Remove commands from the whitelist."""
        self.whitelist.difference_update(commands)

    @property
    def allowed_commands(self) -> List[str]:
        """Get list of allowed commands."""
        return sorted(self.whitelist)


def create_shell_tool(whitelist: Optional[List[str]] = None) -> ShellTool:
    """Create a shell tool instance."""
    return ShellTool(whitelist)
