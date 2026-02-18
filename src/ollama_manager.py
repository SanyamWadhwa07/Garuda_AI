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

    # Official Ollama install script - handles all platform details
    OLLAMA_INSTALL_URL = "https://ollama.com/install.sh"
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
        """Download and install Ollama using official install script.
        
        Args:
            progress_callback: Optional function to call with progress messages
            
        Returns:
            True if installation successful or already installed
        """
        if self.is_installed():
            if progress_callback:
                progress_callback("Ollama already installed")
            return True

        if progress_callback:
            progress_callback("Installing Ollama via official install script...")
            progress_callback(f"Running: curl -fsSL {self.OLLAMA_INSTALL_URL} | sh")

        try:
            # Use official Ollama install script
            # The script handles all platform-specific installation details
            result = subprocess.run(
                f"curl -fsSL {self.OLLAMA_INSTALL_URL} | sh",
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes for download + install
            )
            
            if result.returncode != 0:
                if progress_callback:
                    progress_callback(f"Installation script failed: {result.stderr}")
                    progress_callback("Please ensure you have curl installed and can access https://ollama.com")
                return False

            # Verify installation
            if self.is_installed():
                if progress_callback:
                    progress_callback("Ollama installed successfully")
                return True
            else:
                if progress_callback:
                    progress_callback("Installation script ran but Ollama binary not found")
                    progress_callback("Tip: Try running 'curl -fsSL https://ollama.com/install.sh | sh' manually")
                return False

        except subprocess.TimeoutExpired:
            if progress_callback:
                progress_callback("Installation timed out (took > 5 minutes)")
                progress_callback("Tip: Try running 'curl -fsSL https://ollama.com/install.sh | sh' manually")
            return False
        except Exception as e:
            if progress_callback:
                progress_callback(f"Installation error: {e}")
                progress_callback("Tip: Try running 'curl -fsSL https://ollama.com/install.sh | sh' manually")
            return False

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
