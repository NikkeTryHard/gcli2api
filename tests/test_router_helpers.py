"""
Tests for helper functions in antigravity_anthropic_router.

These tests cover:
1. remove_nulls_for_tool_input - Tool input sanitization
2. _pick_usage_metadata_from_antigravity_response - Usage metadata extraction
3. _convert_antigravity_response_to_anthropic_message - Response conversion
4. Edge cases in thinking handling
5. Debug/logging helper functions
6. Redaction functions for sensitive data
"""

import pytest
import sys

sys.path.insert(0, "/home/louiskaneko/dev/ccr-forge/gcli2api")

from src.antigravity_anthropic_router import (
    _convert_antigravity_response_to_anthropic_message,
)
from src.anthropic_helpers import remove_nulls_for_tool_input


class TestRemoveNullsForToolInput:
    """Tests for remove_nulls_for_tool_input helper"""

    def test_removes_null_from_flat_dict(self):
        """Null values should be removed from flat dicts"""
        input_data = {"a": 1, "b": None, "c": "test", "d": None}
        result = remove_nulls_for_tool_input(input_data)
        assert result == {"a": 1, "c": "test"}
        assert "b" not in result
        assert "d" not in result

    def test_removes_null_from_nested_dict(self):
        """Null values should be removed from nested dicts"""
        input_data = {
            "level1": {
                "keep": "value",
                "remove": None,
                "level2": {"nested_keep": 123, "nested_remove": None},
            }
        }
        result = remove_nulls_for_tool_input(input_data)
        assert result == {"level1": {"keep": "value", "level2": {"nested_keep": 123}}}

    def test_removes_null_from_list(self):
        """Null values should be removed from lists"""
        input_data = [1, None, 2, None, 3]
        result = remove_nulls_for_tool_input(input_data)
        assert result == [1, 2, 3]

    def test_handles_nested_list_in_dict(self):
        """Null values in nested lists should be removed"""
        input_data = {"items": [1, None, {"key": None, "keep": "val"}, None]}
        result = remove_nulls_for_tool_input(input_data)
        assert result == {"items": [1, {"keep": "val"}]}

    def test_preserves_primitive_values(self):
        """Primitive values should pass through unchanged"""
        assert remove_nulls_for_tool_input(42) == 42
        assert remove_nulls_for_tool_input("string") == "string"
        assert remove_nulls_for_tool_input(True) is True
        assert remove_nulls_for_tool_input(False) is False
        assert remove_nulls_for_tool_input(3.14) == 3.14

    def test_empty_dict_returned_when_all_null(self):
        """Empty dict should be returned when all values are null"""
        input_data = {"a": None, "b": None}
        result = remove_nulls_for_tool_input(input_data)
        assert result == {}

    def test_empty_list_returned_when_all_null(self):
        """Empty list should be returned when all values are null"""
        input_data = [None, None, None]
        result = remove_nulls_for_tool_input(input_data)
        assert result == []


