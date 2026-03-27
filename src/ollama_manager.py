"""Ollama manager for GarudaAI.

Handles Ollama installation, lifecycle, and model management.
Cross-platform: Linux, macOS, Windows.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.request import urlopen, Request
from urllib.error import URLError

_IS_WINDOWS = sys.platform == "win32"

# Official Ollama download URLs
_OLLAMA_LINUX_INSTALL_URL = "https://ollama.com/install.sh"
_OLLAMA_WINDOWS_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"


class OllamaManager:
    """Manage Ollama installation and lifecycle."""

    OLLAMA_PORT = 11434

    def __init__(self, install_dir: str = "~/.local/share/garudaai/ollama"):
        self.install_dir = Path(install_dir).expanduser()
        self.ollama_bin = self.install_dir / "bin" / "ollama"
        self.models_dir = self.install_dir / "models"

    # ------------------------------------------------------------------
    # Installation checks
    # ------------------------------------------------------------------

    def is_installed(self) -> bool:
        """Check if Ollama is installed (system PATH or local binary)."""
        if shutil.which("ollama"):
            return True
        return self.ollama_bin.exists()

    def get_ollama_path(self) -> str:
        """Return path to the ollama binary."""
        path = shutil.which("ollama")
        if path:
            return path
        if self.ollama_bin.exists():
            return str(self.ollama_bin)
        return "ollama"

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------

    def install(self, progress_callback=None) -> bool:
        """Download and install Ollama safely (no shell=True)."""
        if self.is_installed():
            if progress_callback:
                progress_callback("Ollama already installed")
            return True

        if _IS_WINDOWS:
            return self._install_windows(progress_callback)
        else:
            return self._install_unix(progress_callback)

    def _install_unix(self, progress_callback=None) -> bool:
        """Install Ollama on Linux/macOS by downloading and running the install script."""
        if progress_callback:
            progress_callback("Downloading Ollama install script...")

        try:
            # Download the install script to a temp file (no shell=True)
            req = Request(_OLLAMA_LINUX_INSTALL_URL, headers={"User-Agent": "GarudaAI/0.1"})
            with urlopen(req, timeout=30) as resp:
                script_bytes = resp.read()

            with tempfile.NamedTemporaryFile(suffix=".sh", delete=False) as tmp:
                tmp.write(script_bytes)
                tmp_path = tmp.name

            if progress_callback:
                progress_callback("Running install script...")

            result = subprocess.run(
                ["sh", tmp_path],
                capture_output=True,
                text=True,
                timeout=300,
            )

            try:
                Path(tmp_path).unlink()
            except OSError:
                pass

            if result.returncode != 0:
                if progress_callback:
                    progress_callback(f"Install script failed: {result.stderr[:200]}")
                return False

            if self.is_installed():
                if progress_callback:
                    progress_callback("Ollama installed successfully")
                return True

            if progress_callback:
                progress_callback("Script ran but Ollama not found in PATH")
            return False

        except Exception as e:
            if progress_callback:
                progress_callback(f"Installation error: {e}")
            return False

    def _install_windows(self, progress_callback=None) -> bool:
        """Install Ollama on Windows by downloading and running the GUI installer silently."""
        if progress_callback:
            progress_callback("Downloading OllamaSetup.exe...")

        try:
            req = Request(_OLLAMA_WINDOWS_INSTALLER_URL, headers={"User-Agent": "GarudaAI/0.1"})
            with urlopen(req, timeout=120) as resp:
                installer_bytes = resp.read()

            with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
                tmp.write(installer_bytes)
                installer_path = tmp.name

            if progress_callback:
                progress_callback("Running OllamaSetup.exe silently...")

            result = subprocess.run(
                [installer_path, "/VERYSILENT", "/NORESTART"],
                capture_output=True,
                timeout=300,
            )

            try:
                Path(installer_path).unlink()
            except OSError:
                pass

            if self.is_installed():
                if progress_callback:
                    progress_callback("Ollama installed successfully")
                return True

            if progress_callback:
                progress_callback(f"Installer exited {result.returncode} but Ollama not found")
            return False

        except Exception as e:
            if progress_callback:
                progress_callback(f"Installation error: {e}")
            return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        """Check if Ollama is running."""
        try:
            response = urlopen(f"http://localhost:{self.OLLAMA_PORT}/api/tags", timeout=2)
            return response.status == 200
        except (URLError, Exception):
            return False

    def start(self, progress_callback=None) -> bool:
        """Start Ollama server."""
        if self.is_running():
            if progress_callback:
                progress_callback("Ollama already running")
            return True

        if not self.is_installed():
            if progress_callback:
                progress_callback("Ollama not installed, installing...")
            if not self.install(progress_callback):
                return False

        if progress_callback:
            progress_callback("Starting Ollama server...")

        ollama_path = self.get_ollama_path()

        try:
            popen_kwargs = dict(
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not _IS_WINDOWS:
                popen_kwargs["start_new_session"] = True

            subprocess.Popen([ollama_path, "serve"], **popen_kwargs)

            for i in range(30):
                if self.is_running():
                    if progress_callback:
                        progress_callback("Ollama server ready")
                    return True
                if progress_callback and i % 5 == 0:
                    progress_callback(f"Waiting for Ollama to start ({i}s)...")
                time.sleep(1)

            if progress_callback:
                progress_callback("Ollama startup timeout")
            return False

        except Exception as e:
            if progress_callback:
                progress_callback(f"Failed to start Ollama: {e}")
            return False

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def pull_model(self, model_name: str, progress_callback=None) -> bool:
        """Pull a model from Ollama registry."""
        if not self.is_running():
            if progress_callback:
                progress_callback("Ollama not running, starting...")
            if not self.start(progress_callback):
                return False

        if progress_callback:
            progress_callback(f"Pulling model {model_name}...")

        try:
            response = urlopen(
                f"http://localhost:{self.OLLAMA_PORT}/api/pull",
                data=json.dumps({"name": model_name}).encode(),
                timeout=None,
            )
            for line in response:
                try:
                    data = json.loads(line.decode())
                    if "status" in data:
                        status = data["status"]
                        if "digest" in data:
                            status += f" ({data['digest'][:12]}...)"
                        if progress_callback:
                            progress_callback(status)
                except json.JSONDecodeError:
                    pass

            if progress_callback:
                progress_callback(f"Model {model_name} ready")
            return True

        except Exception as e:
            if progress_callback:
                progress_callback(f"Failed to pull model: {e}")
            return False

    def list_models(self) -> List[Dict[str, Any]]:
        """List all downloaded models."""
        if not self.is_running():
            return []
        try:
            response = urlopen(f"http://localhost:{self.OLLAMA_PORT}/api/tags", timeout=5)
            data = json.loads(response.read().decode())
            return data.get("models", [])
        except Exception:
            return []

    def delete_model(self, model_name: str) -> bool:
        """Delete a model."""
        if not self.is_running():
            return False
        try:
            ollama_path = self.get_ollama_path()
            result = subprocess.run(
                [ollama_path, "rm", model_name],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get info about a specific model."""
        for model in self.list_models():
            if model.get("name") == model_name:
                return model
        return None


def get_ollama_manager() -> OllamaManager:
    """Convenience function to get manager."""
    return OllamaManager()
