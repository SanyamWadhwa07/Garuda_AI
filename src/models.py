"""Model recommendation engine for GarudaAI.

Suggests appropriate models based on hardware and use case.
"""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class Model:
    """Model definition."""
    name: str
    vram_required_mb: int
    quantization: str  # q4, q5, q8, fp16
    use_cases: List[str]  # ["chat", "coding", "vision", "reasoning"]
    description: str
    parameters_billion: float
    url: str  # Ollama model identifier


class ModelSuggester:
    """Recommend models based on hardware specs."""

    # Curated model database (Phase 1)
    MODELS: List[Model] = [
        # Tiny models for low-end hardware
        Model(
            name="tinyllama",
            vram_required_mb=2048,
            quantization="q4",
            use_cases=["chat"],
            description="1.1B parameter model, fast and lightweight",
            parameters_billion=1.1,
            url="tinyllama:1.1b",
        ),
        Model(
            name="neural-chat",
            vram_required_mb=3072,
            quantization="q4",
            use_cases=["chat"],
            description="7B parameter chat model, good quality/speed tradeoff",
            parameters_billion=7,
            url="neural-chat:7b",
        ),
        # Mid-range models
        Model(
            name="mistral",
            vram_required_mb=6144,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="7B model, strong reasoning and coding",
            parameters_billion=7,
            url="mistral:7b",
        ),
        Model(
            name="orca-mini",
            vram_required_mb=3840,
            quantization="q4",
            use_cases=["chat", "reasoning"],
            description="3B model optimized for reasoning",
            parameters_billion=3,
            url="orca-mini:3b",
        ),
        Model(
            name="llama2",
            vram_required_mb=8192,
            quantization="q4",
            use_cases=["chat", "coding"],
            description="7B parameter model, very capable",
            parameters_billion=7,
            url="llama2:7b",
        ),
        # High-end models
        Model(
            name="mistral-large",
            vram_required_mb=16384,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="13B parameter, excellent reasoning and coding",
            parameters_billion=13,
            url="mistral:13b",
        ),
        Model(
            name="wizard-vicuna",
            vram_required_mb=12288,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="13B fine-tuned model",
            parameters_billion=13,
            url="wizardlm:13b",
        ),
        # Vision models (Phase 2+)
        Model(
            name="llava",
            vram_required_mb=10240,
            quantization="q4",
            use_cases=["vision", "chat"],
            description="7B vision model, can understand images",
            parameters_billion=7,
            url="llava:7b",
        ),
    ]

    def __init__(self):
        """Initialize the suggester."""
        pass

    def suggest(
        self,
        vram_mb: int,
        cpu_cores: int,
        ram_mb: int,
        use_case: Optional[str] = None,
        prefer_smaller: bool = False,
    ) -> Dict[str, Any]:
        """Suggest models based on hardware and use case.
        
        Args:
            vram_mb: Available GPU VRAM in MB (0 if no GPU)
            cpu_cores: Number of CPU cores
            ram_mb: Total system RAM in MB
            use_case: Specific use case ("chat", "coding", "reasoning", "vision", None for all)
            
        Returns:
            Dict with:
                - primary_model: Model name to use
                - alternatives: List of alternative model names
                - reason: Explanation of the recommendation
                - all_matching: List of all models that fit the hardware
        """
        # Filter models that fit in available VRAM
        fitting_models = [m for m in self.MODELS if m.vram_required_mb <= vram_mb]

        if not fitting_models:
            # If no GPU model fits, suggest smallest available
            fitting_models = [min(self.MODELS, key=lambda m: m.vram_required_mb)]

        # Filter by use case if specified
        if use_case:
            use_case_models = [m for m in fitting_models if use_case in m.use_cases]
            selected_models = use_case_models if use_case_models else fitting_models
        else:
            selected_models = fitting_models

        # Sort by parameter count (prefer smaller for speed or larger for quality)
        selected_models.sort(
            key=lambda m: m.parameters_billion,
            reverse=not prefer_smaller,
        )

        if not selected_models:
            primary = fitting_models[0]
            alternatives = fitting_models[1:3]
            reason = f"Recommended based on {vram_mb}MB VRAM. {use_case or 'General'} models may have limited capability."
        else:
            primary = selected_models[0]
            alternatives = selected_models[1:3]
            if prefer_smaller:
                reason = (
                    f"Recommended for speed on your {vram_mb}MB VRAM. "
                    f"{primary.description}"
                )
            else:
                reason = f"Recommended for your {vram_mb}MB VRAM. {primary.description}"

        return {
            "primary_model": primary.name,
            "primary_model_url": primary.url,
            "alternatives": [m.name for m in alternatives],
            "reason": reason,
            "all_matching": [
                {
                    "name": m.name,
                    "vram_required_mb": m.vram_required_mb,
                    "quantization": m.quantization,
                    "use_cases": m.use_cases,
                    "description": m.description,
                    "parameters_billion": m.parameters_billion,
                }
                for m in selected_models
            ],
        }

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific model."""
        for model in self.MODELS:
            if model.name == model_name:
                return {
                    "name": model.name,
                    "vram_required_mb": model.vram_required_mb,
                    "quantization": model.quantization,
                    "use_cases": model.use_cases,
                    "description": model.description,
                    "parameters_billion": model.parameters_billion,
                    "url": model.url,
                }
        return None

    def list_models(self) -> List[Dict[str, Any]]:
        """List all known models."""
        return [
            {
                "name": m.name,
                "vram_required_mb": m.vram_required_mb,
                "use_cases": m.use_cases,
                "parameters_billion": m.parameters_billion,
            }
            for m in self.MODELS
        ]


def suggest_model(vram_mb: int, use_case: Optional[str] = None) -> Dict[str, Any]:
    """Convenience function to get model suggestion."""
    suggester = ModelSuggester()
    return suggester.suggest(vram_mb, cpu_cores=4, ram_mb=8192, use_case=use_case)
