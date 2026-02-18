# GarudaAI

A self-hosted, hardware-aware, phone-controlled local AI agent platform for Garuda Linux.

## Vision

GarudaAI brings intelligent AI computation to your laptop—locally, safely, and intelligently.

- **Hardware-aware**: Automatically detects your GPU, CPU, RAM, and recommends appropriate models
- **Easy setup**: `yay -S garudaai` and you're done
- **Phone-friendly**: PWA interface accessible at `garudaai.local` with chat, file browser, and voice input
- **Auditable**: Every action logged, nothing happens silently
- **Extensible**: Plugin architecture for custom tools and models

## Project Structure

```
GarudaAI/
├── src/                          # Main Python package
│   ├── __init__.py
│   ├── __main__.py              # CLI entry point
│   ├── hardware.py              # Hardware detection
│   ├── models.py                # Model recommendation engine
│   ├── ollama_manager.py        # Ollama lifecycle management
│   ├── agent.py                 # FastAPI backend
│   ├── cli.py                   # CLI commands
│   ├── tools/                   # Agent tools
│   │   ├── __init__.py
│   │   ├── filesystem.py        # File operations
│   │   └── shell.py             # Safe shell execution
│   └── static/                  # PWA served by FastAPI
├── frontend/                    # PWA source
│   ├── index.html
│   ├── script.js
│   ├── style.css
│   └── sw.js                    # Service worker
├── config/                      # Configuration templates
│   └── config.toml.example
├── systemd/                     # Systemd service files
│   └── garudaai.service
├── scripts/                     # Utility scripts
├── PKGBUILD                     # AUR package definition
└── README.md
```

## Installation (Future)

```bash
yay -S garudaai
garudaai setup
```

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for setup instructions.