class TestConvertAntigravityResponseFullCoverage:
    """Comprehensive tests for _convert_antigravity_response_to_anthropic_message"""

    def _make_response_data(
        self, parts: list, finish_reason: str = "STOP", usage: dict = None
    ) -> dict:
        """Helper to create mock Antigravity response data"""
        candidate = {
            "content": {"parts": parts},
            "finishReason": finish_reason,
        }
        if usage:
            candidate["usageMetadata"] = usage

        return {
            "response": {
                "candidates": [candidate],
                "usageMetadata": usage
                or {"promptTokenCount": 100, "candidatesTokenCount": 50},
            }
        }

    def test_text_only_response(self):
        """Simple text response should be converted correctly"""
        response_data = self._make_response_data([{"text": "Hello world"}])
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test-model", message_id="msg_123"
        )

        assert result["role"] == "assistant"
        assert result["model"] == "test-model"
        assert result["id"] == "msg_123"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello world"

    def test_thinking_then_text_enabled(self):
        """Thinking followed by text with thinking enabled"""
        response_data = self._make_response_data(
            [
                {
                    "thought": True,
                    "text": "Let me analyze...",
                    "thoughtSignature": "sig1",
                },
                {"text": "The answer is 42."},
            ]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="test",
            message_id="msg_123",
            client_thinking_enabled=True,
        )

        assert len(result["content"]) == 2
        assert result["content"][0]["type"] == "thinking"
        assert result["content"][0]["thinking"] == "Let me analyze..."
        assert result["content"][0]["signature"] == "sig1"
        assert result["content"][1]["type"] == "text"
        assert result["content"][1]["text"] == "The answer is 42."

    def test_thinking_disabled_strips_thinking(self):
        """Thinking blocks should be stripped when disabled and not converting"""
        response_data = self._make_response_data(
            [
                {"thought": True, "text": "Secret thoughts"},
                {"text": "Public answer"},
            ]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="test",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=False,
        )

        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Public answer"
        assert "Secret thoughts" not in result["content"][0]["text"]

    def test_thinking_to_text_conversion(self):
        """Thinking should be converted to text when requested"""
        response_data = self._make_response_data(
            [
                {"thought": True, "text": "My reasoning..."},
                {"text": "My conclusion."},
            ]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="test",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        )

        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        text = result["content"][0]["text"]
        assert "<assistant_thinking>" in text
        assert "My reasoning..." in text
        assert "</assistant_thinking>" in text
        assert "My conclusion." in text

    def test_multiple_thinking_blocks_concatenated(self):
        """Multiple thinking blocks should be concatenated"""
        response_data = self._make_response_data(
            [
                {"thought": True, "text": "First thought."},
                {"thought": True, "text": "Second thought."},
                {"text": "Final answer."},
            ]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="test",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        )

        assert len(result["content"]) == 1
        text = result["content"][0]["text"]
        assert "First thought." in text
        assert "Second thought." in text
        assert "Final answer." in text

    def test_thinking_only_response(self):
        """Response with only thinking should still produce output"""
        response_data = self._make_response_data(
            [{"thought": True, "text": "Just thinking..."}]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="test",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        )

        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert "Just thinking..." in result["content"][0]["text"]

    def test_tool_use_with_thinking(self):
        """Tool use should work with thinking prepended"""
        response_data = self._make_response_data(
            [
                {"thought": True, "text": "I need to search."},
                {"functionCall": {"name": "search", "args": {"query": "test"}}},
            ]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="test",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        )

        assert len(result["content"]) == 2
        assert result["content"][0]["type"] == "text"
        assert "I need to search." in result["content"][0]["text"]
        assert result["content"][1]["type"] == "tool_use"
        assert result["content"][1]["name"] == "search"

    def test_tool_use_generates_id_if_missing(self):
        """Tool use should generate ID if not provided"""
        response_data = self._make_response_data(
            [{"functionCall": {"name": "test_tool", "args": {}}}]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_123"
        )

        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "tool_use"
        assert result["content"][0]["id"].startswith("toolu_")

    def test_tool_use_with_null_args_cleaned(self):
        """Tool use args with null values should be cleaned"""
        response_data = self._make_response_data(
            [
                {
                    "functionCall": {
                        "name": "tool",
                        "args": {"keep": "value", "remove": None},
                    }
                }
            ]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_123"
        )

        assert result["content"][0]["input"] == {"keep": "value"}

    def test_inline_data_image(self):
        """Inline data should be converted to image block"""
        response_data = self._make_response_data(
            [{"inlineData": {"mimeType": "image/png", "data": "base64imagedata"}}]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_123"
        )

        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "image"
        assert result["content"][0]["source"]["type"] == "base64"
        assert result["content"][0]["source"]["media_type"] == "image/png"
        assert result["content"][0]["source"]["data"] == "base64imagedata"

    def test_stop_reason_end_turn(self):
        """Stop reason should be end_turn for STOP finish"""
        response_data = self._make_response_data([{"text": "Done."}], "STOP")
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_123"
        )
        assert result["stop_reason"] == "end_turn"

    def test_stop_reason_max_tokens(self):
        """Stop reason should be max_tokens for MAX_TOKENS finish"""
        response_data = self._make_response_data([{"text": "Cut off..."}], "MAX_TOKENS")
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_123"
        )
        assert result["stop_reason"] == "max_tokens"

    def test_stop_reason_tool_use(self):
        """Stop reason should be tool_use when tool is used"""
        response_data = self._make_response_data(
            [{"functionCall": {"name": "tool", "args": {}}}]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_123"
        )
        assert result["stop_reason"] == "tool_use"

    def test_usage_from_response(self):
        """Usage should be extracted from response"""
        response_data = self._make_response_data(
            [{"text": "Hello"}],
            usage={"promptTokenCount": 150, "candidatesTokenCount": 75},
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_123"
        )

        assert result["usage"]["input_tokens"] == 150
        assert result["usage"]["output_tokens"] == 75

    def test_fallback_input_tokens(self):
        """Fallback input tokens should be used when not provided"""
        response_data = {
            "response": {"candidates": [{"content": {"parts": [{"text": "Hi"}]}}]}
        }
        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="test",
            message_id="msg_123",
            fallback_input_tokens=999,
        )

        assert result["usage"]["input_tokens"] == 999

    def test_empty_parts_handled(self):
        """Empty parts list should be handled"""
        response_data = {"response": {"candidates": [{"content": {"parts": []}}]}}
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_123"
        )

        assert result["content"] == []

    def test_non_dict_parts_skipped(self):
        """Non-dict parts should be skipped"""
        response_data = self._make_response_data(
            [
                "not a dict",
                123,
                {"text": "Valid text"},
                None,
            ]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_123"
        )

        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "Valid text"

    def test_thinking_without_signature(self):
        """Thinking block without signature should still work"""
        response_data = self._make_response_data(
            [{"thought": True, "text": "No signature here"}]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="test",
            message_id="msg_123",
            client_thinking_enabled=True,
        )

        assert result["content"][0]["type"] == "thinking"
        assert "signature" not in result["content"][0]

    def test_empty_thinking_text_skipped(self):
        """Empty thinking text should be skipped in buffer"""
        response_data = self._make_response_data(
            [
                {"thought": True, "text": ""},
                {"text": "Answer only."},
            ]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="test",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        )

        # Should just have the answer, no empty thinking wrapper
        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "Answer only."

    def test_mixed_content_types(self):
        """Mixed content types should all be handled"""
        response_data = self._make_response_data(
            [
                {"thought": True, "text": "Thinking..."},
                {"text": "Some text."},
                {"inlineData": {"mimeType": "image/jpeg", "data": "img"}},
                {"functionCall": {"name": "func", "args": {"x": 1}}},
            ]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="test",
            message_id="msg_123",
            client_thinking_enabled=True,
        )

        assert len(result["content"]) == 4
        assert result["content"][0]["type"] == "thinking"
        assert result["content"][1]["type"] == "text"
        assert result["content"][2]["type"] == "image"
        assert result["content"][3]["type"] == "tool_use"


