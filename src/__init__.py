"""GarudaAI - A self-hosted, hardware-aware, phone-controlled local AI agent platform."""

__version__ = "0.1.0"
__author__ = "GarudaAI Contributors"

from .hardware import HardwareDetector
from .models import ModelSuggester
from .ollama_manager import OllamaManager

__all__ = ["HardwareDetector", "ModelSuggester", "OllamaManager"]
