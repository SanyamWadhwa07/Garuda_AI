# 🦅 GarudaAI

> Self-hosted, hardware-aware, phone-controlled local AI agent platform.

Run powerful AI models entirely on your own hardware. Control your laptop from your phone. No cloud, no subscriptions, no data leaving your machine.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)]()

---

## Install

**Linux / macOS**
```bash
curl -fsSL https://raw.githubusercontent.com/SanyamWadhwa07/Garuda_AI/main/install.sh | sh
```

**Windows (PowerShell)**
```powershell
irm https://raw.githubusercontent.com/SanyamWadhwa07/Garuda_AI/main/install.ps1 | iex
```

**pip (manual)**
```bash
pip install git+https://github.com/SanyamWadhwa07/Garuda_AI.git
```

The installer handles Python version checks, pip, Ollama, firewall rules (Windows), and PATH setup automatically.

---

## Quick Start

```bash
garudaai setup    # one-time wizard — detects GPU, picks a model, sets password
garudaai serve    # start the server
```

Open **`https://localhost:8000`** in your browser (accept the self-signed cert warning).
Access from your phone at **`https://<your-local-IP>:8000`** on the same WiFi.

> **Windows note:** If `garudaai` is not on PATH after install, run `pip install -e .` inside the repo directory or use `python -m src.cli <command>`.

---

## Features

| | |
|---|---|
| 🧠 **Hardware-aware** | Detects GPU/CPU/RAM, runs a live inference benchmark, and recommends the best model for your machine |
| 📱 **Phone control** | Screenshot, volume, power, processes, notifications — all from your phone |
| 💬 **Streaming chat** | WebSocket streaming with markdown rendering and syntax highlighting |
| 🎤 **Voice I/O** | Whisper speech-to-text input + Piper TTS output (local, no cloud) |
| 📸 **Camera vision** | Capture a photo from your phone camera and ask the AI what it sees (LLaVA / llama3.2-vision) |
| 📚 **RAG documents** | Upload PDFs and text files — ask questions about your own documents |
| 🧬 **Persona (SOUL.md)** | Edit a markdown file to define the AI's personality and persistent facts about you |
| 📖 **Session history** | All conversations saved in a local SQLite database |
| 🐌 **AirLLM Slow Mode** | Run 70B+ models on 4GB VRAM via SSD layer offloading |
| 🔒 **Secure** | bcrypt auth, TLS, rate limiting, sandboxed tools |
| 🔓 **Full access mode** | Optionally grant unrestricted filesystem and shell access |
| 🌐 **PWA** | Installable on Android/iOS, works offline |
| 🖥️ **Cross-platform** | Linux, macOS, Windows |

---

## CLI Reference

```bash
garudaai detect    # Show GPU, CPU, RAM, disk speed
garudaai suggest   # Get model recommendations (runs a live benchmark)
garudaai setup     # First-time setup wizard
garudaai serve     # Start the server (default: https://0.0.0.0:8000)
garudaai status    # Check Ollama and server status
```

---

## Supported Models

| VRAM | Models |
|---|---|
| 2–4 GB | `gemma2:2b`, `phi3.5:3.8b`, `qwen2.5:3b`, `llama3.2:3b` |
| 4–8 GB | `mistral:7b`, `qwen2.5:7b`, `deepseek-coder-v2:7b` |
| 8–16 GB | `llama3.1:8b`, `gemma2:9b`, `mistral-nemo:12b`, `qwen2.5:14b` |
| 16+ GB | `llama3.3:70b`, `qwen2.5:32b` |
| Any + SSD | 70B models via AirLLM Slow Mode (1–3 min/reply) |

Vision models: `llava:7b`, `llama3.2-vision:11b` (used automatically when a camera photo is attached).

Pull any model with:
```bash
ollama pull gemma2:2b
```

---

## Optional Features

Install extras as needed:

```bash
pip install garudaai[voice]   # Whisper STT (faster-whisper)
pip install garudaai[rag]     # Document Q&A (chromadb + pypdf)
pip install garudaai[airllm]  # 70B models on small GPUs (AirLLM)
```

**Voice output (Piper TTS):** Piper is a standalone binary. Download from the [Piper releases page](https://github.com/rhasspy/piper/releases) and place it at `~/.local/share/garudaai/piper/piper` (Linux/macOS) or `%APPDATA%\garudaai\piper\piper.exe` (Windows).

**RAG embedding model:** Pull `nomic-embed-text` once via Ollama:
```bash
ollama pull nomic-embed-text
```

---

## Phone Control

Ask the AI to control your laptop:

```
"Take a screenshot"
"What's my CPU usage?"
"Set volume to 40%"
"Show me the top 10 processes"
"Lock my screen"
"Open YouTube"
"Send me a desktop notification when done"
```

---

## Persona (SOUL.md)

Edit `~/.config/garudaai/SOUL.md` to define the AI's personality and facts about you. Changes take effect within 60 seconds without restarting the server.

```markdown
# My AI Persona

## Personality
You are a helpful, direct assistant. Prefer code examples over long explanations.

## About Me
- Name: Sanyam
- Role: Developer

## Persistent Facts
- I prefer Python with type hints
```

You can also edit SOUL.md directly from the Settings tab in the UI.

---

## AirLLM — Big Models on Small GPUs

Run 70B parameter models on a 4GB GPU using layer-by-layer SSD offloading:

```bash
pip install garudaai[airllm]
```

Select a `-airllm` model in the UI. Requires an SSD (≥400 MB/s). Responses take 1–3 min.

---

## Full System Access

By default, file access is sandboxed to your home directory and shell commands are whitelisted. During `garudaai setup` you can enable full access mode, which allows the AI to read any file and run any shell command on your machine.

You can also toggle it manually in `~/.config/garudaai/config.toml`:

```toml
[tools]
full_access = true
```

Restart the server after changing this.

---

## Development

```bash
git clone https://github.com/SanyamWadhwa07/Garuda_AI
cd Garuda_AI
pip install -e ".[dev]"

pytest tests/                     # run tests
black src/ && ruff check src/     # format & lint
```

---

## Project Structure

```
src/
├── agent.py              # FastAPI app — WebSocket, auth, sessions, tool loop
├── cli.py                # Click CLI (setup, serve, detect, suggest, status)
├── hardware.py           # Cross-platform GPU/CPU/RAM/disk detection + benchmark
├── models.py             # Model database + recommendation engine
├── ollama_manager.py     # Ollama install, start, pull
├── airllm_backend.py     # AirLLM layer-offloading for big models
├── tools/
│   ├── filesystem.py     # File reader (sandboxed to $HOME, or full access)
│   ├── shell.py          # Shell execution (whitelisted or full access)
│   ├── system_control.py # Remote laptop control
│   └── rag_tool.py       # Document ingestion and semantic search
└── static/               # PWA frontend — vanilla JS, no build step
```

Config: `~/.config/garudaai/config.toml`
Persona: `~/.config/garudaai/SOUL.md`
Sessions: `~/.local/share/garudaai/sessions.db`
Logs: `~/.local/share/garudaai/garudaai.log`

---

## License

MIT © [Sanyam Wadhwa](https://github.com/SanyamWadhwa07)
