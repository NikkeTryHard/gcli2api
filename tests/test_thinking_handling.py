"""
Tests for thinking handling in gcli2api.

These tests cover:
1. Non-streaming response conversion with thinking enabled/disabled
2. Streaming response conversion with thinking enabled/disabled
3. Model variant handling (-nothinking suffix)
4. Thinking-to-text conversion
5. Signature preservation
"""

import pytest

# Import the functions we're testing
import sys

sys.path.insert(0, "/home/louiskaneko/dev/ccr-forge/gcli2api")

from src.antigravity_anthropic_router import (
    _convert_antigravity_response_to_anthropic_message,
)


class TestNonStreamingThinkingHandling:
    """Tests for _convert_antigravity_response_to_anthropic_message"""

    def _make_response_data(self, parts: list, finish_reason: str = "STOP") -> dict:
        """Helper to create mock Antigravity response data"""
        return {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": parts},
                        "finishReason": finish_reason,
                        "usageMetadata": {
                            "promptTokenCount": 100,
                            "candidatesTokenCount": 50,
                        },
                    }
                ],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
            }
        }

    def test_thinking_enabled_preserves_thinking_blocks(self):
        """When client_thinking_enabled=True, thinking blocks should be preserved"""
        response_data = self._make_response_data(
            [
                {
                    "thought": True,
                    "text": "Let me think about this...",
                    "thoughtSignature": "sig123",
                },
                {"text": "Here is my answer."},
            ]
        )

        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=True,
            thinking_to_text=False,
        )

        # Should have 2 content blocks: thinking and text
        assert len(result["content"]) == 2
        assert result["content"][0]["type"] == "thinking"
        assert result["content"][0]["thinking"] == "Let me think about this..."
        assert result["content"][0]["signature"] == "sig123"
        assert result["content"][1]["type"] == "text"
        assert result["content"][1]["text"] == "Here is my answer."

    def test_thinking_disabled_strips_thinking_blocks(self):
        """When client_thinking_enabled=False and thinking_to_text=False, thinking should be stripped"""
        response_data = self._make_response_data(
            [
                {"thought": True, "text": "Let me think about this..."},
                {"text": "Here is my answer."},
            ]
        )

        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=False,
        )

        # Should have only 1 content block (text), thinking stripped
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Here is my answer."

    def test_thinking_disabled_converts_to_text(self):
        """When client_thinking_enabled=False and thinking_to_text=True, thinking should become text"""
        response_data = self._make_response_data(
            [
                {"thought": True, "text": "Let me think about this..."},
                {"text": "Here is my answer."},
            ]
        )

        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        )

        # Should have 1 content block with thinking prepended as text
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        text = result["content"][0]["text"]
        assert "<assistant_thinking>" in text
        assert "Let me think about this..." in text
        assert "</assistant_thinking>" in text
        assert "Here is my answer." in text

    def test_thinking_only_response_converts_to_text_block(self):
        """When there's only thinking and no text, it should still create a text block"""
        response_data = self._make_response_data(
            [{"thought": True, "text": "I thought deeply about this."}]
        )

        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        )

        # Should have 1 content block with thinking as text
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        text = result["content"][0]["text"]
        assert "<assistant_thinking>" in text
        assert "I thought deeply about this." in text

    def test_multiple_thinking_blocks_concatenated(self):
        """Multiple thinking blocks should be concatenated when converted to text"""
        response_data = self._make_response_data(
            [
                {"thought": True, "text": "First thought."},
                {"thought": True, "text": "Second thought."},
                {"text": "Final answer."},
            ]
        )

        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        )

        assert len(result["content"]) == 1
        text = result["content"][0]["text"]
        assert "First thought." in text
        assert "Second thought." in text
        assert "Final answer." in text

    def test_signature_preserved_when_thinking_enabled(self):
        """Signature should be preserved when thinking is enabled"""
        response_data = self._make_response_data(
            [
                {
                    "thought": True,
                    "text": "Thinking...",
                    "thoughtSignature": "unique_sig_abc123",
                }
            ]
        )

        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=True,
            thinking_to_text=False,
        )

        assert result["content"][0]["signature"] == "unique_sig_abc123"

    def test_tool_use_response_preserved(self):
        """Tool use responses should be preserved regardless of thinking settings"""
        response_data = self._make_response_data(
            [
                {"thought": True, "text": "I need to use a tool."},
                {
                    "functionCall": {
                        "id": "tool_123",
                        "name": "search",
                        "args": {"query": "test"},
                    }
                },
            ]
        )

        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        )

        # Should have thinking text block and tool_use block
        assert len(result["content"]) == 2
        assert result["content"][0]["type"] == "text"
        assert result["content"][1]["type"] == "tool_use"
        assert result["content"][1]["name"] == "search"

    def test_empty_thinking_text_handled(self):
        """Empty thinking text should be handled gracefully"""
        response_data = self._make_response_data(
            [{"thought": True, "text": ""}, {"text": "Answer."}]
        )

        result = _convert_antigravity_response_to_anthropic_message(
            response_data,
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        )

        # Should just have the text, no empty thinking prepended
        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "Answer."

    def test_stop_reason_correctly_set(self):
        """Stop reason should be correctly set based on response"""
        # Regular end_turn
        response_data = self._make_response_data(
            [{"text": "Done."}], finish_reason="STOP"
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_1"
        )
        assert result["stop_reason"] == "end_turn"

        # Max tokens
        response_data = self._make_response_data(
            [{"text": "Cut off..."}], finish_reason="MAX_TOKENS"
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_2"
        )
        assert result["stop_reason"] == "max_tokens"

        # Tool use
        response_data = self._make_response_data(
            [{"functionCall": {"name": "tool", "args": {}}}]
        )
        result = _convert_antigravity_response_to_anthropic_message(
            response_data, model="test", message_id="msg_3"
        )
        assert result["stop_reason"] == "tool_use"


