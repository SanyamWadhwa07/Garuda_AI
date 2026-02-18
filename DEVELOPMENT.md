# Development Guide

## Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/garudaai/garudaai.git
cd garudaai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

## Running GarudaAI

### Setup Phase (first run)
```bash
garudaai detect        # Check hardware
garudaai suggest       # Get model recommendations
garudaai setup         # Interactive setup
```

### Run the server
```bash
garudaai serve        # Start GarudaAI server
```

Then open your browser to: `https://garudaai.local:8000` or `https://localhost:8000`

## Testing

```bash
pytest tests/
```

## Code Style

We use Black and Ruff for code formatting and linting:

```bash
black src/
ruff check src/
```

## Project Structure

- **src/**: Main Python package
  - `hardware.py`: Hardware detection module
  - `models.py`: Model recommendation engine
  - `ollama_manager.py`: Ollama lifecycle management
  - `agent.py`: FastAPI backend with streaming
  - `cli.py`: Command-line interface
  - `tools/`: Agent tools (filesystem, shell)
  - `static/`: PWA frontend files

- **systemd/**: Systemd service files for daemon mode

- **config/**: Configuration templates

- **tests/**: Test suite

## Key Features (Phase 1)

✅ Hardware detection (GPU VRAM, CPU cores, RAM, disk speed)
✅ Model recommendation engine with Ollama integration
✅ PWA frontend with chat interface
✅ Streaming responses via WebSocket
✅ Session management with SQLite
✅ Audit logging
✅ Voice input support (Web Speech API)
✅ File browser widget (read-only)
✅ CLI tools for setup and management
✅ Self-signed HTTPS certificates
✅ mDNS discovery (garudaai.local)

## Future Phases

**Phase 2**: Complete tool integration (write files, execute commands)
**Phase 3**: Vision models (llava), advanced search
**Phase 4**: Plugin system, user management, advanced analytics
**Phase 5**: Cloud sync, multi-user deployment

## Troubleshooting

### Ollama not starting
```bash
# Check if Ollama is installed
which ollama

# Run Ollama directly to see errors
ollama serve
```

### Models not loading
```bash
# List available models
ollama list

# Pull a model manually
ollama pull neural-chat:7b
```

### Frontend not loading
```bash
# Check if FastAPI is running
curl http://localhost:8000

# Check logs
journalctl --user -u garudaai
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

GarudaAI is released under the MIT License. See [LICENSE](LICENSE) for details.
