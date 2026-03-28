# GarudaAI Installer — Windows (PowerShell)
# Usage: irm https://raw.githubusercontent.com/SanyamWadhwa07/Garuda_AI/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$REPO    = "https://github.com/SanyamWadhwa07/Garuda_AI"
$PACKAGE = "git+https://github.com/SanyamWadhwa07/Garuda_AI.git"

function Write-Step   { param($msg) Write-Host "  -> $msg" -ForegroundColor Cyan }
function Write-Ok     { param($msg) Write-Host "  OK $msg" -ForegroundColor Green }
function Write-Warn   { param($msg) Write-Host "  !! $msg" -ForegroundColor Yellow }
function Write-Fail   { param($msg) Write-Host "  X  $msg" -ForegroundColor Red; exit 1 }
function Write-Header { param($msg) Write-Host "`n$msg" -ForegroundColor White }

# ── Banner ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ╔═══════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "  ║       GarudaAI Installer          ║" -ForegroundColor Magenta
Write-Host "  ║   Self-hosted local AI platform   ║" -ForegroundColor Magenta
Write-Host "  ╚═══════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

# ── Python check ─────────────────────────────────────────────────────────────
Write-Header "Checking Python..."

$python = $null
foreach ($cmd in @("python", "python3", "python3.12", "python3.11", "python3.10")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver) {
            $parts = $ver.Split(".")
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                $python = $cmd
                Write-Ok "Found $cmd $ver"
                break
            }
        }
    } catch {}
}

if (-not $python) {
    Write-Fail "Python 3.10+ not found.`n  Download from: https://python.org/downloads`n  Make sure to check 'Add Python to PATH' during install."
}

# ── pip ───────────────────────────────────────────────────────────────────────
try {
    & $python -m pip --version | Out-Null
    Write-Ok "pip available"
} catch {
    Write-Step "Bootstrapping pip..."
    & $python -m ensurepip --upgrade
}

# ── Install GarudaAI ─────────────────────────────────────────────────────────
Write-Header "Installing GarudaAI..."
Write-Step "Installing from GitHub..."

& $python -m pip install --quiet --upgrade $PACKAGE
if ($LASTEXITCODE -ne 0) { Write-Fail "pip install failed" }
Write-Ok "GarudaAI installed"

# ── Add Scripts to PATH ───────────────────────────────────────────────────────
Write-Header "Configuring PATH..."

$userBase  = & $python -m site --user-base
$scriptsDir = Join-Path $userBase "Scripts"

$currentPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*$scriptsDir*") {
    [System.Environment]::SetEnvironmentVariable("PATH", "$currentPath;$scriptsDir", "User")
    $env:PATH = "$env:PATH;$scriptsDir"
    Write-Ok "Added $scriptsDir to PATH"
} else {
    Write-Ok "PATH already configured"
}

# ── Ollama ───────────────────────────────────────────────────────────────────
Write-Header "Checking Ollama..."

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Ok "Ollama already installed"
} else {
    Write-Step "Downloading OllamaSetup.exe..."
    $installer = Join-Path $env:TEMP "OllamaSetup.exe"
    Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile $installer
    Write-Step "Running installer (silent)..."
    Start-Process $installer -ArgumentList "/VERYSILENT", "/NORESTART" -Wait
    Remove-Item $installer -ErrorAction SilentlyContinue
    Write-Ok "Ollama installed"
}

# ── Firewall ─────────────────────────────────────────────────────────────────
Write-Header "Configuring firewall..."
try {
    $rule = Get-NetFirewallRule -DisplayName "GarudaAI Port 8000" -ErrorAction SilentlyContinue
    if (-not $rule) {
        New-NetFirewallRule -DisplayName "GarudaAI Port 8000" `
            -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow | Out-Null
        Write-Ok "Firewall rule added (port 8000)"
    } else {
        Write-Ok "Firewall rule already exists"
    }
} catch {
    Write-Warn "Could not add firewall rule (run as admin to enable phone access)"
}

# ── Done ─────────────────────────────────────────────────────────────────────
$localIP = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.InterfaceAlias -like "*Wi-Fi*" -or $_.InterfaceAlias -like "*Ethernet*" } |
    Where-Object { $_.IPAddress -notlike "169.*" } |
    Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Run setup:"
Write-Host "    garudaai setup" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Then start:"
Write-Host "    garudaai serve" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Browser: http://localhost:8000" -ForegroundColor Cyan
if ($localIP) {
Write-Host "  Phone:   http://${localIP}:8000  (same WiFi)" -ForegroundColor Cyan
}
Write-Host "  Source:  $REPO" -ForegroundColor Cyan
Write-Host ""
