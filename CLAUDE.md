# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GarudaAI is a local AI agent platform for Garuda Linux. It detects user hardware, recommends appropriate local LLM models, manages Ollama, and serves a streaming chat PWA frontend via FastAPI. No build step is required — the frontend is vanilla JS and the backend is pure Python.

## Commands

### Development Setup
```bash
pip install -e ".[dev]"
```

### Run the App
```bash
garudaai detect          # Detect GPU/CPU/RAM
garudaai suggest         # Get model recommendations
garudaai setup           # Interactive first-time setup (required before serve)
garudaai serve           # Start FastAPI server on localhost:8000
garudaai status          # Check Ollama status and config
```

### Testing
```bash
pytest tests/                          # Run all tests
pytest tests/test_hardware.py          # Run a single test file
pytest tests/test_shell.py::TestShellTool::test_whitelist  # Run a single test
```

### Code Quality
```bash
black src/       # Format (100 char line length)
ruff check src/  # Lint
```

## Architecture

### Request Flow
Browser (PWA) → HTTPS WebSocket `/ws` → FastAPI Agent (`src/agent.py`) → Ollama HTTP API (port 11434)

The frontend at `src/static/` is served as static files by FastAPI — no separate frontend server.

### Key Modules

- **`src/agent.py`** — FastAPI app + WebSocket chat endpoint. Contains `SessionManager` (SQLite at `~/.local/share/garudaai/sessions.db`) and `Agent` class which streams tokens from Ollama, parses tool calls (`[tool: name, arg1]` syntax), and routes to tool handlers.

- **`src/cli.py`** — Click CLI with 6 commands. The `setup` wizard writes config to `~/.config/garudaai/config.toml` (see `config/config.toml.example` for schema).

- **`src/hardware.py`** — Detects GPU vendor (nvidia-smi / rocm-smi / lspci), VRAM, CPU cores, RAM, disk speed. Results are cached 24h at `~/.cache/garudaai/hardware.json`.

- **`src/models.py`** — Hardcoded database of 8 curated models with VRAM requirements. `ModelSuggester.suggest()` filters by available VRAM, then by use case, then ranks by capability.

- **`src/ollama_manager.py`** — Manages Ollama lifecycle: install from GitHub releases, start server, pull models, query `/api/tags` and `/api/show`.

- **`src/tools/filesystem.py`** — Read-only, sandboxed to `$HOME`. `_validate_path()` prevents path traversal and symlink escapes.

- **`src/tools/shell.py`** — Whitelisted commands only (18 safe defaults: ls, find, grep, cat, etc.). 30-second timeout, 10KB output cap.

### Configuration
- User config: `~/.config/garudaai/config.toml`
- Sessions DB: `~/.local/share/garudaai/sessions.db`
- Hardware cache: `~/.cache/garudaai/hardware.json`
- TLS cert: `~/.local/share/garudaai/`

### Tool Invocation Protocol
The `Agent` class detects tool requests in user messages via `_is_tool_request()` and parses `[tool: name, arg1, arg2]` patterns from model output via `parse_tool_calls()`. Tool results are injected back into the conversation context before streaming continues.

### Frontend
Vanilla JS/HTML/CSS — no build step, no npm. PWA with service worker for offline support. Connects via WebSocket and renders streaming tokens as they arrive. Session ID is stored in localStorage.