class TestDebugLogFunctions:
    """Tests for debug logging functions"""

    def test_debug_log_request_payload_disabled(self, monkeypatch):
        """Should not log when debug is disabled"""
        from unittest.mock import MagicMock, patch

        monkeypatch.delenv("ANTHROPIC_DEBUG", raising=False)
        monkeypatch.delenv("ANTHROPIC_DEBUG_BODY", raising=False)

        from src.antigravity_anthropic_router import _debug_log_request_payload

        request = MagicMock()
        payload = {"test": "data"}

        with patch("src.antigravity_anthropic_router.log") as mock_log:
            _debug_log_request_payload(request, payload)
            mock_log.info.assert_not_called()

    def test_debug_log_request_payload_enabled(self, monkeypatch):
        """Should log when debug is enabled"""
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("ANTHROPIC_DEBUG", "1")
        monkeypatch.setenv("ANTHROPIC_DEBUG_BODY", "1")

        # Need to reload to pick up env changes
        import importlib
        import src.antigravity_anthropic_router as router_module

        importlib.reload(router_module)

        request = MagicMock()
        request.headers.get.return_value = "application/json"
        payload = {"model": "claude-3", "messages": []}

        with patch.object(router_module, "log") as mock_log:
            router_module._debug_log_request_payload(request, payload)
            assert mock_log.info.called

    def test_debug_log_downstream_request_body_disabled(self, monkeypatch):
        """Should not log downstream body when debug disabled"""
        from unittest.mock import patch

        monkeypatch.delenv("ANTHROPIC_DEBUG", raising=False)
        monkeypatch.delenv("ANTHROPIC_DEBUG_BODY", raising=False)

        from src.antigravity_anthropic_router import _debug_log_downstream_request_body

        with patch("src.antigravity_anthropic_router.log") as mock_log:
            _debug_log_downstream_request_body({"test": "data"})
            mock_log.info.assert_not_called()

    def test_debug_log_downstream_request_body_enabled(self, monkeypatch):
        """Should log downstream body when debug enabled"""
        from unittest.mock import patch

        monkeypatch.setenv("ANTHROPIC_DEBUG", "1")
        monkeypatch.setenv("ANTHROPIC_DEBUG_BODY", "1")

        import importlib
        import src.antigravity_anthropic_router as router_module

        importlib.reload(router_module)

        with patch.object(router_module, "log") as mock_log:
            router_module._debug_log_downstream_request_body({"test": "body"})
            assert mock_log.info.called


