"""Model recommendation engine for GarudaAI.

Suggests appropriate models based on hardware and use case.
Model database updated for 2026 — all entries verified in Ollama registry.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class Model:
    """Model definition."""
    name: str
    vram_required_mb: int
    quantization: str        # q4, q5, q8, fp16
    use_cases: List[str]     # chat / coding / reasoning / vision
    description: str
    parameters_billion: float
    url: str                 # Ollama pull identifier
    airllm: bool = False     # True → served via AirLLM, not Ollama
    hf_id: str = ""          # HuggingFace model ID (AirLLM only)


class ModelSuggester:
    """Recommend models based on hardware specs."""

    # ---------------------------------------------------------------------------
    # Current model database (2026 — all available in Ollama registry)
    # ---------------------------------------------------------------------------
    MODELS: List[Model] = [
        # ── Tiny (CPU / 2-4 GB VRAM) ─────────────────────────────────────────
        Model(
            name="gemma2:2b",
            vram_required_mb=2048,
            quantization="q4",
            use_cases=["chat", "coding"],
            description="Google Gemma 2B — excellent quality for its size",
            parameters_billion=2.0,
            url="gemma2:2b",
        ),
        Model(
            name="phi3.5:3.8b",
            vram_required_mb=3072,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Microsoft Phi-3.5 — best-in-class tiny reasoning model",
            parameters_billion=3.8,
            url="phi3.5",
        ),
        Model(
            name="qwen2.5:3b",
            vram_required_mb=2560,
            quantization="q4",
            use_cases=["chat", "coding"],
            description="Alibaba Qwen 2.5 3B — strong multilingual support",
            parameters_billion=3.0,
            url="qwen2.5:3b",
        ),
        # ── Small (4-8 GB VRAM) ───────────────────────────────────────────────
        Model(
            name="llama3.2:3b",
            vram_required_mb=3072,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Meta Llama 3.2 3B — Meta's current small flagship",
            parameters_billion=3.0,
            url="llama3.2:3b",
        ),
        Model(
            name="mistral:7b",
            vram_required_mb=5120,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Mistral 7B — proven, fast, excellent all-rounder",
            parameters_billion=7.0,
            url="mistral:7b",
        ),
        Model(
            name="qwen2.5:7b",
            vram_required_mb=5120,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Qwen 2.5 7B — strong coder, multilingual",
            parameters_billion=7.0,
            url="qwen2.5:7b",
        ),
        Model(
            name="deepseek-coder-v2:7b",
            vram_required_mb=5120,
            quantization="q4",
            use_cases=["coding"],
            description="DeepSeek Coder V2 7B — best 7B model for code",
            parameters_billion=7.0,
            url="deepseek-coder-v2:7b-lite-instruct-q4_K_M",
        ),
        # ── Medium (8-16 GB VRAM) ─────────────────────────────────────────────
        Model(
            name="llama3.1:8b",
            vram_required_mb=6144,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Meta Llama 3.1 8B — highly capable, well-tuned",
            parameters_billion=8.0,
            url="llama3.1:8b",
        ),
        Model(
            name="gemma2:9b",
            vram_required_mb=7168,
            quantization="q4",
            use_cases=["chat", "reasoning"],
            description="Google Gemma 2 9B — exceptional reasoning quality",
            parameters_billion=9.0,
            url="gemma2:9b",
        ),
        Model(
            name="mistral-nemo:12b",
            vram_required_mb=9216,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Mistral NeMo 12B — Mistral + NVIDIA collaboration",
            parameters_billion=12.0,
            url="mistral-nemo:12b",
        ),
        Model(
            name="qwen2.5:14b",
            vram_required_mb=10240,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Qwen 2.5 14B — strong coding and long-context",
            parameters_billion=14.0,
            url="qwen2.5:14b",
        ),
        # ── Large (16+ GB VRAM) ───────────────────────────────────────────────
        Model(
            name="llama3.3:70b",
            vram_required_mb=40960,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Meta Llama 3.3 70B — best open-weight model available",
            parameters_billion=70.0,
            url="llama3.3:70b",
        ),
        Model(
            name="qwen2.5:32b",
            vram_required_mb=20480,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Qwen 2.5 32B — best balance of size and capability",
            parameters_billion=32.0,
            url="qwen2.5:32b",
        ),
        # ── Vision ────────────────────────────────────────────────────────────
        Model(
            name="llava:7b",
            vram_required_mb=5120,
            quantization="q4",
            use_cases=["vision", "chat"],
            description="LLaVA 7B — understands images and photos",
            parameters_billion=7.0,
            url="llava:7b",
        ),
        Model(
            name="llama3.2-vision:11b",
            vram_required_mb=8192,
            quantization="q4",
            use_cases=["vision", "chat", "reasoning"],
            description="Meta Llama 3.2 Vision 11B — best open vision model",
            parameters_billion=11.0,
            url="llama3.2-vision:11b",
        ),
        # ── AirLLM Slow Mode (layer-offloaded, needs SSD + 4GB VRAM) ─────────
        Model(
            name="llama3.3:70b-airllm",
            vram_required_mb=4096,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Llama 3.3 70B via AirLLM — slow (1-3 min/reply) but full 70B quality on 4GB GPU",
            parameters_billion=70.0,
            url="",
            airllm=True,
            hf_id="meta-llama/Llama-3.3-70B-Instruct",
        ),
        Model(
            name="qwen2.5:72b-airllm",
            vram_required_mb=4096,
            quantization="q4",
            use_cases=["chat", "coding", "reasoning"],
            description="Qwen 2.5 72B via AirLLM — slow but powerful on small GPUs",
            parameters_billion=72.0,
            url="",
            airllm=True,
            hf_id="Qwen/Qwen2.5-72B-Instruct",
        ),
        Model(
            name="mixtral:8x7b-airllm",
            vram_required_mb=4096,
            quantization="q4",
            use_cases=["chat", "coding"],
            description="Mixtral 8x7B via AirLLM — mixture-of-experts on small GPU",
            parameters_billion=46.7,
            url="",
            airllm=True,
            hf_id="mistralai/Mixtral-8x7B-Instruct-v0.1",
        ),
    ]

    def __init__(self):
        pass

    def suggest(
        self,
        vram_mb: int,
        cpu_cores: int,
        ram_mb: int,
        use_case: Optional[str] = None,
        prefer_smaller: bool = True,
    ) -> Dict[str, Any]:
        """Suggest models based on hardware and use case.

        Returns dict with primary_model, alternatives, reason, all_matching.
        AirLLM models are only included when is_airllm_eligible() says so.
        """
        from .hardware import is_airllm_eligible
        airllm_info = is_airllm_eligible({"vram_mb": vram_mb, "disk_speed_mbps": 0, "ram_mb": ram_mb})

        # Filter non-AirLLM models by VRAM
        standard = [m for m in self.MODELS if not m.airllm]
        fitting = [m for m in standard if m.vram_required_mb <= vram_mb]

        # CPU-only fallback: if RAM >= 75% of model VRAM, allow running on CPU
        if not fitting:
            fitting = [m for m in standard if m.vram_required_mb <= ram_mb * 0.75]

        if not fitting:
            fitting = [min(standard, key=lambda m: m.vram_required_mb)]

        # Apply use-case filter
        if use_case:
            filtered = [m for m in fitting if use_case in m.use_cases]
            selected = filtered if filtered else fitting
        else:
            selected = fitting

        # Sort
        selected.sort(key=lambda m: m.parameters_billion, reverse=not prefer_smaller)

        # Include AirLLM models if eligible and use_case is not vision
        airllm_models = []
        if airllm_info["eligible"] and use_case != "vision":
            airllm_candidates = [m for m in self.MODELS if m.airllm]
            if use_case:
                airllm_candidates = [m for m in airllm_candidates if use_case in m.use_cases]
            airllm_models = airllm_candidates

        primary = selected[0] if selected else fitting[0]
        alternatives = [m.name for m in selected[1:3]]

        if prefer_smaller:
            reason = f"Recommended for speed on {vram_mb}MB VRAM. {primary.description}"
        else:
            reason = f"Best quality for {vram_mb}MB VRAM. {primary.description}"

        return {
            "primary_model": primary.name,
            "primary_model_url": primary.url,
            "alternatives": alternatives,
            "reason": reason,
            "all_matching": [
                {
                    "name": m.name,
                    "vram_required_mb": m.vram_required_mb,
                    "quantization": m.quantization,
                    "use_cases": m.use_cases,
                    "description": m.description,
                    "parameters_billion": m.parameters_billion,
                    "airllm": m.airllm,
                }
                for m in selected + airllm_models
            ],
            "airllm_eligible": airllm_info["eligible"],
            "airllm_reason": airllm_info["reason"],
            "airllm_estimated_tps": airllm_info["estimated_tokens_per_sec"],
        }

    def get_model_by_name(self, name: str) -> Optional[Model]:
        """Look up a model by name (including AirLLM models)."""
        for m in self.MODELS:
            if m.name == name:
                return m
        return None

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        m = self.get_model_by_name(model_name)
        if not m:
            return None
        return {
            "name": m.name, "vram_required_mb": m.vram_required_mb,
            "quantization": m.quantization, "use_cases": m.use_cases,
            "description": m.description, "parameters_billion": m.parameters_billion,
            "url": m.url, "airllm": m.airllm, "hf_id": m.hf_id,
        }

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": m.name, "vram_required_mb": m.vram_required_mb,
             "use_cases": m.use_cases, "parameters_billion": m.parameters_billion,
             "airllm": m.airllm}
            for m in self.MODELS
        ]


def suggest_model(vram_mb: int, use_case: Optional[str] = None) -> Dict[str, Any]:
    """Convenience function to get model suggestion."""
    return ModelSuggester().suggest(vram_mb, cpu_cores=4, ram_mb=8192, use_case=use_case)
