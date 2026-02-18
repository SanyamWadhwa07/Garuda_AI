"""Tests for model suggestion engine."""

import pytest
from src.models import ModelSuggester


@pytest.fixture
def suggester():
    """Create a model suggester instance."""
    return ModelSuggester()


def test_suggestion_with_small_vram(suggester):
    """Test model suggestion with limited VRAM."""
    result = suggester.suggest(vram_mb=2048)  # 2GB

    assert "primary_model" in result
    assert "reason" in result
    assert "all_matching" in result

    # Should suggest a small model
    assert result["primary_model"] in ["tinyllama", "neural-chat"]


def test_suggestion_with_8gb_vram(suggester):
    """Test model suggestion with 8GB VRAM."""
    result = suggester.suggest(vram_mb=8192)  # 8GB

    assert "primary_model" in result
    primary = result["primary_model"]

    # Should suggest a reasonable model for 8GB
    assert primary is not None


def test_suggestion_by_use_case(suggester):
    """Test model suggestion filtered by use case."""
    result = suggester.suggest(vram_mb=8192, use_case="coding")

    assert "primary_model" in result
    assert "coding" in result["all_matching"][0]["use_cases"]


def test_list_models(suggester):
    """Test listing all available models."""
    models = suggester.list_models()

    assert len(models) > 0
    assert all("name" in m for m in models)
    assert all("vram_required_mb" in m for m in models)