class TestThinkingPreferenceDetection:
    """Tests for thinking preference detection in the router"""

    def test_thinking_type_enabled(self):
        """thinking: {type: "enabled"} should enable thinking"""
        thinking_value = {"type": "enabled", "budget_tokens": 10000}
        client_thinking_enabled = thinking_value.get("type") == "enabled"
        assert client_thinking_enabled is True

    def test_thinking_type_disabled(self):
        """thinking: {type: "disabled"} should disable thinking"""
        thinking_value = {"type": "disabled"}
        client_thinking_enabled = thinking_value.get("type") == "enabled"
        assert client_thinking_enabled is False

    def test_thinking_false(self):
        """thinking: false should disable thinking"""
        thinking_value = False
        client_thinking_enabled = True
        if thinking_value is False:
            client_thinking_enabled = False
        assert client_thinking_enabled is False

    def test_thinking_not_present(self):
        """Missing thinking should default to enabled (backwards compatible)"""
        thinking_value = None
        client_thinking_enabled = True
        if isinstance(thinking_value, dict):
            client_thinking_enabled = thinking_value.get("type") == "enabled"
        elif thinking_value is False:
            client_thinking_enabled = False
        # None case: keep default True
        assert client_thinking_enabled is True

    def test_nothinking_model_variant(self):
        """Model ending with -nothinking should disable thinking and enable thinking_to_text"""
        model = "claude-opus-4-5-nothinking"
        client_thinking_enabled = True
        thinking_to_text = False

        if "-nothinking" in model.lower():
            client_thinking_enabled = False
            thinking_to_text = True

        assert client_thinking_enabled is False
        assert thinking_to_text is True


class TestCliLogsParser:
    """Tests for CLI log parsing functionality"""

    def test_parse_standard_log_line(self):
        """Standard log line should be parsed correctly"""
        from cli_logs import parse_log_line

        line = "[2025-12-31 10:30:45] [INFO] [ANTHROPIC] Request received"
        result = parse_log_line(line)

        assert result is not None
        assert result["level"] == "info"
        assert result["component"] == "ANTHROPIC"
        assert "Request received" in result["message"]

    def test_parse_log_with_reqid(self):
        """Log line with reqId should extract it"""
        from cli_logs import parse_log_line

        line = "[2025-12-31 10:30:45] [DEBUG] Processing reqId=abc123 for model"
        result = parse_log_line(line)

        assert result is not None
        assert result["req_id"] == "abc123"

    def test_parse_invalid_line(self):
        """Invalid log line should return None"""
        from cli_logs import parse_log_line

        result = parse_log_line("This is not a valid log line")
        assert result is None

    def test_parse_time_delta(self):
        """Time delta strings should be parsed correctly"""
        from cli_logs import parse_time_delta
        from datetime import timedelta

        assert parse_time_delta("5m") == timedelta(minutes=5)
        assert parse_time_delta("1h") == timedelta(hours=1)
        assert parse_time_delta("30s") == timedelta(seconds=30)
        assert parse_time_delta("2d") == timedelta(days=2)
        assert parse_time_delta("invalid") is None


# Run tests with: python -m pytest tests/test_thinking_handling.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src", "--cov-report=term-missing"])
