# GarudaAI Quick Start

Welcome to **GarudaAI** — a self-hosted, hardware-aware, phone-controlled local AI agent platform!

## 🚀 Quick Start (5 minutes)

### 1. Install Dependencies

```bash
cd ~/GarudaAI  # Or wherever you cloned the repo

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install GarudaAI
pip install -e .
```

### 2. Detect Your Hardware

```bash
garudaai detect
```

Output will show your GPU (if any), VRAM, CPU cores, and RAM.

### 3. Get Model Recommendations

```bash
garudaai suggest
```

Get smart recommendations based on your hardware.

### 4. Run Setup (Interactive)

```bash
garudaai setup
```

This will:
- Detect your hardware ✅
- Recommend a model ✅
- Download and install Ollama ✅
- Start Ollama server ✅
- Pull a recommended model ✅
- Set your password ✅
- Save configuration ✅

### 5. Start the Server

```bash
garudaai serve
```

Open your browser to:
- **Local machine**: `https://localhost:8000`
- **From phone/network**: `https://garudaai.local:8000` (if Avahi installed)

### 6. Start Chatting!

Select a model, type a message, and press Enter. Responses stream in real-time!

---

## 📱 Using from Your Phone

1. Connect your phone to the **same WiFi network** as your computer
2. Open a browser on your phone
3. Navigate to: `https://garudaai.local:8000`
4. Enter your password (set during setup)
5. Start chatting!

**Features on phone**:
- 💬 Real-time streaming responses
- 🎤 Voice input (tap microphone button)
- 📁 File browser (read-only, Phase 1)
- 📝 Session history
- ⚙️ Settings and preferences

---

## 🛠️ Useful Commands

### Check Status
```bash
garudaai status
```

### View Logs
```bash
garudaai logs -n 50
```

### Detect Hardware (Force Refresh)
```bash
garudaai detect --json
```

### Get Model Info
```bash
garudaai suggest --use-case coding
```

Available use cases: `chat`, `coding`, `reasoning`, `vision`

---

## 🔧 Advanced: Manual Model Selection

List all available models:
```bash
ollama list
```

Pull a specific model:
```bash
ollama pull mistral:7b
```

Then in the PWA, select it from the dropdown.

---

## ⚠️ First Run Notes

- **HTTPS**: Self-signed certificate is generated automatically. Your browser will warn you—it's safe to ignore (it's your local machine).
- **Password**: Set during `garudaai setup`. If you forgot it, re-run setup.
- **mDNS (garudaai.local)**: Requires Avahi. Install with: `sudo pacman -S avahi`
- **Performance**: First chat response may be slow (model is loading). Subsequent responses are fast.

---

## 📚 Architecture Overview

```
┌──────────────────────┐
│     Your Phone       │
│   (PWA in browser)   │
└──────────┬───────────┘
           │ HTTPS
           ▼
┌──────────────────────────┐
│   FastAPI Backend        │
│  (localhost:8000)        │
│  - WebSocket streaming   │
│  - Session management    │
│  - Tool access           │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│   Ollama (localhost:     │
│   11434)                 │
│  - Model inference       │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│   Your System            │
│  - Files (read-only)     │
│  - Safe commands         │
└──────────────────────────┘
```

---

## 🐛 Troubleshooting

### "Can't connect to Ollama"
```bash
# Start Ollama manually
ollama serve

# In another terminal, check if it's running
curl http://localhost:11434/api/tags
```

### "Model not loading"
```bash
# Pull the model manually
ollama pull neural-chat:7b

# Check what's available
ollama list
```

### "Can't access garudaai.local"
Install Avahi:
```bash
sudo pacman -S avahi
systemctl --user restart avahi-daemon.service
```

Or just use `https://localhost:8000`

### "Password doesn't work"
Re-run setup to reset:
```bash
garudaai setup
```

---

## 📖 Documentation

- **[Development Guide](DEVELOPMENT.md)** - For developers
- **[Architecture](ARCHITECTURE.md)** - Coming in Phase 2
- **[API Reference](API.md)** - Coming in Phase 2

---

## 💡 Next Steps

### Phase 1 (Now ✅)
- ✅ Hardware detection
- ✅ Model recommendation
- ✅ Streaming chat
- ✅ PWA interface
- ✅ Read-only file browser
- ✅ CLI tools

### Phase 2 (Soon)
- 🔨 Write files / execute commands
- 🔨 Advanced filesystem access
- 🔨 Web search integration
- 🔨 Improved error handling

### Phase 3
- 🔜 Vision models (llava)
- 🔜 Advanced search
- 🔜 Image generation

### Phase 4+
- 🔜 Plugin system
- 🔜 Multi-user support
- 🔜 Cloud sync
- 🔜 Analytics dashboard

---

## 🤝 Contributing

Have ideas? Found a bug? Want to help?

1. Check [GitHub Issues](https://github.com/garudaai/garudaai/issues)
2. Join our [discussions](https://github.com/garudaai/garudaai/discussions)
3. Submit a PR!

---

## 📄 License

MIT License - See [LICENSE](LICENSE)

---

**Happy chatting!** 🦅

Questions? Open an issue on GitHub or check the [Development Guide](DEVELOPMENT.md).