class TestDebugHelperFunctions:
    """Tests for debug and logging helper functions"""

    def test_anthropic_debug_max_chars_default(self, monkeypatch):
        """Default max chars should be 2000"""
        monkeypatch.delenv("ANTHROPIC_DEBUG_MAX_CHARS", raising=False)
        from src.antigravity_anthropic_router import _anthropic_debug_max_chars

        assert _anthropic_debug_max_chars() == 2000

    def test_anthropic_debug_max_chars_custom(self, monkeypatch):
        """Custom max chars should be respected"""
        monkeypatch.setenv("ANTHROPIC_DEBUG_MAX_CHARS", "500")
        from src.antigravity_anthropic_router import _anthropic_debug_max_chars

        assert _anthropic_debug_max_chars() == 500

    def test_anthropic_debug_max_chars_minimum(self, monkeypatch):
        """Min of 200 should be enforced"""
        monkeypatch.setenv("ANTHROPIC_DEBUG_MAX_CHARS", "50")
        from src.antigravity_anthropic_router import _anthropic_debug_max_chars

        assert _anthropic_debug_max_chars() == 200

    def test_anthropic_debug_max_chars_invalid(self, monkeypatch):
        """Invalid value should return default"""
        monkeypatch.setenv("ANTHROPIC_DEBUG_MAX_CHARS", "not_a_number")
        from src.antigravity_anthropic_router import _anthropic_debug_max_chars

        assert _anthropic_debug_max_chars() == 2000

    def test_anthropic_debug_enabled_false(self, monkeypatch):
        """Debug should be disabled by default"""
        monkeypatch.delenv("ANTHROPIC_DEBUG", raising=False)
        from src.anthropic_helpers import anthropic_debug_enabled

        assert anthropic_debug_enabled() is False

    def test_anthropic_debug_enabled_true(self, monkeypatch):
        """Debug should be enabled when set to 1"""
        monkeypatch.setenv("ANTHROPIC_DEBUG", "1")
        from src.anthropic_helpers import anthropic_debug_enabled

        assert anthropic_debug_enabled() is True

    def test_anthropic_debug_enabled_yes(self, monkeypatch):
        """Debug should be enabled when set to yes"""
        monkeypatch.setenv("ANTHROPIC_DEBUG", "yes")
        from src.anthropic_helpers import anthropic_debug_enabled

        assert anthropic_debug_enabled() is True

    def test_anthropic_debug_body_enabled(self, monkeypatch):
        """Debug body should be disabled by default"""
        monkeypatch.delenv("ANTHROPIC_DEBUG_BODY", raising=False)
        from src.antigravity_anthropic_router import _anthropic_debug_body_enabled

        assert _anthropic_debug_body_enabled() is False

    def test_anthropic_debug_body_enabled_true(self, monkeypatch):
        """Debug body should be enabled when set"""
        monkeypatch.setenv("ANTHROPIC_DEBUG_BODY", "true")
        from src.antigravity_anthropic_router import _anthropic_debug_body_enabled

        assert _anthropic_debug_body_enabled() is True


