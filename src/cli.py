"""CLI tool for GarudaAI."""

import sys
import json
import os
import subprocess
from pathlib import Path
from typing import Optional
import ssl

# On Windows the default console encoding is cp1252 which can't print ✓ ✗ etc.
# Reconfigure stdout/stderr to UTF-8 so Unicode output works everywhere.
if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_is_windows = sys.platform == "win32"

import click
from click import echo, style

from .hardware import HardwareDetector, detect_hardware
from .models import ModelSuggester
from .ollama_manager import OllamaManager


# Global config path
CONFIG_DIR = Path("~/.config/garudaai").expanduser()
CONFIG_FILE = CONFIG_DIR / "config.toml"


def ensure_config_dir():
    """Ensure config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load configuration from file."""
    if not CONFIG_FILE.exists():
        return {}

    import tomli
    try:
        with open(CONFIG_FILE, 'rb') as f:
            return tomli.load(f)
    except Exception as e:
        echo(f"Error loading config: {e}", err=True)
        return {}


def save_config(config: dict):
    """Save configuration to file."""
    ensure_config_dir()
    import tomli_w
    with open(CONFIG_FILE, 'wb') as f:
        tomli_w.dump(config, f)


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    from passlib.hash import bcrypt
    return bcrypt.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    from passlib.hash import bcrypt
    try:
        return bcrypt.verify(plain, hashed)
    except Exception:
        return False


def _generate_self_signed_cert(key_file: Path, cert_file: Path):
    """Generate a self-signed TLS certificate using the cryptography library."""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "garudaai.local"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("garudaai.local"),
                x509.DNSName("localhost"),
            ]), critical=False)
            .sign(key, hashes.SHA256())
        )
        key_file.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        click.echo("✓ Self-signed certificate generated")
    except ImportError:
        # Fall back to openssl CLI on non-Windows
        if not _is_windows:
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key_file), "-out", str(cert_file),
                "-days", "365", "-nodes", "-subj", "/CN=garudaai.local"
            ], check=False, capture_output=True)
            click.echo("✓ Self-signed certificate generated (openssl)")
        else:
            click.echo("⚠️ Install 'cryptography' package for HTTPS support: pip install cryptography")


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """GarudaAI - Local AI Agent Platform.
    
    A self-hosted, hardware-aware, phone-controlled AI agent for Garuda Linux.
    """
    pass


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def detect(output_json: bool):
    """Detect system hardware capabilities."""
    click.echo(style("Detecting hardware...", fg="cyan"))

    hardware = detect_hardware(force_refresh=True)

    if output_json:
        click.echo(json.dumps(hardware, indent=2))
    else:
        click.echo(f"\n{style('Hardware Detection Results:', bold=True)}")
        click.echo(f"  GPU Vendor: {hardware.get('gpu_vendor') or 'None (CPU only)'}")
        click.echo(f"  GPU VRAM: {hardware.get('vram_mb', 0) / 1024:.1f} GB")
        click.echo(f"  CPU Cores: {hardware.get('cpu_cores')}")
        click.echo(f"  System RAM: {hardware.get('ram_mb') / 1024:.1f} GB")
        click.echo(f"  Disk Speed: {hardware.get('disk_speed_mbps'):.1f} MB/s")
        click.echo(f"  Compute Available: {style('✓' if hardware.get('compute_ok') else '✗', fg='green' if hardware.get('compute_ok') else 'red')}")


@cli.command()
@click.option("--use-case", type=click.Choice(["chat", "coding", "reasoning", "vision"]), help="Filter by use case")
@click.option("--prefer-smaller/--prefer-larger", default=True, help="Prefer smaller/faster models when recommending")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def suggest(use_case: Optional[str], prefer_smaller: bool, output_json: bool):
    """Suggest models based on hardware."""
    click.echo(style("Detecting hardware and analyzing models...", fg="cyan"))

    hardware = detect_hardware()
    vram_mb = hardware.get("vram_mb", 0)

    suggester = ModelSuggester()
    suggestion = suggester.suggest(
        vram_mb=vram_mb,
        cpu_cores=hardware.get("cpu_cores", 4),
        ram_mb=hardware.get("ram_mb", 8192),
        use_case=use_case,
        prefer_smaller=prefer_smaller,
    )

    if output_json:
        click.echo(json.dumps(suggestion, indent=2))
    else:
        click.echo(f"\n{style('Model Recommendation:', bold=True)}")
        click.echo(f"  Primary: {style(suggestion['primary_model'], fg='green', bold=True)}")
        click.echo(f"  Reason: {suggestion['reason']}")

        if suggestion["alternatives"]:
            click.echo(f"  Alternatives: {', '.join(suggestion['alternatives'])}")

        click.echo(f"\n{style('All Matching Models:', bold=True)}")
        for model in suggestion["all_matching"]:
            click.echo(f"  • {model['name']:<20} ({model['parameters_billion']:.1f}B) - {model['description']}")


