"""System control tool for GarudaAI.

Allows the AI agent (and the user via their phone) to control the host machine:
  - Power: shutdown, restart, sleep, lock screen
  - Volume: get/set/mute
  - Screenshot: capture screen and save to disk
  - Processes: list running processes, kill by PID/name
  - Applications: open files and URLs with default programs
  - System info: CPU/RAM/GPU usage in real-time

Cross-platform: Linux, macOS, Windows.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_IS_WINDOWS = sys.platform == "win32"
_IS_MAC     = sys.platform == "darwin"
_IS_LINUX   = sys.platform.startswith("linux")


class SystemControlTool:
    """Safe system control operations accessible from the AI agent."""

    # Actions explicitly allowed (prevents the AI from doing things not in this list)
    ALLOWED_ACTIONS = {
        "screenshot", "processes", "kill_process",
        "volume_get", "volume_set", "volume_mute", "volume_unmute",
        "system_info", "open_file", "open_url",
        "lock_screen", "sleep", "shutdown", "restart",
        "notify",
    }

    def __init__(self, screenshot_dir: str = "~/Pictures/GarudaAI"):
        self.screenshot_dir = Path(screenshot_dir).expanduser()
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Dispatch an action and return a result dict."""
        if action not in self.ALLOWED_ACTIONS:
            return {"success": False, "error": f"Unknown action '{action}'. Allowed: {sorted(self.ALLOWED_ACTIONS)}"}

        handler = getattr(self, f"_do_{action}", None)
        if not handler:
            return {"success": False, "error": f"Action '{action}' not implemented on this platform"}

        try:
            return handler(**kwargs)
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------
    def _do_screenshot(self, filename: Optional[str] = None) -> Dict[str, Any]:
        """Capture the screen and save to disk."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        fname = filename or f"screenshot_{ts}.png"
        dest = self.screenshot_dir / fname

        if _IS_LINUX:
            # Try several tools in preference order
            for cmd in [
                ["scrot", str(dest)],
                ["gnome-screenshot", "-f", str(dest)],
                ["import", "-window", "root", str(dest)],  # ImageMagick
                ["spectacle", "-b", "-o", str(dest)],
            ]:
                try:
                    r = subprocess.run(cmd, capture_output=True, timeout=10)
                    if r.returncode == 0 and dest.exists():
                        return {"success": True, "path": str(dest)}
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
            return {"success": False, "error": "No screenshot tool found (install scrot or gnome-screenshot)"}

        elif _IS_MAC:
            r = subprocess.run(["screencapture", "-x", str(dest)], capture_output=True, timeout=10)
            return {"success": r.returncode == 0, "path": str(dest)} if r.returncode == 0 else \
                   {"success": False, "error": r.stderr.decode()}

        elif _IS_WINDOWS:
            # Use PowerShell + .NET
            script = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "Add-Type -AssemblyName System.Drawing;"
                "$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
                "$bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height);"
                "$g = [System.Drawing.Graphics]::FromImage($bmp);"
                "$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size);"
                f"$bmp.Save('{dest}');"
            )
            r = subprocess.run(["powershell", "-Command", script], capture_output=True, timeout=15)
            return {"success": dest.exists(), "path": str(dest)} if dest.exists() else \
                   {"success": False, "error": r.stderr.decode()}

        return {"success": False, "error": "Platform not supported"}

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------
    def _do_processes(self, limit: int = 20, sort_by: str = "cpu") -> Dict[str, Any]:
        """List top running processes."""
        try:
            import psutil
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
                try:
                    procs.append(p.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            procs.sort(key=lambda p: p.get(sort_by + "_percent", 0) or 0, reverse=True)
            return {"success": True, "processes": procs[:limit]}
        except ImportError:
            # Fallback: ps on Linux/Mac
            if not _IS_WINDOWS:
                r = subprocess.run(["ps", "aux", "--sort=-%cpu"], capture_output=True, text=True, timeout=5)
                lines = r.stdout.splitlines()[:limit + 1]
                return {"success": True, "output": "\n".join(lines)}
            return {"success": False, "error": "Install psutil: pip install psutil"}

    def _do_kill_process(self, pid: Optional[int] = None, name: Optional[str] = None) -> Dict[str, Any]:
        """Kill a process by PID or name."""
        if not pid and not name:
            return {"success": False, "error": "Provide pid or name"}
        try:
            import psutil
            killed = []
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    if (pid and p.pid == int(pid)) or (name and p.name().lower() == name.lower()):
                        p.terminate()
                        killed.append({"pid": p.pid, "name": p.name()})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return {"success": True, "killed": killed} if killed else {"success": False, "error": "No matching process"}
        except ImportError:
            if pid and not _IS_WINDOWS:
                r = subprocess.run(["kill", str(pid)], capture_output=True)
                return {"success": r.returncode == 0}
            return {"success": False, "error": "Install psutil: pip install psutil"}

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------
    def _do_volume_get(self) -> Dict[str, Any]:
        if _IS_LINUX:
            r = subprocess.run(["amixer", "get", "Master"], capture_output=True, text=True, timeout=3)
            import re
            m = re.search(r'\[(\d+)%\]', r.stdout)
            return {"success": True, "volume": int(m.group(1)) if m else None}
        elif _IS_MAC:
            r = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"],
                               capture_output=True, text=True, timeout=3)
            return {"success": True, "volume": int(r.stdout.strip()) if r.stdout.strip().isdigit() else None}
        elif _IS_WINDOWS:
            script = "(Get-AudioDevice -Playback).Volume"
            r = subprocess.run(["powershell", "-Command", script], capture_output=True, text=True, timeout=5)
            return {"success": True, "volume": r.stdout.strip()}
        return {"success": False, "error": "Platform not supported"}

    def _do_volume_set(self, level: int = 50) -> Dict[str, Any]:
        level = max(0, min(100, int(level)))
        if _IS_LINUX:
            r = subprocess.run(["amixer", "set", "Master", f"{level}%"], capture_output=True, timeout=3)
            return {"success": r.returncode == 0, "volume": level}
        elif _IS_MAC:
            r = subprocess.run(["osascript", "-e", f"set volume output volume {level}"],
                               capture_output=True, timeout=3)
            return {"success": r.returncode == 0, "volume": level}
        elif _IS_WINDOWS:
            script = f"(New-Object -ComObject WScript.Shell).SendKeys([char]0xAD); " \
                     f"$obj = new-object -com wscript.shell; $obj.SendKeys([char]0xAD)"
            # Simpler: use nircmd if available
            r = subprocess.run(["nircmd.exe", "setsysvolume", str(int(level * 655.35))],
                               capture_output=True, timeout=3)
            return {"success": r.returncode == 0, "volume": level}
        return {"success": False, "error": "Platform not supported"}

    def _do_volume_mute(self) -> Dict[str, Any]:
        if _IS_LINUX:
            r = subprocess.run(["amixer", "set", "Master", "mute"], capture_output=True, timeout=3)
            return {"success": r.returncode == 0}
        elif _IS_MAC:
            r = subprocess.run(["osascript", "-e", "set volume with output muted"], capture_output=True, timeout=3)
            return {"success": r.returncode == 0}
        elif _IS_WINDOWS:
            r = subprocess.run(["nircmd.exe", "mutesysvolume", "1"], capture_output=True, timeout=3)
            return {"success": r.returncode == 0}
        return {"success": False, "error": "Platform not supported"}

    def _do_volume_unmute(self) -> Dict[str, Any]:
        if _IS_LINUX:
            r = subprocess.run(["amixer", "set", "Master", "unmute"], capture_output=True, timeout=3)
            return {"success": r.returncode == 0}
        elif _IS_MAC:
            r = subprocess.run(["osascript", "-e", "set volume without output muted"], capture_output=True, timeout=3)
            return {"success": r.returncode == 0}
        elif _IS_WINDOWS:
            r = subprocess.run(["nircmd.exe", "mutesysvolume", "0"], capture_output=True, timeout=3)
            return {"success": r.returncode == 0}
        return {"success": False, "error": "Platform not supported"}

    # ------------------------------------------------------------------
    # System info
    # ------------------------------------------------------------------
    def _do_system_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {}
        try:
            import psutil
            info["cpu_percent"] = psutil.cpu_percent(interval=0.5)
            info["cpu_cores"] = psutil.cpu_count()
            mem = psutil.virtual_memory()
            info["ram_used_gb"] = round(mem.used / 1073741824, 2)
            info["ram_total_gb"] = round(mem.total / 1073741824, 2)
            info["ram_percent"] = mem.percent
            disk = psutil.disk_usage(str(Path.home()))
            info["disk_used_gb"] = round(disk.used / 1073741824, 2)
            info["disk_total_gb"] = round(disk.total / 1073741824, 2)
            info["disk_percent"] = disk.percent
        except ImportError:
            info["note"] = "Install psutil for detailed stats: pip install psutil"
        # GPU via nvidia-smi
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
            )
            if r.returncode == 0:
                parts = [p.strip() for p in r.stdout.strip().split(",")]
                if len(parts) >= 5:
                    info["gpu"] = {
                        "name": parts[0], "util_pct": parts[1],
                        "vram_used_mb": parts[2], "vram_total_mb": parts[3],
                        "temp_c": parts[4],
                    }
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return {"success": True, **info}

    # ------------------------------------------------------------------
    # Open file / URL
    # ------------------------------------------------------------------
    def _do_open_file(self, path: str) -> Dict[str, Any]:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if _IS_LINUX:
            subprocess.Popen(["xdg-open", str(resolved)])
        elif _IS_MAC:
            subprocess.Popen(["open", str(resolved)])
        elif _IS_WINDOWS:
            os.startfile(str(resolved))
        return {"success": True, "opened": str(resolved)}

    def _do_open_url(self, url: str) -> Dict[str, Any]:
        import webbrowser
        webbrowser.open(url)
        return {"success": True, "url": url}

    # ------------------------------------------------------------------
    # Power management
    # ------------------------------------------------------------------
    def _do_lock_screen(self) -> Dict[str, Any]:
        if _IS_LINUX:
            for cmd in [["loginctl", "lock-session"], ["xdg-screensaver", "lock"],
                        ["gnome-screensaver-command", "-l"], ["xscreensaver-command", "-lock"]]:
                try:
                    r = subprocess.run(cmd, capture_output=True, timeout=5)
                    if r.returncode == 0:
                        return {"success": True}
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
            return {"success": False, "error": "No screen locker found"}
        elif _IS_MAC:
            r = subprocess.run(["pmset", "displaysleepnow"], capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        elif _IS_WINDOWS:
            r = subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        return {"success": False, "error": "Platform not supported"}

    def _do_sleep(self) -> Dict[str, Any]:
        if _IS_LINUX:
            r = subprocess.run(["systemctl", "suspend"], capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        elif _IS_MAC:
            r = subprocess.run(["pmset", "sleepnow"], capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        elif _IS_WINDOWS:
            r = subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"],
                               capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        return {"success": False, "error": "Platform not supported"}

    def _do_shutdown(self, delay_seconds: int = 0) -> Dict[str, Any]:
        if _IS_LINUX or _IS_MAC:
            cmd = ["shutdown", "-h", f"+{delay_seconds // 60}" if delay_seconds else "now"]
            r = subprocess.run(cmd, capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        elif _IS_WINDOWS:
            cmd = ["shutdown", "/s", "/t", str(delay_seconds)]
            r = subprocess.run(cmd, capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        return {"success": False, "error": "Platform not supported"}

    def _do_restart(self, delay_seconds: int = 0) -> Dict[str, Any]:
        if _IS_LINUX or _IS_MAC:
            cmd = ["shutdown", "-r", f"+{delay_seconds // 60}" if delay_seconds else "now"]
            r = subprocess.run(cmd, capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        elif _IS_WINDOWS:
            cmd = ["shutdown", "/r", "/t", str(delay_seconds)]
            r = subprocess.run(cmd, capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        return {"success": False, "error": "Platform not supported"}

    # ------------------------------------------------------------------
    # Desktop notification
    # ------------------------------------------------------------------
    def _do_notify(self, title: str = "GarudaAI", message: str = "") -> Dict[str, Any]:
        if _IS_LINUX:
            r = subprocess.run(["notify-send", title, message], capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        elif _IS_MAC:
            script = f'display notification "{message}" with title "{title}"'
            r = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            return {"success": r.returncode == 0}
        elif _IS_WINDOWS:
            # PowerShell toast notification
            script = (
                f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                f"ContentType = WindowsRuntime] | Out-Null;"
                f"$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
                f"[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
                f"$t.GetElementsByTagName('text')[0].AppendChild($t.CreateTextNode('{title}')) | Out-Null;"
                f"$t.GetElementsByTagName('text')[1].AppendChild($t.CreateTextNode('{message}')) | Out-Null;"
                f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('GarudaAI')"
                f".Show([Windows.UI.Notifications.ToastNotification]::new($t));"
            )
            r = subprocess.run(["powershell", "-Command", script], capture_output=True, timeout=8)
            return {"success": r.returncode == 0}
        return {"success": False, "error": "Platform not supported"}
