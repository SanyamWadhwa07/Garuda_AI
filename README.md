# GarudaAI

A self-hosted, hardware-aware, phone-controlled local AI agent platform.

Run powerful AI models entirely on your own hardware. Control your laptop from your phone. No cloud, no data leaks, no subscriptions.

## Features

- **Hardware-aware** — detects your GPU, CPU, and RAM; recommends the best model for your machine
- **Streaming chat** — WebSocket-based streaming with markdown rendering (via marked.js + DOMPurify)
- **Session history** — all conversations stored in a local SQLite database
- **Phone control** — control your laptop remotely via the AI: screenshots, volume, power, processes, notifications
- **Remote system management** — ask the AI to check CPU/GPU usage, kill a process, lock the screen, or open a file
- **AirLLM support** — run 70B+ models on 4GB VRAM via layer-by-layer SSD offloading (slow mode)
- **Secure by default** — bcrypt authentication, TLS, rate limiting, sandboxed filesystem and shell tools
- **PWA** — installable on Android/iOS; works offline via service worker
- **Cross-platform** — Linux, macOS, Windows

## Quick Start

```bash
pip install garudaai
garudaai setup       # First-time setup: detects hardware, sets password, configures Ollama
garudaai serve       # Start the server at https://localhost:8000
```

Open `https://localhost:8000` in your browser (or on your phone via your local IP).

## CLI Commands

| Command | Description |
|---|---|
| `garudaai detect` | Detect GPU, CPU, RAM, disk speed |
| `garudaai suggest` | Get model recommendations for your hardware |
| `garudaai setup` | Interactive first-time setup wizard |
| `garudaai serve` | Start the FastAPI server |
| `garudaai status` | Check Ollama status and current config |

## Agent Tools

The AI can invoke tools on your behalf:

| Tool | What it does |
|---|---|
| `filesystem_read` | Read files (sandboxed to `$HOME`) |
| `shell` | Run whitelisted commands (ls, grep, cat, find, etc.) |
| `system_control` | Control the host machine — see below |

### System Control Actions

Control your laptop from your phone by asking the AI:

| Action | Example prompt |
|---|---|
| `screenshot` | "Take a screenshot of my screen" |
| `system_info` | "What's my CPU and GPU usage right now?" |
| `processes` | "Show me the top 10 processes by CPU" |
| `kill_process` | "Kill the process named chrome" |
| `volume_set` | "Set volume to 40%" |
| `volume_mute` / `volume_unmute` | "Mute my laptop" |
| `notify` | "Send me a desktop notification when done" |
| `lock_screen` | "Lock my screen" |
| `sleep` | "Put the laptop to sleep" |
| `open_url` | "Open YouTube in my browser" |
| `open_file` | "Open my resume PDF" |
| `shutdown` / `restart` | "Restart in 30 seconds" |

## Model Support

GarudaAI recommends models based on your available VRAM:

| VRAM | Recommended models |
|---|---|
| 2–4 GB | gemma2:2b, phi3.5:3.8b, qwen2.5:3b |
| 4–8 GB | mistral:7b, qwen2.5:7b, deepseek-coder-v2:7b |
| 8–16 GB | llama3.1:8b, gemma2:9b, mistral-nemo:12b, qwen2.5:14b |
| 16+ GB | llama3.3:70b, qwen2.5:32b |
| Any (SSD + 4GB) | 70B models via AirLLM Slow Mode (1–3 min/reply) |

### AirLLM Slow Mode

Run 70B models on a 4GB GPU using layer-by-layer SSD offloading:

```bash
pip install garudaai[airllm]
```

Select a `-airllm` model in the UI. Responses take 1–3 minutes. Requires an SSD (≥400 MB/s).

## Security

- Passwords hashed with bcrypt (not SHA-256)
- All routes protected with `Authorization: Bearer` token auth (24h TTL)
- TLS certificate auto-generated on first run (no openssl CLI needed)
- Filesystem tool sandboxed to `$HOME` with symlink escape prevention
- Shell tool allows only 18 whitelisted commands with a 30s timeout and 10KB output cap
- Rate limiting via slowapi (200 req/min global default)

## Development

```bash
git clone https://github.com/garudaai/garudaai
cd garudaai
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run a single test
pytest tests/test_agent.py::test_parse_tool_calls_basic

# Format / lint
black src/
ruff check src/
```

## Project Structure

```
src/
├── agent.py              # FastAPI app, WebSocket streaming, auth, session management
├── cli.py                # Click CLI (setup, serve, detect, suggest, status)
├── hardware.py           # Cross-platform GPU/CPU/RAM/disk detection
├── models.py             # Model database and recommendation engine
├── ollama_manager.py     # Ollama install, start, pull, lifecycle
├── airllm_backend.py     # AirLLM layer-offloading backend for big models
├── tools/
│   ├── filesystem.py     # Sandboxed file reader
│   ├── shell.py          # Whitelisted shell executor
│   └── system_control.py # Remote laptop control (screenshot, volume, power, etc.)
└── static/               # PWA frontend (vanilla JS, no build step)
    ├── index.html
    ├── script.js
    ├── style.css
    ├── sw.js             # Service worker (offline support)
    ├── marked.min.js     # Markdown renderer (vendored)
    └── purify.min.js     # XSS sanitizer (vendored)
```

Configuration is stored at `~/.config/garudaai/config.toml`. Sessions are in `~/.local/share/garudaai/sessions.db`.

## License

MIT