@cli.command()
@click.option("--password", prompt=False, hide_input=True, help="Set password (prompted if not provided)")
@click.option("--no-password", is_flag=True, help="Disable password protection (not recommended)")
@click.option("--port", type=int, default=8000, help="Port for web interface (default: 8000)")
@click.option("--prefer-smaller/--prefer-larger", default=True, help="Prefer smaller/faster models when recommending")
def setup(password: Optional[str], no_password: bool, port: int, prefer_smaller: bool):
    """Set up GarudaAI for first run."""
    click.echo(style("Welcome to GarudaAI Setup", fg="cyan", bold=True))
    click.echo()

    # Hardware detection
    click.echo(style("Step 1: Detecting hardware...", fg="cyan"))
    hardware = detect_hardware()
    vram_mb = hardware.get("vram_mb", 0)
    
    click.echo(f"✓ Detected: {hardware.get('gpu_vendor') or 'CPU'} / {vram_mb/1024:.1f}GB VRAM")
    click.echo()

    # Model suggestion
    click.echo(style("Step 2: Recommending models...", fg="cyan"))
    suggester = ModelSuggester()
    suggestion = suggester.suggest(
        vram_mb,
        cpu_cores=hardware.get("cpu_cores", 4),
        ram_mb=hardware.get("ram_mb", 8192),
        prefer_smaller=prefer_smaller,
    )
    
    click.echo(f"✓ Recommended model: {style(suggestion['primary_model'], fg='green')}")
    click.echo()

    # Ollama setup
    click.echo(style("Step 3: Setting up Ollama...", fg="cyan"))
    ollama = OllamaManager()

    def progress(msg):
        click.echo(f"  {msg}")

    if ollama.is_installed():
        click.echo("✓ Ollama already installed")
    else:
        click.echo("  Note: Ollama needs to be installed to run models.")
        try_install = click.confirm("  Attempt to download and install Ollama?", default=True)
        
        if try_install:
            click.echo("  Installing Ollama...")
            if ollama.install(progress):
                click.echo("✓ Ollama installed")
            else:
                click.echo(style("⚠️ Ollama installation failed", fg="yellow"))
                click.echo("   Install Ollama manually with:")
                click.echo("   curl -fsSL https://ollama.com/install.sh | sh")
                click.echo("   Then restart this setup.")
        else:
            click.echo("  Skipping Ollama installation.")
            click.echo("  To use GarudaAI, please install Ollama manually.")

    # Start Ollama
    click.echo("  Checking for Ollama server...")
    if not ollama.is_running():
        click.echo("  Ollama not running. Attempting to start...")
        if ollama.start(progress):
            click.echo("✓ Ollama server running")
        else:
            click.echo(style("⚠️ Could not start Ollama", fg="yellow"))
            click.echo("   Make sure Ollama is installed, then run in another terminal:")
            click.echo("   ollama serve")
    else:
        click.echo("✓ Ollama server already running")

    # Pull model (if Ollama is available)
    if ollama.is_running():
        click.echo(f"  Pulling recommended model ({suggestion['primary_model']})...")
        if ollama.pull_model(suggestion['primary_model_url'], progress):
            click.echo("✓ Model ready")
        else:
            click.echo(style("⚠️ Failed to pull model", fg="yellow"))
            click.echo(f"   You can pull it manually with: ollama pull {suggestion['primary_model_url']}")
    else:
        click.echo(style("ℹ️ Model will be downloaded when you start the server", fg="cyan"))
        click.echo(f"   Once Ollama is running, pull with: ollama pull {suggestion['primary_model_url']}")

    click.echo()

    # Password setup
    click.echo(style("Step 4: Security Setup", fg="cyan"))
    click.echo("  Note: Passwords are hashed with bcrypt. Re-run setup if you had a previous SHA256 hash.")
    if no_password:
        password_hash = ""
        click.echo("⚠️ Password protection disabled (only use on trusted networks!)")
    else:
        if not password:
            password = click.prompt("Enter password for web interface", hide_input=True, confirmation_prompt=True)
        password_hash = hash_password(password)
        click.echo("✓ Password set (bcrypt)")

    click.echo()

    # Save config
    click.echo(style("Step 5: Saving configuration...", fg="cyan"))
    ensure_config_dir()

    config = {
        "server": {
            "port": port,
            "https": True,
            "bind_all": True,
        },
        "auth": {
            "password_hash": password_hash,
        },
        "models": {
            "default_model": suggestion["primary_model"],
            "ollama_url": "http://localhost:11434",
            "prefer_smaller": prefer_smaller,
        },
        "paths": {
            "home_dir": "~",
            "session_dir": "~/.local/share/garudaai",
            "cache_dir": "~/.cache/garudaai",
        },
        "tools": {
            "filesystem_enabled": True,
            "shell_enabled": True,
        },
        "features": {
            "voice_input": True,
            "file_browser": True,
        },
    }

    save_config(config)
    click.echo(f"✓ Config saved to {CONFIG_FILE}")
    click.echo()

    click.echo(style("Setup Complete!", fg="green", bold=True))
    click.echo()
    click.echo(f"Start the server with: {style('garudaai serve', fg='yellow')}")
    click.echo(f"Access at: {style('https://garudaai.local:' + str(port), fg='yellow')}")


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
@click.option("--port", type=int, help="Port (overrides config)")
@click.option("--https", is_flag=True, default=True, help="Enable HTTPS (default: enabled)")
def serve(host: str, port: Optional[int], https: bool):
    """Start the GarudaAI server."""
    config = load_config()

    if not port:
        port = config.get("server", {}).get("port", 8000)

    click.echo(style("Starting GarudaAI Server...", fg="cyan", bold=True))
    click.echo(f"  Host: {host}")
    click.echo(f"  Port: {port}")
    click.echo(f"  HTTPS: {style('✓' if https else '✗', fg='green' if https else 'dim')}")
    click.echo()

    # Generate self-signed cert if needed
    cert_dir = Path("~/.local/share/garudaai").expanduser()
    cert_dir.mkdir(parents=True, exist_ok=True)
    key_file = cert_dir / "garudaai.key"
    cert_file = cert_dir / "garudaai.crt"

    if https and not (key_file.exists() and cert_file.exists()):
        click.echo("Generating self-signed certificate...")
        _generate_self_signed_cert(key_file, cert_file)

    # Register mDNS (Linux only)
    if not _is_windows:
        try:
            subprocess.Popen([
                "avahi-publish-service",
                "garudaai", "_http._tcp", str(port),
                "path=/", "description=GarudaAI Local AI Agent"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            click.echo(f"✓ Registered at {style('garudaai.local:' + str(port), fg='green')}")
        except FileNotFoundError:
            click.echo("  (Avahi not available; use localhost)")
    else:
        click.echo(f"  Access at https://localhost:{port}")

    click.echo()
    click.echo(style("Server running. Press Ctrl+C to stop.", fg="green"))

    # Import and run agent
    from .agent import run_agent

    ssl_kwargs = {}
    if https and key_file.exists() and cert_file.exists():
        ssl_kwargs = {
            "ssl_keyfile": str(key_file),
            "ssl_certfile": str(cert_file),
        }

    run_agent(host=host, port=port, **ssl_kwargs)


@cli.command()
def status():
    """Check GarudaAI status."""
    click.echo(style("GarudaAI Status", fg="cyan", bold=True))
    click.echo()

    # Check config
    if CONFIG_FILE.exists():
        click.echo(f"✓ Configured: {CONFIG_FILE}")
    else:
        click.echo(f"✗ Not configured (run 'garudaai setup')")
        return

    # Check Ollama
    ollama = OllamaManager()
    if ollama.is_running():
        click.echo("✓ Ollama running")
        models = ollama.list_models()
        if models:
            click.echo(f"  Models: {', '.join(m.get('name', '?') for m in models)}")
    else:
        click.echo("✗ Ollama not running (start with 'garudaai serve')")

    # Check service (Linux) or HTTP probe (Windows)
    if _is_windows:
        try:
            from urllib.request import urlopen
            config = load_config()
            srv_port = config.get("server", {}).get("port", 8000)
            urlopen(f"http://localhost:{srv_port}/api/health", timeout=2)
            click.echo("✓ Server responding on localhost")
        except Exception:
            click.echo("✗ Server not reachable (run 'garudaai serve')")
    else:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", "garudaai"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                click.echo("✓ Service running")
            else:
                click.echo("✗ Service not running")
        except FileNotFoundError:
            click.echo("  (systemd service not installed)")


@cli.command()
@click.option("-n", "--lines", type=int, default=50, help="Number of lines to show")
def logs(lines: int):
    """View service logs."""
    if _is_windows:
        log_file = Path("~/.local/share/garudaai/garudaai.log").expanduser()
        if not log_file.exists():
            click.echo("No log file found. Start the server first.", err=True)
            return
        try:
            all_lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in all_lines[-lines:]:
                click.echo(line)
        except Exception as e:
            click.echo(f"Error reading log: {e}", err=True)
    else:
        try:
            subprocess.run(["journalctl", "--user", "-u", "garudaai", "-n", str(lines), "--no-pager"])
        except FileNotFoundError:
            click.echo("journalctl not found", err=True)


def main():
    """Main entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\nInterrupted", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
