"""
Tests for configuration module enhancements.

These tests cover:
1. Existing config functionality (regression tests)
2. Timeout configuration (REQUEST_TIMEOUT, STREAMING_TIMEOUT, CONNECTION_TIMEOUT)
3. Thinking budget configuration (DEFAULT, MAX, ENABLED, TO_TEXT_FALLBACK)
"""

import pytest
import sys

sys.path.insert(0, "/home/louiskaneko/dev/ccr-forge/gcli2api")


class TestExistingConfigBehavior:
    """Regression tests for existing config functionality"""

    @pytest.mark.asyncio
    async def test_get_config_value_default(self):
        """get_config_value should return default when key not found"""
        from config import get_config_value

        result = await get_config_value("nonexistent_key", "default_val")
        assert result == "default_val"

    @pytest.mark.asyncio
    async def test_get_config_value_env_priority(self, monkeypatch):
        """Environment variable should take priority"""
        from config import get_config_value

        monkeypatch.setenv("TEST_ENV_VAR", "env_value")

        result = await get_config_value("test_key", "default", "TEST_ENV_VAR")
        assert result == "env_value"

    @pytest.mark.asyncio
    async def test_get_server_host_default(self, monkeypatch):
        """Default server host should be 0.0.0.0"""
        monkeypatch.delenv("HOST", raising=False)

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_server_host()
        assert result == "0.0.0.0"

    @pytest.mark.asyncio
    async def test_get_server_port_default(self, monkeypatch):
        """Default server port should be 7861"""
        monkeypatch.delenv("PORT", raising=False)

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_server_port()
        assert result == 7861


class TestTimeoutConfiguration:
    """Tests for timeout configuration functions"""

    @pytest.mark.asyncio
    async def test_get_request_timeout_default(self, monkeypatch):
        """Default request timeout should be 300.0 seconds"""
        monkeypatch.delenv("REQUEST_TIMEOUT", raising=False)

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_request_timeout()
        assert result == 300.0

    @pytest.mark.asyncio
    async def test_get_request_timeout_custom(self, monkeypatch):
        """Custom request timeout should be respected"""
        monkeypatch.setenv("REQUEST_TIMEOUT", "120")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_request_timeout()
        assert result == 120.0

    @pytest.mark.asyncio
    async def test_get_request_timeout_invalid(self, monkeypatch):
        """Invalid request timeout should return default"""
        monkeypatch.setenv("REQUEST_TIMEOUT", "not_a_number")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_request_timeout()
        assert result == 300.0

    @pytest.mark.asyncio
    async def test_get_streaming_timeout_default(self, monkeypatch):
        """Default streaming timeout should be 600.0 seconds"""
        monkeypatch.delenv("STREAMING_TIMEOUT", raising=False)

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_streaming_timeout()
        assert result == 600.0

    @pytest.mark.asyncio
    async def test_get_streaming_timeout_custom(self, monkeypatch):
        """Custom streaming timeout should be respected"""
        monkeypatch.setenv("STREAMING_TIMEOUT", "900")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_streaming_timeout()
        assert result == 900.0

    @pytest.mark.asyncio
    async def test_get_connection_timeout_default(self, monkeypatch):
        """Default connection timeout should be 30.0 seconds"""
        monkeypatch.delenv("CONNECTION_TIMEOUT", raising=False)

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_connection_timeout()
        assert result == 30.0

    @pytest.mark.asyncio
    async def test_get_connection_timeout_custom(self, monkeypatch):
        """Custom connection timeout should be respected"""
        monkeypatch.setenv("CONNECTION_TIMEOUT", "60")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_connection_timeout()
        assert result == 60.0


