"""Tests for hardware detection module."""

import pytest
from src.hardware import HardwareDetector


@pytest.fixture
def detector():
    """Create a hardware detector instance."""
    return HardwareDetector()


def test_hardware_detection(detector):
    """Test basic hardware detection."""
    hardware = detector.detect(force_refresh=True)

    assert "gpu_vendor" in hardware
    assert "vram_mb" in hardware
    assert "cpu_cores" in hardware
    assert "ram_mb" in hardware
    assert "compute_ok" in hardware

    # Basic validations
    assert hardware["vram_mb"] >= 0
    assert hardware["cpu_cores"] > 0
    assert hardware["ram_mb"] > 0


def test_cpu_detection(detector):
    """Test CPU core detection."""
    cores = detector._detect_cpu_cores()
    assert cores > 0


def test_ram_detection(detector):
    """Test RAM detection."""
    ram_mb = detector._detect_system_ram()
    assert ram_mb > 0


def test_caching(detector, tmp_path):
    """Test hardware detection caching."""
    # Create detector with temp cache directory
    detector = HardwareDetector(cache_dir=str(tmp_path))

    # First detection
    hw1 = detector.detect(force_refresh=True)

    # Second detection (should use cache)
    hw2 = detector.detect(force_refresh=False)

    # Should return same data
    assert hw1["cpu_cores"] == hw2["cpu_cores"]
    assert hw1["ram_mb"] == hw2["ram_mb"]
