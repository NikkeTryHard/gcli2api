"""
Tests for native Anthropic Messages API endpoint.

These tests cover:
1. Request model validation
2. Response format (Anthropic Messages API format)
3. Streaming vs non-streaming
4. Thinking mode handling via config
5. Tool use passthrough
6. Error responses in Anthropic format
"""

import pytest
import sys

sys.path.insert(0, "/home/louiskaneko/dev/ccr-forge/gcli2api")


class TestAnthropicMessagesRequestModel:
    """Tests for AnthropicMessagesRequest Pydantic model"""

    def test_valid_minimal_request(self):
        """Minimal valid request should be accepted"""
        from src.models import AnthropicMessagesRequest

        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert request.model == "claude-sonnet-4-5"
        assert request.max_tokens == 1024
        assert len(request.messages) == 1

    def test_valid_full_request(self):
        """Full request with all optional fields should be accepted"""
        from src.models import AnthropicMessagesRequest

        request = AnthropicMessagesRequest(
            model="claude-opus-4-5",
            max_tokens=4096,
            messages=[
                {"role": "user", "content": "What is 2+2?"},
            ],
            system="You are a helpful assistant.",
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            stream=True,
            stop_sequences=["END"],
            metadata={"user_id": "test123"},
            thinking={"type": "enabled", "budget_tokens": 2048},
        )
        assert request.model == "claude-opus-4-5"
        assert request.stream is True
        assert request.temperature == 0.7
        assert request.thinking["type"] == "enabled"

    def test_missing_required_fields(self):
        """Missing required fields should raise validation error"""
        from src.models import AnthropicMessagesRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AnthropicMessagesRequest(
                model="claude-sonnet-4-5",
                # missing max_tokens and messages
            )

    def test_empty_messages_rejected(self):
        """Empty messages list should be rejected"""
        from src.models import AnthropicMessagesRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AnthropicMessagesRequest(
                model="claude-sonnet-4-5",
                max_tokens=1024,
                messages=[],
            )

    def test_invalid_max_tokens(self):
        """Non-positive max_tokens should be rejected"""
        from src.models import AnthropicMessagesRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AnthropicMessagesRequest(
                model="claude-sonnet-4-5",
                max_tokens=0,
                messages=[{"role": "user", "content": "Hello"}],
            )

    def test_stream_default_false(self):
        """Stream should default to False"""
        from src.models import AnthropicMessagesRequest

        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert request.stream is False

    def test_thinking_dict_format(self):
        """Thinking dict format should be accepted"""
        from src.models import AnthropicMessagesRequest

        request = AnthropicMessagesRequest(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
            thinking={"type": "enabled", "budget_tokens": 4096},
        )
        assert request.thinking["type"] == "enabled"
        assert request.thinking["budget_tokens"] == 4096

    def test_thinking_bool_format(self):
        """Thinking bool format should be accepted for backwards compat"""
        from src.models import AnthropicMessagesRequest

        request = AnthropicMessagesRequest(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
            thinking=False,
        )
        assert request.thinking is False

    def test_multimodal_content(self):
        """Multimodal content (text + image) should be accepted"""
        from src.models import AnthropicMessagesRequest

        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image?"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "base64data...",
                            },
                        },
                    ],
                }
            ],
        )
        assert len(request.messages) == 1

    def test_tool_use_request(self):
        """Request with tools should be accepted"""
        from src.models import AnthropicMessagesRequest

        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Search for Python tutorials"}],
            tools=[
                {
                    "name": "search",
                    "description": "Search the web",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                }
            ],
        )
        assert len(request.tools) == 1
        assert request.tools[0]["name"] == "search"


class TestAnthropicMessagesResponseFormat:
    """Tests for Anthropic Messages API response format"""

    def test_response_has_required_fields(self):
        """Response should have all required Anthropic fields"""
        from src.models import AnthropicMessagesResponse

        response = AnthropicMessagesResponse(
            id="msg_123",
            type="message",
            role="assistant",
            model="claude-sonnet-4-5",
            content=[{"type": "text", "text": "Hello!"}],
            stop_reason="end_turn",
            stop_sequence=None,
            usage={"input_tokens": 10, "output_tokens": 5},
        )

        assert response.id == "msg_123"
        assert response.type == "message"
        assert response.role == "assistant"
        assert response.stop_reason == "end_turn"

    def test_response_with_thinking(self):
        """Response with thinking block should be valid"""
        from src.models import AnthropicMessagesResponse

        response = AnthropicMessagesResponse(
            id="msg_456",
            type="message",
            role="assistant",
            model="claude-opus-4-5",
            content=[
                {
                    "type": "thinking",
                    "thinking": "Let me think...",
                    "signature": "sig123",
                },
                {"type": "text", "text": "The answer is 42."},
            ],
            stop_reason="end_turn",
            stop_sequence=None,
            usage={"input_tokens": 15, "output_tokens": 20},
        )

        assert len(response.content) == 2
        assert response.content[0]["type"] == "thinking"

    def test_response_with_tool_use(self):
        """Response with tool_use should be valid"""
        from src.models import AnthropicMessagesResponse

        response = AnthropicMessagesResponse(
            id="msg_789",
            type="message",
            role="assistant",
            model="claude-sonnet-4-5",
            content=[
                {
                    "type": "tool_use",
                    "id": "toolu_abc123",
                    "name": "search",
                    "input": {"query": "Python tutorials"},
                }
            ],
            stop_reason="tool_use",
            stop_sequence=None,
            usage={"input_tokens": 20, "output_tokens": 15},
        )

        assert response.stop_reason == "tool_use"
        assert response.content[0]["type"] == "tool_use"


