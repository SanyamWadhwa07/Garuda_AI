"""Tests for filesystem tools."""

import pytest
from pathlib import Path
from src.tools.filesystem import FilesystemTool


@pytest.fixture
def fs_tool(tmp_path):
    """Create a filesystem tool with temp home directory."""
    return FilesystemTool(home_dir=str(tmp_path))


@pytest.fixture
def test_file(tmp_path):
    """Create a test file."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello, World!")
    return test_file


def test_read_file(fs_tool, test_file):
    """Test reading a file."""
    content = fs_tool.read_file(str(test_file))
    assert content == "Hello, World!"


def test_read_nonexistent_file(fs_tool):
    """Test reading a file that doesn't exist."""
    with pytest.raises(FileNotFoundError):
        fs_tool.read_file("/nonexistent/file.txt")


def test_path_traversal_protection(fs_tool):
    """Test that path traversal is prevented."""
    with pytest.raises(ValueError):
        fs_tool.read_file("/../../../etc/passwd")


def test_list_files(fs_tool, tmp_path):
    """Test listing files in a directory."""
    # Create some test files
    (tmp_path / "file1.txt").write_text("test1")
    (tmp_path / "file2.txt").write_text("test2")
    (tmp_path / "subdir").mkdir()

    files = fs_tool.list_files(str(tmp_path))

    assert len(files) > 0
    names = [f["name"] for f in files]
    assert "file1.txt" in names
    assert "file2.txt" in names
