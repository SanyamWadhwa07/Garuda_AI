"""Filesystem tools for GarudaAI agent.

Provides sandboxed file access (read-only in Phase 1).
"""

import os
from pathlib import Path
from typing import List, Dict, Optional, Any


class FilesystemTool:
    """Filesystem access — sandboxed to home dir by default, or full system if full_access=True."""

    def __init__(self, home_dir: str = "~", full_access: bool = False):
        """Initialize filesystem tool.

        Args:
            home_dir: Root directory for sandboxed access (default: $HOME)
            full_access: If True, disable sandbox — AI can read any path on the system
        """
        self.full_access = full_access
        if full_access:
            import sys
            # Use filesystem root so relative_to() always succeeds
            self.home_dir = Path("C:\\") if sys.platform == "win32" else Path("/")
        else:
            self.home_dir = Path(home_dir).expanduser().resolve()

    def _validate_path(self, path: str) -> Path:
        """Resolve a path. In full_access mode any path is allowed; otherwise must be under home_dir."""
        requested = Path(path).expanduser().resolve()

        if self.full_access:
            return requested

        try:
            requested.relative_to(self.home_dir)
        except ValueError:
            raise ValueError(f"Access denied: {path} is outside allowed directory {self.home_dir}")

        return requested

    def read_file(self, path: str, max_size_mb: int = 10) -> str:
        """Read a file (text only).
        
        Args:
            path: Path to file
            max_size_mb: Maximum file size to read (default: 10MB)
            
        Returns:
            File contents
            
        Raises:
            ValueError: If path is invalid or file too large
            FileNotFoundError: If file doesn't exist
        """
        file_path = self._validate_path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not file_path.is_file():
            raise ValueError(f"Not a file: {path}")

        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > max_size_mb:
            raise ValueError(f"File too large ({size_mb:.1f}MB > {max_size_mb}MB limit)")

        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()

    def list_files(
        self,
        path: str = ".",
        recursive: bool = False,
        pattern: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List files in a directory.
        
        Args:
            path: Directory path (default: current home)
            recursive: Include subdirectories
            pattern: Optional glob pattern filter
            
        Returns:
            List of dicts with name, type, size, modified_time
        """
        dir_path = self._validate_path(path)

        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not dir_path.is_dir():
            raise ValueError(f"Not a directory: {path}")

        results = []

        if recursive:
            iterator = dir_path.rglob(pattern or "*")
        else:
            iterator = dir_path.glob(pattern or "*")

        for item in iterator:
            # Skip symlinks that might escape sandbox
            if item.is_symlink():
                try:
                    item.resolve().relative_to(self.home_dir)
                except ValueError:
                    continue

            try:
                stat = item.stat(follow_symlinks=False)
                results.append({
                    "name": item.name,
                    "path": str(item.relative_to(self.home_dir)),
                    "type": "dir" if item.is_dir() else "file",
                    "size_bytes": stat.st_size,
                    "modified_timestamp": stat.st_mtime,
                })
            except (PermissionError, OSError):
                # Skip files we can't read
                continue

        return sorted(results, key=lambda x: (x["type"] != "dir", x["name"]))

    def get_file_info(self, path: str) -> Dict[str, Any]:
        """Get information about a file.
        
        Args:
            path: Path to file
            
        Returns:
            Dict with name, type, size, created, modified, permissions
        """
        file_path = self._validate_path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        stat = file_path.stat()

        return {
            "name": file_path.name,
            "path": str(file_path.relative_to(self.home_dir)),
            "type": "dir" if file_path.is_dir() else "file",
            "size_bytes": stat.st_size,
            "permissions": oct(stat.st_mode)[-3:],
            "created_timestamp": stat.st_ctime,
            "modified_timestamp": stat.st_mtime,
            "is_readable": os.access(file_path, os.R_OK),
        }


def create_filesystem_tool(home_dir: str = "~") -> FilesystemTool:
    """Create a filesystem tool instance."""
    return FilesystemTool(home_dir)
