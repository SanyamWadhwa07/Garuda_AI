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

Open **`http://localhost:8000`** in your browser.
Access from your phone at **`http://<your-local-IP>:8000`** on the same WiFi.

---

## Features

| | |
|---|---|
| 🧠 **Hardware-aware** | Detects GPU/CPU/RAM and recommends the best model for your machine |
| 📱 **Phone control** | Screenshot, volume, power, processes, notifications — all from your phone |
| 💬 **Streaming chat** | WebSocket streaming with markdown rendering |
| 📚 **Session history** | All conversations saved in a local SQLite database |
| 🐌 **AirLLM Slow Mode** | Run 70B+ models on 4GB VRAM via SSD layer offloading |
| 🔒 **Secure** | bcrypt auth, TLS, rate limiting, sandboxed tools |
| 🌐 **PWA** | Installable on Android/iOS, works offline |
| 🖥️ **Cross-platform** | Linux, macOS, Windows |

---

## CLI Reference

```bash
garudaai detect    # Show GPU, CPU, RAM, disk speed
garudaai suggest   # Get model recommendations for your hardware
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

Pull any model with:
```bash
ollama pull gemma2:2b
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
"Restart in 30 seconds"
```

---

## AirLLM — Big Models on Small GPUs

Run 70B parameter models on a 4GB GPU using layer-by-layer SSD offloading:

```bash
pip install garudaai[airllm]   # install extra deps
```

Select a `-airllm` model in the UI. Requires an SSD (≥400 MB/s). Responses take 1–3 min.

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
├── hardware.py           # Cross-platform GPU/CPU/RAM/disk detection
├── models.py             # Model database + recommendation engine
├── ollama_manager.py     # Ollama install, start, pull
├── airllm_backend.py     # AirLLM layer-offloading for big models
├── tools/
│   ├── filesystem.py     # Sandboxed file reader ($HOME only)
│   ├── shell.py          # Whitelisted shell (18 safe commands)
│   └── system_control.py # Remote laptop control
└── static/               # PWA frontend — vanilla JS, no build step
```

Config: `~/.config/garudaai/config.toml`
Sessions: `~/.local/share/garudaai/sessions.db`
Logs: `~/.local/share/garudaai/garudaai.log`

---

## License

MIT © [Sanyam Wadhwa](https://github.com/SanyamWadhwa07)
