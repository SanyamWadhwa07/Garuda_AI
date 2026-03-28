#!/usr/bin/env sh
# GarudaAI Installer — Linux & macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/SanyamWadhwa07/Garuda_AI/main/install.sh | sh

set -e

REPO="https://github.com/SanyamWadhwa07/Garuda_AI"
PACKAGE="git+https://github.com/SanyamWadhwa07/Garuda_AI.git"
MIN_PYTHON="3.10"

# ── Colors ──────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; RESET=''
fi

info()    { printf "${BLUE}  →${RESET} %s\n" "$1"; }
success() { printf "${GREEN}  ✓${RESET} %s\n" "$1"; }
warn()    { printf "${YELLOW}  ⚠${RESET} %s\n" "$1"; }
error()   { printf "${RED}  ✗${RESET} %s\n" "$1"; exit 1; }
header()  { printf "\n${BOLD}%s${RESET}\n" "$1"; }

# ── Banner ───────────────────────────────────────────────────────────────────
printf "\n${BOLD}"
printf "  ╔═══════════════════════════════════╗\n"
printf "  ║       🦅  GarudaAI Installer       ║\n"
printf "  ║   Self-hosted local AI platform   ║\n"
printf "  ╚═══════════════════════════════════╝\n"
printf "${RESET}\n"

# ── OS Detection ────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
    Linux*)  PLATFORM="linux" ;;
    Darwin*) PLATFORM="macos" ;;
    *)       error "Unsupported OS: $OS. Use install.ps1 on Windows." ;;
esac
success "Platform: $OS"

# ── Python check ────────────────────────────────────────────────────────────
header "Checking Python..."

PYTHON=""
for cmd in python3 python python3.13 python3.12 python3.11 python3.10; do
    if command -v "$cmd" >/dev/null 2>&1; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            success "Found $cmd $ver"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    error "Python $MIN_PYTHON+ not found. Install it first:
    • Ubuntu/Debian: sudo apt install python3.11
    • Arch/Garuda:   sudo pacman -S python
    • macOS:         brew install python@3.11
    • Or: https://python.org/downloads"
fi

# ── pip check ───────────────────────────────────────────────────────────────
if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
    info "Installing pip..."
    "$PYTHON" -m ensurepip --upgrade 2>/dev/null || \
        curl -fsSL https://bootstrap.pypa.io/get-pip.py | "$PYTHON"
fi
success "pip available"

# ── Install GarudaAI ────────────────────────────────────────────────────────
header "Installing GarudaAI..."

info "Installing from GitHub..."
"$PYTHON" -m pip install --quiet --upgrade "$PACKAGE"

# Verify
if ! command -v garudaai >/dev/null 2>&1; then
    # Try adding user bin to PATH
    USER_BIN="$($PYTHON -m site --user-base)/bin"
    export PATH="$PATH:$USER_BIN"

    if ! command -v garudaai >/dev/null 2>&1; then
        warn "garudaai not in PATH. Adding $USER_BIN to your shell config..."

        SHELL_RC=""
        case "$SHELL" in
            */bash) SHELL_RC="$HOME/.bashrc" ;;
            */zsh)  SHELL_RC="$HOME/.zshrc" ;;
            */fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
        esac

        if [ -n "$SHELL_RC" ]; then
            echo "export PATH=\"\$PATH:$USER_BIN\"" >> "$SHELL_RC"
            success "Added $USER_BIN to $SHELL_RC (restart terminal or run: source $SHELL_RC)"
        else
            warn "Add this to your shell config: export PATH=\"\$PATH:$USER_BIN\""
        fi
    fi
fi
success "GarudaAI installed"

# ── Ollama ───────────────────────────────────────────────────────────────────
header "Checking Ollama..."

if command -v ollama >/dev/null 2>&1; then
    success "Ollama already installed ($(ollama --version 2>/dev/null | head -1))"
else
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    success "Ollama installed"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
printf "\n${GREEN}${BOLD}  Installation complete!${RESET}\n\n"
printf "  Run setup now:\n"
printf "${BOLD}    garudaai setup${RESET}\n\n"
printf "  Then start the server:\n"
printf "${BOLD}    garudaai serve${RESET}\n\n"
printf "  Open in browser:  ${BLUE}http://localhost:8000${RESET}\n"
printf "  From your phone:  ${BLUE}http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'YOUR_IP'):8000${RESET}\n\n"
printf "  Docs & source:    ${BLUE}$REPO${RESET}\n\n"
