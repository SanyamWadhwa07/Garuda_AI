"""Ollama manager for GarudaAI.

Handles Ollama installation, lifecycle, and model management.
"""

import subprocess
import json
import time
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.request import urlopen
from urllib.error import URLError


class OllamaManager:
    """Manage Ollama installation and lifecycle."""

    OLLAMA_URL = "https://github.com/ollama/ollama/releases/download/v0.1.29/ollama-linux-x86_64.tgz"
    OLLAMA_PORT = 11434

    def __init__(self, install_dir: str = "~/.local/share/garudaai/ollama"):
        """Initialize Ollama manager.
        
        Args:
            install_dir: Directory to install Ollama to
        """
        self.install_dir = Path(install_dir).expanduser()
        self.ollama_bin = self.install_dir / "bin" / "ollama"
        self.models_dir = self.install_dir / "models"

    def is_installed(self) -> bool:
        """Check if Ollama is installed."""
        # Check system ollama first
        try:
            subprocess.run(
                ["which", "ollama"],
                capture_output=True,
                check=True,
                timeout=2,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Check local installation
        return self.ollama_bin.exists()

    def get_ollama_path(self) -> str:
        """Get path to ollama binary."""
        try:
            result = subprocess.run(
                ["which", "ollama"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        if self.ollama_bin.exists():
            return str(self.ollama_bin)

        return "ollama"  # Fallback: assume in PATH

    def install(self, progress_callback=None) -> bool:
        """Download and install Ollama.
        
        Args:
            progress_callback: Optional function to call with progress messages
            
        Returns:
            True if installation successful
        """
        if self.is_installed():
            if progress_callback:
                progress_callback("Ollama already installed")
            return True

        if progress_callback:
            progress_callback(f"Downloading Ollama from {self.OLLAMA_URL}...")

        self.install_dir.mkdir(parents=True, exist_ok=True)

        # Download
        try:
            tar_path = self.install_dir / "ollama.tgz"
            urlopen(self.OLLAMA_URL)
            # Stream download with progress
            with urlopen(self.OLLAMA_URL) as response:
                with open(tar_path, 'wb') as out:
                    total = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        out.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total > 0:
                            pct = int(100 * downloaded / total)
                            progress_callback(f"Downloaded {pct}%")
        except URLError as e:
            if progress_callback:
                progress_callback(f"Download failed: {e}")
            return False

        # Extract
        if progress_callback:
            progress_callback("Extracting Ollama...")
        try:
            subprocess.run(
                ["tar", "-xzf", str(tar_path), "-C", str(self.install_dir)],
                check=True,
                timeout=30,
            )
            tar_path.unlink()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            if progress_callback:
                progress_callback(f"Extraction failed: {e}")
            return False

        if progress_callback:
            progress_callback("Ollama installed successfully")
        return True

    def is_running(self) -> bool:
        """Check if Ollama is running."""
        try:
            response = urlopen(f"http://localhost:{self.OLLAMA_PORT}/api/tags", timeout=2)
            return response.status == 200
        except (URLError, Exception):
            return False

    def start(self, progress_callback=None) -> bool:
        """Start Ollama server.
        
        Args:
            progress_callback: Optional function to call with progress messages
            
        Returns:
            True if Ollama started successfully
        """
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
            # Start Ollama in background via systemd user service if managed by us
            # For now, try to start directly
            subprocess.Popen(
                [ollama_path, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            # Wait for health check
            max_retries = 30
            for i in range(max_retries):
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

    def pull_model(self, model_name: str, progress_callback=None) -> bool:
        """Pull a model from Ollama registry.
        
        Args:
            model_name: Model name (e.g., "neural-chat:7b")
            progress_callback: Optional function to call with progress messages
            
        Returns:
            True if model pulled successfully
        """
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
                timeout=None,  # No timeout for large model pulls
            )

            # Stream response
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
            # Ollama doesn't have a standard delete API yet, so use CLI
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
        models = self.list_models()
        for model in models:
            if model.get("name") == model_name:
                return model
        return None


def get_ollama_manager() -> OllamaManager:
    """Convenience function to get manager."""
    return OllamaManager()
