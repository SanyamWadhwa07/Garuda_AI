"""Hardware detection module for GarudaAI.

Detects GPU, CPU, RAM, and disk capabilities to inform model selection.
"""

import json
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class HardwareDetector:
    """Detect and report system hardware capabilities."""

    def __init__(self, cache_dir: str = "~/.cache/garudaai", cache_ttl_hours: int = 24):
        """Initialize hardware detector.
        
        Args:
            cache_dir: Directory for caching hardware info
            cache_ttl_hours: Cache time-to-live in hours
        """
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "hardware.json"
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    def detect(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Detect hardware and return capabilities.
        
        Args:
            force_refresh: Skip cache and re-detect hardware
            
        Returns:
            Dict with gpu_vendor, vram_mb, cpu_cores, ram_mb, disk_speed_mbps, compute_ok
        """
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

        # Test compute capability by checking drivers
        result["compute_ok"] = self._test_compute()

        # Write cache
        with open(self.cache_file, 'w') as f:
            json.dump(result, f, indent=2)

        return result

    def _detect_gpu_vendor(self) -> Optional[str]:
        """Detect GPU vendor (nvidia, amd, intel, or none)."""
        # Check for NVIDIA
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, check=False, timeout=2)
            return "nvidia"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Check for AMD (ROCm)
        try:
            subprocess.run(["rocm-smi"], capture_output=True, check=False, timeout=2)
            return "amd"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Check for Intel Arc
        try:
            result = subprocess.run(
                ["lspci"], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and "Intel.*GPU" in result.stdout.upper():
                return "intel"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    def _detect_vram(self) -> int:
        """Detect GPU VRAM in MB. Returns 0 if no GPU detected."""
        try:
            # NVIDIA
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,nounits,noheader"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return int(result.stdout.strip().split('\n')[0])
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass

        try:
            # AMD (rocm-smi outputs in MB)
            result = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                # Rough estimate: MI100=32GB, MI50=32GB, etc.
                # For now, parse the product name - this is a heuristic
                if "MI100" in result.stdout or "MI200" in result.stdout:
                    return 32768
                elif "MI50" in result.stdout or "MI60" in result.stdout:
                    return 16384
                else:
                    return 8192  # Conservative default
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return 0

    def _detect_cpu_cores(self) -> int:
        """Detect number of CPU cores."""
        try:
            result = subprocess.run(
                ["nproc"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass

        # Fallback: read from /proc/cpuinfo
        try:
            with open("/proc/cpuinfo", "r") as f:
                return len([line for line in f if line.startswith("processor")])
        except (FileNotFoundError, IOError):
            return 4  # Conservative default

    def _detect_system_ram(self) -> int:
        """Detect total system RAM in MB."""
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1])  # Already in KB, convert to MB
        except (FileNotFoundError, IOError, IndexError):
            pass

        # Fallback via free command
        try:
            result = subprocess.run(
                ["free", "-m"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                return int(lines[1].split()[1])  # Mem row, total column
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
            pass

        return 8192  # Conservative default (8GB)

    def _detect_disk_speed(self) -> float:
        """Estimate disk speed in MB/s using dd benchmark."""
        try:
            result = subprocess.run(
                ["dd", "if=/dev/zero", "of=/tmp/test.img", "bs=1M", "count=100"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Parse output like "100 MB/s"
            output = result.stdout + result.stderr
            for line in output.split('\n'):
                if "MB/s" in line:
                    parts = line.split()
                    try:
                        return float(parts[-2])
                    except (ValueError, IndexError):
                        pass
            # Clean up
            try:
                os.remove("/tmp/test.img")
            except FileNotFoundError:
                pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return 100.0  # Conservative default

    def _test_compute(self) -> bool:
        """Test if compute is actually working (drivers OK)."""
        # This will be expanded in Phase 2 to try loading a tiny model.
        # For now, check if nvidia-smi or rocm-smi works.
        try:
            gpu_vendor = self._detect_gpu_vendor()
            if gpu_vendor == "nvidia":
                result = subprocess.run(
                    ["nvidia-smi"],
                    capture_output=True,
                    timeout=2,
                )
                return result.returncode == 0
            elif gpu_vendor == "amd":
                result = subprocess.run(
                    ["rocm-smi"],
                    capture_output=True,
                    timeout=2,
                )
                return result.returncode == 0
            else:
                # CPU is always available
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False


def detect_hardware(force_refresh: bool = False) -> Dict[str, Any]:
    """Convenience function to detect hardware."""
    detector = HardwareDetector()
    return detector.detect(force_refresh=force_refresh)
