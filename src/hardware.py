"""Hardware detection module for GarudaAI.

Detects GPU, CPU, RAM, and disk capabilities to inform model selection.
Cross-platform: Linux, macOS, Windows.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

_IS_WINDOWS = sys.platform == "win32"


class HardwareDetector:
    """Detect and report system hardware capabilities."""

    def __init__(self, cache_dir: str = "~/.cache/garudaai", cache_ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "hardware.json"
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    def detect(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Detect hardware and return capabilities."""
        if not force_refresh and self.cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(self.cache_file.stat().st_mtime)
            if cache_age < self.cache_ttl:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)

        result = {
            "timestamp": datetime.now().isoformat(),
            "gpu_vendor": self._detect_gpu_vendor(),
            "vram_mb": self._detect_vram(),
            "cpu_cores": self._detect_cpu_cores(),
            "ram_mb": self._detect_system_ram(),
            "disk_speed_mbps": self._detect_disk_speed(),
            "compute_ok": False,
        }
        result["compute_ok"] = self._test_compute()

        with open(self.cache_file, 'w') as f:
            json.dump(result, f, indent=2)

        return result

    def _detect_gpu_vendor(self) -> Optional[str]:
        """Detect GPU vendor (nvidia, amd, intel, or None)."""
        # NVIDIA — nvidia-smi works on both Linux and Windows
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, check=False, timeout=3)
            return "nvidia"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        if _IS_WINDOWS:
            return self._detect_gpu_vendor_windows()

        # AMD (ROCm) — Linux only
        try:
            subprocess.run(["rocm-smi"], capture_output=True, check=False, timeout=2)
            return "amd"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Intel Arc — Linux
        try:
            result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                output_upper = result.stdout.upper()
                if "INTEL" in output_upper and ("GPU" in output_upper or "ARC" in output_upper or "VGA" in output_upper):
                    return "intel"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    def _detect_gpu_vendor_windows(self) -> Optional[str]:
        """Detect GPU vendor on Windows via wmic."""
        try:
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                output = result.stdout.upper()
                if "NVIDIA" in output:
                    return "nvidia"
                if "AMD" in output or "RADEON" in output:
                    return "amd"
                if "INTEL" in output:
                    return "intel"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # PowerShell fallback
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=8,
            )
            if result.returncode == 0:
                output = result.stdout.upper()
                if "NVIDIA" in output:
                    return "nvidia"
                if "AMD" in output or "RADEON" in output:
                    return "amd"
                if "INTEL" in output:
                    return "intel"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    def _detect_vram(self) -> int:
        """Detect GPU VRAM in MB. Returns 0 if no GPU detected."""
        # NVIDIA — works on Linux and Windows
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,nounits,noheader"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                return int(result.stdout.strip().split('\n')[0])
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass

        if _IS_WINDOWS:
            return self._detect_vram_windows()

        # AMD (rocm-smi) — Linux only
        try:
            result = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                if "MI100" in result.stdout or "MI200" in result.stdout:
                    return 32768
                elif "MI50" in result.stdout or "MI60" in result.stdout:
                    return 16384
                else:
                    return 8192
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return 0

    def _detect_vram_windows(self) -> int:
        """Detect VRAM on Windows via wmic AdapterRAM."""
        try:
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "AdapterRAM"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line and line.isdigit():
                        return int(line) // (1024 * 1024)  # bytes → MB
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass
        return 0

    def _detect_cpu_cores(self) -> int:
        """Detect number of CPU cores (cross-platform)."""
        cores = os.cpu_count()
        return cores if cores else 4

    def _detect_system_ram(self) -> int:
        """Detect total system RAM in MB (cross-platform)."""
        if _IS_WINDOWS:
            return self._detect_ram_windows()

        # Linux: /proc/meminfo (value is in kB)
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb // 1024
        except (FileNotFoundError, IOError, IndexError):
            pass

        # macOS / Linux fallback
        try:
            result = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                return int(lines[1].split()[1])
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
            pass

        return 8192

    def _detect_ram_windows(self) -> int:
        """Detect RAM on Windows via ctypes GlobalMemoryStatusEx."""
        try:
            import ctypes
            import ctypes.wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullTotalPhys) // (1024 * 1024)
        except Exception:
            pass

        # wmic fallback
        try:
            result = subprocess.run(
                ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line and line.isdigit():
                        return int(line) // (1024 * 1024)
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass

        return 8192

    def _detect_disk_speed(self) -> float:
        """Estimate sequential write speed in MB/s."""
        if _IS_WINDOWS:
            return self._detect_disk_speed_python()

        # Linux: dd benchmark
        try:
            result = subprocess.run(
                ["dd", "if=/dev/zero", "of=/tmp/garudaai_bench.img", "bs=1M", "count=100"],
                capture_output=True, text=True, timeout=15,
            )
            try:
                os.remove("/tmp/garudaai_bench.img")
            except FileNotFoundError:
                pass
            output = result.stdout + result.stderr
            for line in output.split('\n'):
                if "MB/s" in line:
                    parts = line.split()
                    try:
                        return float(parts[-2])
                    except (ValueError, IndexError):
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return self._detect_disk_speed_python()

    def _detect_disk_speed_python(self) -> float:
        """Pure-Python disk speed benchmark: write 64MB to a temp file."""
        try:
            chunk = b'\x00' * (1024 * 1024)  # 1 MB chunk
            total_mb = 64
            tmp = tempfile.NamedTemporaryFile(delete=False)
            tmp_path = tmp.name
            tmp.close()

            start = time.monotonic()
            with open(tmp_path, 'wb') as f:
                for _ in range(total_mb):
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
            elapsed = time.monotonic() - start

            try:
                os.remove(tmp_path)
            except OSError:
                pass

            if elapsed > 0:
                return round(total_mb / elapsed, 1)
        except Exception:
            pass
        return 100.0

    def _test_compute(self) -> bool:
        """Test if GPU compute is actually working."""
        try:
            gpu_vendor = self._detect_gpu_vendor()
            if gpu_vendor == "nvidia":
                result = subprocess.run(["nvidia-smi"], capture_output=True, timeout=3)
                return result.returncode == 0
            elif gpu_vendor == "amd" and not _IS_WINDOWS:
                result = subprocess.run(["rocm-smi"], capture_output=True, timeout=2)
                return result.returncode == 0
            else:
                return True  # CPU always available
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False


def detect_hardware(force_refresh: bool = False) -> Dict[str, Any]:
    """Convenience function to detect hardware."""
    detector = HardwareDetector()
    return detector.detect(force_refresh=force_refresh)


def is_airllm_eligible(hw: Dict[str, Any]) -> Dict[str, Any]:
    """Check if hardware is eligible to run AirLLM (layer-offloaded big models).

    Requirements: SSD with >=400 MB/s + GPU with >=4GB VRAM.
    """
    disk_ok = hw.get("disk_speed_mbps", 0) >= 400
    vram_ok = hw.get("vram_mb", 0) >= 4096

    if not disk_ok:
        reason = f"Disk too slow ({hw.get('disk_speed_mbps', 0):.0f} MB/s; need ≥400 MB/s SSD)"
    elif not vram_ok:
        reason = f"GPU VRAM too low ({hw.get('vram_mb', 0)} MB; need ≥4096 MB)"
    else:
        reason = "Eligible"

    disk_mbps = hw.get("disk_speed_mbps", 0)
    estimated_tps = max(0.3, disk_mbps / 2000) if disk_ok and vram_ok else 0.0

    return {
        "eligible": disk_ok and vram_ok,
        "reason": reason,
        "estimated_tokens_per_sec": round(estimated_tps, 2),
    }