class TestRedactForLog:
    """Tests for _redact_for_log helper"""

    def test_redacts_sensitive_keys(self):
        """Sensitive keys should be redacted"""
        from src.antigravity_anthropic_router import _redact_for_log

        data = {
            "authorization": "Bearer secret123",
            "api_key": "sk-xxx",
            "password": "hunter2",
            "normal_key": "visible",
        }
        result = _redact_for_log(data, max_chars=2000)
        assert result["authorization"] == "<REDACTED>"
        assert result["api_key"] == "<REDACTED>"
        assert result["password"] == "<REDACTED>"
        assert result["normal_key"] == "visible"

    def test_truncates_long_strings(self):
        """Long strings should be truncated"""
        from src.antigravity_anthropic_router import _redact_for_log

        long_string = "x" * 5000
        result = _redact_for_log(long_string, max_chars=100)
        assert len(result) < 5000
        assert "省略" in result or "..." in result

    def test_redacts_base64_data(self):
        """Base64 data fields should be marked"""
        from src.antigravity_anthropic_router import _redact_for_log

        data = {"data": "x" * 1000}
        # Redact the data dict (triggers nested call with key_hint)
        _redact_for_log(data, key_hint="data", max_chars=2000)
        # The key_hint is applied to nested calls
        data_with_hint = _redact_for_log("x" * 1000, key_hint="data", max_chars=2000)
        assert "<base64 len=" in data_with_hint

    def test_handles_nested_structures(self):
        """Nested dicts and lists should be redacted recursively"""
        from src.antigravity_anthropic_router import _redact_for_log

        data = {
            "level1": {
                "token": "secret",
                "nested_list": [{"password": "pw123"}, "normal"],
            }
        }
        result = _redact_for_log(data, max_chars=2000)
        assert result["level1"]["token"] == "<REDACTED>"
        assert result["level1"]["nested_list"][0]["password"] == "<REDACTED>"
        assert result["level1"]["nested_list"][1] == "normal"

    def test_preserves_short_strings(self):
        """Short strings should not be truncated"""
        from src.antigravity_anthropic_router import _redact_for_log

        result = _redact_for_log("short", max_chars=2000)
        assert result == "short"


class TestJsonDumpsForLog:
    """Tests for _json_dumps_for_log helper"""

    def test_valid_json_serialization(self):
        """Valid data should be serialized"""
        from src.antigravity_anthropic_router import _json_dumps_for_log

        data = {"key": "value", "number": 123}
        result = _json_dumps_for_log(data)
        assert '"key":"value"' in result
        assert '"number":123' in result

    def test_handles_non_serializable(self):
        """Non-serializable data should fallback to str()"""
        from src.antigravity_anthropic_router import _json_dumps_for_log

        class NonSerializable:
            pass

        result = _json_dumps_for_log(NonSerializable())
        assert isinstance(result, str)