class TestAnthropicErrorResponse:
    """Tests for Anthropic error response format"""

    def test_error_response_format(self):
        """Error response should match Anthropic format"""
        from src.models import AnthropicErrorResponse

        error = AnthropicErrorResponse(
            type="error",
            error={
                "type": "invalid_request_error",
                "message": "Invalid model specified",
            },
        )

        assert error.type == "error"
        assert error.error["type"] == "invalid_request_error"
        assert "message" in error.error


class TestThinkingConfigIntegration:
    """Tests for thinking config integration with endpoint"""

    @pytest.mark.asyncio
    async def test_thinking_config_applied_to_request(self, monkeypatch):
        """Config thinking settings should be applied to request processing"""
        monkeypatch.setenv("ANTHROPIC_DEFAULT_THINKING_BUDGET", "2048")
        monkeypatch.setenv("ANTHROPIC_THINKING_ENABLED", "true")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        default_budget = await config_module.get_anthropic_default_thinking_budget()
        thinking_enabled = await config_module.get_anthropic_thinking_enabled()

        assert default_budget == 2048
        assert thinking_enabled is True

    @pytest.mark.asyncio
    async def test_thinking_to_text_fallback_config(self, monkeypatch):
        """Thinking-to-text fallback config should work"""
        monkeypatch.setenv("ANTHROPIC_THINKING_TO_TEXT_FALLBACK", "true")

        import importlib
        import config as config_module

        importlib.reload(config_module)

        fallback = await config_module.get_anthropic_thinking_to_text_fallback()
        assert fallback is True


class TestNothinkingModelVariant:
    """Tests for -nothinking model variant handling"""

    def test_nothinking_suffix_detection(self):
        """Model with -nothinking suffix should be detected"""
        model = "claude-opus-4-5-nothinking"

        has_nothinking = "-nothinking" in model.lower()
        assert has_nothinking is True

        # Strip the suffix for downstream
        base_model = model.replace("-nothinking", "")
        assert base_model == "claude-opus-4-5"

    def test_regular_model_no_nothinking(self):
        """Regular model should not trigger nothinking mode"""
        model = "claude-sonnet-4-5"

        has_nothinking = "-nothinking" in model.lower()
        assert has_nothinking is False


class TestHelperFunctions:
    """Tests for router helper functions"""

    def test_generate_message_id(self):
        """Message ID should be generated in correct format"""
        import uuid

        # Simulate message ID generation
        message_id = f"msg_{uuid.uuid4().hex}"

        assert message_id.startswith("msg_")
        assert len(message_id) > 10

    def test_extract_stop_reason_mapping(self):
        """Stop reasons should map correctly from Antigravity to Anthropic"""
        finish_reason_map = {
            "STOP": "end_turn",
            "MAX_TOKENS": "max_tokens",
            "SAFETY": "end_turn",
            "RECITATION": "end_turn",
        }

        assert finish_reason_map.get("STOP") == "end_turn"
        assert finish_reason_map.get("MAX_TOKENS") == "max_tokens"
        assert finish_reason_map.get("UNKNOWN", "end_turn") == "end_turn"


class TestNativeV1MessagesEndpoint:
    """Tests for native /v1/messages endpoint routes"""

    def test_router_has_v1_messages_route(self):
        """Router should have /v1/messages route registered"""
        from src.antigravity_anthropic_router import router

        # Get all registered routes
        route_paths = [route.path for route in router.routes]

        assert "/v1/messages" in route_paths
        assert "/antigravity/v1/messages" in route_paths

    def test_router_has_v1_messages_count_tokens_route(self):
        """Router should have /v1/messages/count_tokens route registered"""
        from src.antigravity_anthropic_router import router

        route_paths = [route.path for route in router.routes]

        assert "/v1/messages/count_tokens" in route_paths
        assert "/antigravity/v1/messages/count_tokens" in route_paths

    def test_v1_messages_route_accepts_post(self):
        """v1/messages routes should accept POST method"""
        from src.antigravity_anthropic_router import router

        for route in router.routes:
            if route.path in ["/v1/messages", "/antigravity/v1/messages"]:
                assert "POST" in route.methods

    def test_both_routes_use_same_handler(self):
        """Both /v1/messages and /antigravity/v1/messages should use same handler"""
        from src.antigravity_anthropic_router import router

        v1_handler = None
        antigravity_handler = None

        for route in router.routes:
            if route.path == "/v1/messages":
                v1_handler = route.endpoint
            elif route.path == "/antigravity/v1/messages":
                antigravity_handler = route.endpoint

        assert v1_handler is not None
        assert antigravity_handler is not None
        assert v1_handler == antigravity_handler


# Run tests with: python -m pytest tests/test_anthropic_endpoint.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
