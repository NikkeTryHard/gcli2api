"""
Tests for model mapping to ensure models are routed correctly.

These tests verify that:
1. Supported models pass through unchanged
2. Special mappings work correctly (e.g., claude-opus-4-5 -> claude-opus-4-5-thinking)
3. Unknown models fall back to claude-sonnet-4-5
4. Gemini 3 Flash is properly supported (regression test for routing bug)
"""

import pytest
import sys

sys.path.insert(0, "/home/louiskaneko/dev/ccr-forge/gcli2api")

from src.anthropic_converter import map_claude_model_to_gemini


class TestModelPassThrough:
    """Tests for models that should pass through unchanged"""

    @pytest.mark.parametrize(
        "model",
        [
            "gemini-2.5-flash",
            "gemini-2.5-flash-thinking",
            "gemini-2.5-pro",
            "gemini-3-pro-low",
            "gemini-3-pro-high",
            "gemini-3-pro-image",
            "gemini-3-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash-image",
            "claude-sonnet-4-5",
            "claude-sonnet-4-5-thinking",
            "claude-opus-4-5-thinking",
            "gpt-oss-120b-medium",
        ],
    )
    def test_supported_models_pass_through(self, model):
        """Supported models should be returned unchanged"""
        result = map_claude_model_to_gemini(model)
        assert result == model, f"Expected {model} to pass through, got {result}"


class TestGemini3FlashRouting:
    """Regression tests for gemini-3-flash routing bug"""

    def test_gemini_3_flash_routes_correctly(self):
        """gemini-3-flash should route to itself, not claude-sonnet-4-5"""
        result = map_claude_model_to_gemini("gemini-3-flash")
        assert result == "gemini-3-flash", f"gemini-3-flash incorrectly routed to {result}"

    def test_gemini_3_flash_in_supported_models(self):
        """Verify gemini-3-flash is in the supported_models set in the code"""
        import os

        api_file = os.path.join(os.path.dirname(__file__), "..", "src", "anthropic_converter.py")
        with open(api_file, "r") as f:
            content = f.read()

        assert '"gemini-3-flash"' in content, "gemini-3-flash not found in supported_models"


class TestSpecialMappings:
    """Tests for models with special mapping rules"""

    def test_claude_opus_4_5_maps_to_thinking(self):
        """claude-opus-4-5 should map to claude-opus-4-5-thinking"""
        result = map_claude_model_to_gemini("claude-opus-4-5")
        assert result == "claude-opus-4-5-thinking"

    def test_claude_haiku_4_5_maps_to_gemini_flash(self):
        """claude-haiku-4-5 should map to gemini-2.5-flash"""
        result = map_claude_model_to_gemini("claude-haiku-4-5")
        assert result == "gemini-2.5-flash"

    def test_claude_sonnet_dot_notation_maps_correctly(self):
        """claude-sonnet-4.5 (with dot) should map to claude-sonnet-4-5"""
        result = map_claude_model_to_gemini("claude-sonnet-4.5")
        assert result == "claude-sonnet-4-5"

    @pytest.mark.parametrize(
        "model",
        [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-sonnet-20240620",
        ],
    )
    def test_legacy_claude_sonnet_models_map_correctly(self, model):
        """Legacy Claude Sonnet models should map to claude-sonnet-4-5"""
        result = map_claude_model_to_gemini(model)
        assert result == "claude-sonnet-4-5"

    def test_claude_opus_4_maps_to_gemini_pro_high(self):
        """claude-opus-4 should map to gemini-3-pro-high"""
        result = map_claude_model_to_gemini("claude-opus-4")
        assert result == "gemini-3-pro-high"

    def test_claude_3_haiku_maps_to_gemini_flash(self):
        """claude-3-haiku-20240307 should map to gemini-2.5-flash"""
        result = map_claude_model_to_gemini("claude-3-haiku-20240307")
        assert result == "gemini-2.5-flash"


class TestVersionedModelNormalization:
    """Tests for versioned model name normalization"""

    @pytest.mark.parametrize(
        "versioned,expected",
        [
            ("claude-opus-4-5-20251101", "claude-opus-4-5-thinking"),
            ("claude-sonnet-4-5-20251001", "claude-sonnet-4-5"),
            ("claude-haiku-4-5-20251001", "gemini-2.5-flash"),
        ],
    )
    def test_versioned_models_normalize_correctly(self, versioned, expected):
        """Versioned model names should be normalized and mapped correctly"""
        result = map_claude_model_to_gemini(versioned)
        assert result == expected, f"Expected {versioned} to map to {expected}, got {result}"


class TestUnknownModelFallback:
    """Tests for unknown model fallback behavior"""

    @pytest.mark.parametrize(
        "model",
        [
            "unknown-model",
            "gpt-4",
            "llama-3",
            "some-random-model",
        ],
    )
    def test_unknown_models_fallback_to_sonnet(self, model):
        """Unknown models should fall back to claude-sonnet-4-5"""
        result = map_claude_model_to_gemini(model)
        assert result == "claude-sonnet-4-5", f"Expected {model} to fall back to claude-sonnet-4-5, got {result}"

    def test_empty_model_fallback(self):
        """Empty model name should fall back to claude-sonnet-4-5"""
        result = map_claude_model_to_gemini("")
        assert result == "claude-sonnet-4-5"

    def test_none_model_fallback(self):
        """None model should fall back to claude-sonnet-4-5"""
        result = map_claude_model_to_gemini(None)
        assert result == "claude-sonnet-4-5"