class TestPickUsageMetadata:
    """Tests for _pick_usage_metadata_from_antigravity_response"""

    def test_picks_from_response_level(self):
        """Should pick usage from response level"""
        from src.antigravity_anthropic_router import (
            _pick_usage_metadata_from_antigravity_response,
        )

        data = {
            "response": {
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
                "candidates": [{}],
            }
        }
        result = _pick_usage_metadata_from_antigravity_response(data)
        assert result["promptTokenCount"] == 100

    def test_picks_from_candidate_level_if_more_complete(self):
        """Should prefer candidate level if it has more fields"""
        from src.antigravity_anthropic_router import (
            _pick_usage_metadata_from_antigravity_response,
        )

        data = {
            "response": {
                "usageMetadata": {"promptTokenCount": 100},
                "candidates": [
                    {
                        "usageMetadata": {
                            "promptTokenCount": 100,
                            "candidatesTokenCount": 50,
                            "totalTokenCount": 150,
                        }
                    }
                ],
            }
        }
        result = _pick_usage_metadata_from_antigravity_response(data)
        assert "totalTokenCount" in result

    def test_handles_missing_usage(self):
        """Should handle missing usage metadata"""
        from src.antigravity_anthropic_router import (
            _pick_usage_metadata_from_antigravity_response,
        )

        data = {"response": {"candidates": [{}]}}
        result = _pick_usage_metadata_from_antigravity_response(data)
        assert result == {} or result is None or isinstance(result, dict)

    def test_handles_non_dict_response(self):
        """Should handle non-dict response"""
        from src.antigravity_anthropic_router import (
            _pick_usage_metadata_from_antigravity_response,
        )

        data = {"response": "not a dict"}
        result = _pick_usage_metadata_from_antigravity_response(data)
        assert result == {}

    def test_handles_non_dict_usage_metadata(self):
        """Should handle non-dict usage metadata"""
        from src.antigravity_anthropic_router import (
            _pick_usage_metadata_from_antigravity_response,
        )

        data = {
            "response": {
                "usageMetadata": "invalid",
                "candidates": [{"usageMetadata": None}],
            }
        }
        result = _pick_usage_metadata_from_antigravity_response(data)
        assert isinstance(result, dict)

    def test_handles_non_dict_candidate(self):
        """Should handle non-dict candidate"""
        from src.antigravity_anthropic_router import (
            _pick_usage_metadata_from_antigravity_response,
        )

        data = {
            "response": {
                "usageMetadata": {"promptTokenCount": 100},
                "candidates": ["not a dict"],
            }
        }
        result = _pick_usage_metadata_from_antigravity_response(data)
        assert result["promptTokenCount"] == 100


class TestAnthropicError:
    """Tests for _anthropic_error helper"""

    def test_creates_error_response(self):
        """Should create proper error response"""
        from src.antigravity_anthropic_router import _anthropic_error

        result = _anthropic_error(
            status_code=400, message="Bad request", error_type="invalid_request"
        )
        assert result.status_code == 400

    def test_default_error_type(self):
        """Should use api_error as default type"""
        from src.antigravity_anthropic_router import _anthropic_error

        result = _anthropic_error(status_code=500, message="Internal error")
        assert result.status_code == 500


class TestExtractApiToken:
    """Tests for _extract_api_token helper"""

    def test_extracts_from_credentials(self):
        """Should extract token from HTTPAuthorizationCredentials"""
        from unittest.mock import MagicMock
        from src.antigravity_anthropic_router import _extract_api_token

        request = MagicMock()
        credentials = MagicMock()
        credentials.credentials = "test_token"

        result = _extract_api_token(request, credentials)
        assert result == "test_token"

    def test_extracts_from_bearer_header(self):
        """Should extract token from Authorization header"""
        from unittest.mock import MagicMock
        from src.antigravity_anthropic_router import _extract_api_token

        request = MagicMock()
        request.headers.get.side_effect = lambda k: (
            "Bearer my_token" if k == "authorization" else None
        )

        result = _extract_api_token(request, None)
        assert result == "my_token"

    def test_extracts_from_x_api_key(self):
        """Should extract token from x-api-key header"""
        from unittest.mock import MagicMock
        from src.antigravity_anthropic_router import _extract_api_token

        request = MagicMock()
        request.headers.get.side_effect = lambda k: (
            "api_key_value" if k == "x-api-key" else None
        )

        result = _extract_api_token(request, None)
        assert result == "api_key_value"

    def test_returns_none_when_no_token(self):
        """Should return None when no token found"""
        from unittest.mock import MagicMock
        from src.antigravity_anthropic_router import _extract_api_token

        request = MagicMock()
        request.headers.get.return_value = None

        result = _extract_api_token(request, None)
        assert result is None


class TestInferProjectAndSession:
    """Tests for _infer_project_and_session helper"""

    def test_infers_project_id(self):
        """Should infer project ID from credential data"""
        from src.antigravity_anthropic_router import _infer_project_and_session

        data = {"project_id": "my_project"}
        project_id, session_id = _infer_project_and_session(data)
        assert project_id == "my_project"
        assert session_id.startswith("session-")

    def test_handles_missing_project_id(self):
        """Should handle missing project ID"""
        from src.antigravity_anthropic_router import _infer_project_and_session

        data = {}
        project_id, session_id = _infer_project_and_session(data)
        assert project_id == "None"
        assert session_id.startswith("session-")


# Run tests with: python -m pytest tests/test_router_helpers.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
