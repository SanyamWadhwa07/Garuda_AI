"""Tests for OllamaManager — installation checks, running state, no shell=True."""

import sys
import shutil
from unittest.mock import patch, MagicMock
import subprocess

import pytest

from src.ollama_manager import OllamaManager


# ---------------------------------------------------------------------------
# is_installed
# ---------------------------------------------------------------------------

def test_is_installed_uses_shutil_which_found():
    """is_installed() returns True when shutil.which finds ollama."""
    with patch("src.ollama_manager.shutil.which", return_value="/usr/bin/ollama") as mock_which:
        mgr = OllamaManager()
        assert mgr.is_installed() is True
        mock_which.assert_called_once_with("ollama")


def test_is_installed_uses_shutil_which_not_found(tmp_path):
    """is_installed() returns False when ollama not on PATH and local bin absent."""
    with patch("src.ollama_manager.shutil.which", return_value=None):
        mgr = OllamaManager(install_dir=str(tmp_path))
        assert mgr.is_installed() is False


# ---------------------------------------------------------------------------
# is_running
# ---------------------------------------------------------------------------

def test_is_running_checks_http_success():
    """is_running() returns True on 200 from /api/tags."""
    mock_response = MagicMock()
    mock_response.status = 200

    with patch("src.ollama_manager.urlopen", return_value=mock_response):
        mgr = OllamaManager()
        assert mgr.is_running() is True


def test_is_running_checks_http_failure():
    """is_running() returns False on URLError."""
    from urllib.error import URLError
    with patch("src.ollama_manager.urlopen", side_effect=URLError("connection refused")):
        mgr = OllamaManager()
        assert mgr.is_running() is False


# ---------------------------------------------------------------------------
# install — verify shell=False (no shell injection risk)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="Unix install path only")
def test_install_unix_no_shell_true(tmp_path):
    """_install_unix() must not use shell=True — verifies shell injection fix."""
    script_content = b"#!/bin/sh\necho installed"
    mock_response = MagicMock()
    mock_response.read.return_value = script_content
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    captured_calls = []

    def fake_run(cmd, **kwargs):
        captured_calls.append((cmd, kwargs))
        result = MagicMock()
        result.returncode = 0
        return result

    with patch("src.ollama_manager.urlopen", return_value=mock_response), \
         patch("src.ollama_manager.subprocess.run", side_effect=fake_run):
        mgr = OllamaManager()
        mgr._install_unix()

    # Verify no call used shell=True
    for cmd, kwargs in captured_calls:
        assert kwargs.get("shell") is not True, (
            f"shell=True found in call: {cmd} — this is a shell injection risk!"
        )
    # Verify the install script was executed as a list (not a string)
    install_calls = [c for c in captured_calls if isinstance(c[0], list) and c[0][0] == "sh"]
    assert len(install_calls) >= 1, "Expected 'sh <script>' subprocess call"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows install path only")
def test_install_windows_no_shell_true(tmp_path):
    """_install_windows() must not use shell=True."""
    exe_bytes = b"MZ fake exe"
    mock_response = MagicMock()
    mock_response.read.return_value = exe_bytes
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    captured_calls = []

    def fake_run(cmd, **kwargs):
        captured_calls.append((cmd, kwargs))
        result = MagicMock()
        result.returncode = 0
        return result

    with patch("src.ollama_manager.urlopen", return_value=mock_response), \
         patch("src.ollama_manager.subprocess.run", side_effect=fake_run):
        mgr = OllamaManager()
        mgr._install_windows()

    for cmd, kwargs in captured_calls:
        assert kwargs.get("shell") is not True, (
            f"shell=True found in call: {cmd}"
        )


# ---------------------------------------------------------------------------
# get_ollama_path
# ---------------------------------------------------------------------------

def test_get_ollama_path_from_which():
    with patch("src.ollama_manager.shutil.which", return_value="/usr/local/bin/ollama"):
        mgr = OllamaManager()
        assert mgr.get_ollama_path() == "/usr/local/bin/ollama"


def test_get_ollama_path_fallback_when_missing(tmp_path):
    """get_ollama_path() returns 'ollama' as fallback when not found (trusts PATH at runtime)."""
    with patch("src.ollama_manager.shutil.which", return_value=None):
        mgr = OllamaManager(install_dir=str(tmp_path))
        # Falls back to "ollama" string — relies on PATH at runtime
        assert mgr.get_ollama_path() == "ollama"