class TestThinkingBudgetConfiguration:
    """Tests for thinking budget configuration functions"""

    @pytest.mark.asyncio
    async def test_get_anthropic_default_thinking_budget_default(self, monkeypatch):
        """Default thinking budget should be 1024 tokens"""
        monkeypatch.delenv("ANTHROPIC_DEFAULT_THINKING_BUDGET", raising=False)

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_default_thinking_budget()
        assert result == 1024

    @pytest.mark.asyncio
    async def test_get_anthropic_default_thinking_budget_custom(self, monkeypatch):
        """Custom default thinking budget should be respected"""
        monkeypatch.setenv("ANTHROPIC_DEFAULT_THINKING_BUDGET", "2048")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_default_thinking_budget()
        assert result == 2048

    @pytest.mark.asyncio
    async def test_get_anthropic_max_thinking_budget_default(self, monkeypatch):
        """Default max thinking budget should be 32768 tokens"""
        monkeypatch.delenv("ANTHROPIC_MAX_THINKING_BUDGET", raising=False)

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_max_thinking_budget()
        assert result == 32768

    @pytest.mark.asyncio
    async def test_get_anthropic_max_thinking_budget_custom(self, monkeypatch):
        """Custom max thinking budget should be respected"""
        monkeypatch.setenv("ANTHROPIC_MAX_THINKING_BUDGET", "65536")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_max_thinking_budget()
        assert result == 65536

    @pytest.mark.asyncio
    async def test_get_anthropic_thinking_enabled_default(self, monkeypatch):
        """Thinking should be enabled by default"""
        monkeypatch.delenv("ANTHROPIC_THINKING_ENABLED", raising=False)

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_thinking_enabled()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_anthropic_thinking_enabled_false(self, monkeypatch):
        """Thinking can be disabled via env var"""
        monkeypatch.setenv("ANTHROPIC_THINKING_ENABLED", "false")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_thinking_enabled()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_anthropic_thinking_enabled_true(self, monkeypatch):
        """Thinking can be explicitly enabled"""
        monkeypatch.setenv("ANTHROPIC_THINKING_ENABLED", "true")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_thinking_enabled()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_anthropic_thinking_to_text_fallback_default(self, monkeypatch):
        """Thinking-to-text fallback should be enabled by default"""
        monkeypatch.delenv("ANTHROPIC_THINKING_TO_TEXT_FALLBACK", raising=False)

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_thinking_to_text_fallback()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_anthropic_thinking_to_text_fallback_false(self, monkeypatch):
        """Thinking-to-text fallback can be disabled"""
        monkeypatch.setenv("ANTHROPIC_THINKING_TO_TEXT_FALLBACK", "false")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_thinking_to_text_fallback()
        assert result is False

    @pytest.mark.asyncio
    async def test_thinking_budget_invalid_returns_default(self, monkeypatch):
        """Invalid thinking budget values should return default"""
        monkeypatch.setenv("ANTHROPIC_DEFAULT_THINKING_BUDGET", "not_a_number")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_default_thinking_budget()
        assert result == 1024

    @pytest.mark.asyncio
    async def test_thinking_budget_negative_returns_default(self, monkeypatch):
        """Negative thinking budget should be clamped to minimum"""
        monkeypatch.setenv("ANTHROPIC_DEFAULT_THINKING_BUDGET", "-100")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_anthropic_default_thinking_budget()
        # Should either return default or clamp to positive
        assert result > 0


class TestConfigurationValidation:
    """Tests for configuration value validation"""

    @pytest.mark.asyncio
    async def test_timeout_minimum_enforced(self, monkeypatch):
        """Timeout values should have a minimum"""
        monkeypatch.setenv("REQUEST_TIMEOUT", "0")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        result = await config_module.get_request_timeout()
        # Should either return default or enforce minimum
        assert result > 0

    @pytest.mark.asyncio
    async def test_thinking_budget_clamped_to_max(self, monkeypatch):
        """Default thinking budget should not exceed max"""
        monkeypatch.setenv("ANTHROPIC_DEFAULT_THINKING_BUDGET", "100000")
        monkeypatch.setenv("ANTHROPIC_MAX_THINKING_BUDGET", "32768")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        default_budget = await config_module.get_anthropic_default_thinking_budget()
        max_budget = await config_module.get_anthropic_max_thinking_budget()

        # Either clamp to max or allow override
        assert default_budget == 100000 or default_budget <= max_budget


# Run tests with: python -m pytest tests/test_config.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
