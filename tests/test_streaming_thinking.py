"""
Tests for streaming thinking handling in gcli2api.

These tests cover:
1. Streaming response conversion with thinking enabled/disabled
2. Thinking-to-text conversion in streaming mode
3. Signature handling in streaming
4. Tool use in streaming with thinking
5. Edge cases: empty chunks, multi-part responses
"""

import pytest
import json
import sys

sys.path.insert(0, "/home/louiskaneko/dev/ccr-forge/gcli2api")

from src.anthropic_streaming import (
    antigravity_sse_to_anthropic_sse,
    _sse_event,
    _StreamingState,
)
from src.anthropic_helpers import remove_nulls_for_tool_input


class AsyncLinesIterator:
    """Helper to create async iterator from list of SSE lines"""

    def __init__(self, lines: list[str]):
        self.lines = lines
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.lines):
            raise StopAsyncIteration
        line = self.lines[self.index]
        self.index += 1
        return line


def make_antigravity_sse_data(parts: list, finish_reason: str = None) -> str:
    """Create SSE data line for Antigravity response"""
    data = {
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
    return f"data: {json.dumps(data)}"


class TestSSEEventCreation:
    """Tests for _sse_event helper"""

    def test_creates_valid_sse_format(self):
        """SSE event should have correct format"""
        result = _sse_event("test_event", {"type": "test", "data": "value"})
        assert b"event: test_event\n" in result
        assert b"data: " in result
        assert b"\n\n" in result

    def test_json_encoding(self):
        """Data should be valid JSON"""
        result = _sse_event("test", {"key": "value"})
        data_line = result.decode("utf-8").split("data: ")[1].split("\n")[0]
        parsed = json.loads(data_line)
        assert parsed["key"] == "value"


class TestRemoveNullsForToolInput:
    """Tests for remove_nulls_for_tool_input helper"""

    def test_removes_null_values_from_dict(self):
        """Null values should be removed from dicts"""
        input_data = {"a": 1, "b": None, "c": "test"}
        result = remove_nulls_for_tool_input(input_data)
        assert result == {"a": 1, "c": "test"}

    def test_removes_null_from_nested_dict(self):
        """Null values should be removed from nested dicts"""
        input_data = {"outer": {"inner": None, "keep": "value"}}
        result = remove_nulls_for_tool_input(input_data)
        assert result == {"outer": {"keep": "value"}}

    def test_removes_null_from_list(self):
        """Null values should be removed from lists"""
        input_data = [1, None, "test", None]
        result = remove_nulls_for_tool_input(input_data)
        assert result == [1, "test"]

    def test_handles_primitive_values(self):
        """Primitive values should pass through unchanged"""
        assert remove_nulls_for_tool_input(42) == 42
        assert remove_nulls_for_tool_input("string") == "string"
        assert remove_nulls_for_tool_input(True) is True


class TestStreamingState:
    """Tests for _StreamingState class"""

    def test_initial_state(self):
        """State should initialize correctly"""
        state = _StreamingState(message_id="msg_123", model="claude-opus-4-5")
        assert state.message_id == "msg_123"
        assert state.model == "claude-opus-4-5"
        assert state._current_block_type is None
        assert state._current_block_index == -1
        assert state.has_tool_use is False

    def test_open_text_block(self):
        """Opening text block should return SSE event"""
        state = _StreamingState(message_id="msg_123", model="test")
        result = state.open_text_block()
        assert b"content_block_start" in result
        assert b'"type":"text"' in result
        assert state._current_block_type == "text"
        assert state._current_block_index == 0

    def test_open_thinking_block(self):
        """Opening thinking block should return SSE event"""
        state = _StreamingState(message_id="msg_123", model="test")
        result = state.open_thinking_block(signature="sig123")
        assert b"content_block_start" in result
        assert b'"type":"thinking"' in result
        assert b'"signature":"sig123"' in result
        assert state._current_block_type == "thinking"
        assert state._current_thinking_signature == "sig123"

    def test_close_block_if_open(self):
        """Closing block should return SSE event when block is open"""
        state = _StreamingState(message_id="msg_123", model="test")
        # No block open - should return None
        assert state.close_block_if_open() is None

        # Open a block
        state.open_text_block()
        result = state.close_block_if_open()
        assert result is not None
        assert b"content_block_stop" in result
        assert state._current_block_type is None


@pytest.mark.asyncio
class TestStreamingThinkingEnabled:
    """Tests for streaming with thinking enabled"""

    async def test_thinking_block_emitted(self):
        """When thinking enabled, thinking blocks should be emitted"""
        lines = [
            make_antigravity_sse_data(
                [
                    {
                        "thought": True,
                        "text": "Let me think...",
                        "thoughtSignature": "sig1",
                    }
                ]
            ),
            make_antigravity_sse_data([{"text": "Here is the answer."}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=True,
            thinking_to_text=False,
        ):
            events.append(event)

        # Verify thinking block was emitted
        events_str = b"".join(events).decode("utf-8")
        assert "thinking_delta" in events_str
        assert "Let me think..." in events_str
        assert "text_delta" in events_str
        assert "Here is the answer." in events_str

    async def test_signature_emitted_with_thinking(self):
        """Signature should be included in thinking block start"""
        lines = [
            make_antigravity_sse_data(
                [
                    {
                        "thought": True,
                        "text": "Thinking...",
                        "thoughtSignature": "unique_sig",
                    }
                ]
            ),
            make_antigravity_sse_data([{"text": "Done."}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=True,
            thinking_to_text=False,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        # Signature should be in the content_block_start for thinking
        assert "unique_sig" in events_str


@pytest.mark.asyncio
class TestStreamingThinkingDisabled:
    """Tests for streaming with thinking disabled"""

    async def test_thinking_stripped_when_disabled(self):
        """When thinking disabled and thinking_to_text=False, thinking should be stripped"""
        lines = [
            make_antigravity_sse_data(
                [{"thought": True, "text": "Secret thinking..."}]
            ),
            make_antigravity_sse_data([{"text": "Visible answer."}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=False,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "Secret thinking..." not in events_str
        assert "Visible answer." in events_str

    async def test_thinking_converted_to_text(self):
        """When thinking disabled and thinking_to_text=True, thinking becomes text"""
        lines = [
            make_antigravity_sse_data([{"thought": True, "text": "My thoughts..."}]),
            make_antigravity_sse_data([{"text": "Final answer."}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "assistant_thinking" in events_str
        assert "My thoughts..." in events_str
        assert "Final answer." in events_str

    async def test_thinking_only_response_handled(self):
        """Response with only thinking should still produce output"""
        lines = [
            make_antigravity_sse_data(
                [{"thought": True, "text": "Just thinking..."}], "STOP"
            ),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "assistant_thinking" in events_str
        assert "Just thinking..." in events_str


@pytest.mark.asyncio
class TestStreamingToolUse:
    """Tests for streaming with tool use"""

    async def test_tool_use_emitted(self):
        """Tool use should be emitted correctly"""
        lines = [
            make_antigravity_sse_data(
                [
                    {
                        "functionCall": {
                            "id": "tool_123",
                            "name": "search",
                            "args": {"query": "test"},
                        }
                    }
                ],
                "STOP",
            ),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "tool_use" in events_str
        assert "search" in events_str
        assert "input_json_delta" in events_str

    async def test_thinking_before_tool_use(self):
        """Thinking before tool use should be handled correctly"""
        lines = [
            make_antigravity_sse_data([{"thought": True, "text": "I need to search."}]),
            make_antigravity_sse_data(
                [
                    {
                        "functionCall": {
                            "name": "search",
                            "args": {"query": "test"},
                        }
                    }
                ],
                "STOP",
            ),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "assistant_thinking" in events_str
        assert "I need to search." in events_str
        assert "tool_use" in events_str


@pytest.mark.asyncio
class TestStreamingEdgeCases:
    """Tests for edge cases in streaming"""

    async def test_empty_text_parts_skipped(self):
        """Empty or whitespace-only text parts should be skipped"""
        lines = [
            make_antigravity_sse_data([{"text": "   "}]),  # Only whitespace
            make_antigravity_sse_data([{"text": "Real content."}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "Real content." in events_str

    async def test_message_start_sent(self):
        """message_start event should be sent"""
        lines = [
            make_antigravity_sse_data([{"text": "Hello"}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
            initial_input_tokens=50,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "message_start" in events_str

    async def test_message_stop_sent(self):
        """message_stop event should be sent at end"""
        lines = [
            make_antigravity_sse_data([{"text": "Done"}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "message_stop" in events_str

    async def test_stop_reason_end_turn(self):
        """stop_reason should be end_turn for normal completion"""
        lines = [
            make_antigravity_sse_data([{"text": "Done"}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert '"stop_reason":"end_turn"' in events_str

    async def test_stop_reason_tool_use(self):
        """stop_reason should be tool_use when tools are used"""
        lines = [
            make_antigravity_sse_data(
                [{"functionCall": {"name": "test", "args": {}}}], "STOP"
            ),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert '"stop_reason":"tool_use"' in events_str

    async def test_stop_reason_max_tokens(self):
        """stop_reason should be max_tokens when hitting limit"""
        lines = [
            make_antigravity_sse_data([{"text": "Truncated..."}], "MAX_TOKENS"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert '"stop_reason":"max_tokens"' in events_str

    async def test_inline_data_handled(self):
        """Inline data (images) should be handled"""
        lines = [
            make_antigravity_sse_data(
                [{"inlineData": {"mimeType": "image/png", "data": "base64data"}}],
                "STOP",
            ),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "image" in events_str
        assert "base64data" in events_str

    async def test_invalid_json_skipped(self):
        """Invalid JSON lines should be skipped gracefully"""
        lines = [
            "data: not valid json",
            make_antigravity_sse_data([{"text": "Valid content"}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "Valid content" in events_str

    async def test_done_marker_handled(self):
        """[DONE] marker should end stream"""
        lines = [
            make_antigravity_sse_data([{"text": "First"}]),
            "data: [DONE]",
            make_antigravity_sse_data([{"text": "Should not appear"}]),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "First" in events_str
        assert "Should not appear" not in events_str

    async def test_non_data_lines_skipped(self):
        """Lines not starting with 'data: ' should be skipped"""
        lines = [
            "event: ping",
            ": comment",
            "",
            make_antigravity_sse_data([{"text": "Content"}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "Content" in events_str


@pytest.mark.asyncio
class TestMultipleThinkingBlocks:
    """Tests for multiple thinking blocks in sequence"""

    async def test_multiple_thinking_blocks_streaming(self):
        """Multiple thinking blocks should be handled correctly in streaming"""
        lines = [
            make_antigravity_sse_data([{"thought": True, "text": "First thought."}]),
            make_antigravity_sse_data([{"thought": True, "text": "Second thought."}]),
            make_antigravity_sse_data([{"text": "Final answer."}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=True,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "First thought." in events_str
        assert "Second thought." in events_str
        assert "Final answer." in events_str

    async def test_multiple_thinking_converted_to_text(self):
        """Multiple thinking blocks should be buffered and converted to text"""
        lines = [
            make_antigravity_sse_data([{"thought": True, "text": "First."}]),
            make_antigravity_sse_data([{"thought": True, "text": "Second."}]),
            make_antigravity_sse_data([{"text": "Answer."}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="claude-opus-4-5",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "First." in events_str
        assert "Second." in events_str
        assert "Answer." in events_str
        assert "assistant_thinking" in events_str


@pytest.mark.asyncio
class TestUsageMetadataHandling:
    """Tests for usage metadata extraction from responses"""

    async def test_usage_from_response_level(self):
        """Usage metadata should be extracted from response level"""
        data = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Hello"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 150, "candidatesTokenCount": 75},
            }
        }
        lines = [f"data: {json.dumps(data)}"]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        # Check that usage is included in message_delta
        assert '"input_tokens":150' in events_str or "input_tokens" in events_str

    async def test_usage_from_candidate_level(self):
        """Usage metadata should prefer candidate level if more complete"""
        data = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Hello"}]},
                        "finishReason": "STOP",
                        "usageMetadata": {
                            "promptTokenCount": 200,
                            "candidatesTokenCount": 100,
                            "totalTokenCount": 300,
                        },
                    }
                ],
                "usageMetadata": {"promptTokenCount": 200},
            }
        }
        lines = [f"data: {json.dumps(data)}"]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "message_delta" in events_str

    async def test_invalid_usage_metadata_handled(self):
        """Non-dict usage metadata should be handled gracefully"""
        data = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Hello"}]},
                        "finishReason": "STOP",
                        "usageMetadata": "invalid",  # Not a dict
                    }
                ],
                "usageMetadata": None,
            }
        }
        lines = [f"data: {json.dumps(data)}"]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
            initial_input_tokens=50,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "message_start" in events_str

    async def test_fallback_input_tokens(self):
        """Should use initial_input_tokens as fallback"""
        data = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Hello"}]},
                        "finishReason": "STOP",
                    }
                ],
            }
        }
        lines = [f"data: {json.dumps(data)}"]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
            initial_input_tokens=999,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        # Fallback should be used
        assert "message_start" in events_str


@pytest.mark.asyncio
class TestCredentialManagerIntegration:
    """Tests for credential manager integration"""

    async def test_success_recorded_on_first_valid_data(self):
        """Credential manager should record success on first valid data"""

        class MockCredentialManager:
            def __init__(self):
                self.recorded = False
                self.success = None

            async def record_api_call_result(self, name, success, is_antigravity=False):
                self.recorded = True
                self.success = success

        mock_cm = MockCredentialManager()

        lines = [
            make_antigravity_sse_data([{"text": "Hello"}], "STOP"),
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
            credential_manager=mock_cm,
            credential_name="test_cred",
        ):
            events.append(event)

        assert mock_cm.recorded is True
        assert mock_cm.success is True


@pytest.mark.asyncio
class TestSignatureHandling:
    """Tests for thinking signature handling in streaming"""

    async def test_late_signature_delta(self):
        """Signature arriving after thinking block start should emit signature_delta"""
        # First chunk: thinking block without signature
        data1 = {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"thought": True, "text": "Thinking..."}]
                        },
                        "usageMetadata": {
                            "promptTokenCount": 100,
                            "candidatesTokenCount": 50,
                        },
                    }
                ],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
            }
        }
        # Second chunk: signature arrives
        data2 = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"thoughtSignature": "late_sig"}]},
                    }
                ],
            }
        }
        # Third chunk: finish
        data3 = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Done."}]},
                        "finishReason": "STOP",
                    }
                ],
            }
        }

        lines = [
            f"data: {json.dumps(data1)}",
            f"data: {json.dumps(data2)}",
            f"data: {json.dumps(data3)}",
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
            client_thinking_enabled=True,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "late_sig" in events_str


@pytest.mark.asyncio
class TestPendingOutputHandling:
    """Tests for pending output buffering before message_start"""

    async def test_events_buffered_before_message_start(self):
        """Events should be buffered until we have usage metadata for message_start"""
        # Response without usage metadata initially
        data1 = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Hello"}]},
                    }
                ],
            }
        }
        # Response with usage metadata
        data2 = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": " World"}]},
                        "finishReason": "STOP",
                        "usageMetadata": {
                            "promptTokenCount": 100,
                            "candidatesTokenCount": 50,
                        },
                    }
                ],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
            }
        }

        lines = [
            f"data: {json.dumps(data1)}",
            f"data: {json.dumps(data2)}",
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        # message_start should come first
        msg_start_pos = events_str.find("message_start")
        msg_delta_pos = events_str.find("message_delta")
        assert msg_start_pos < msg_delta_pos


@pytest.mark.asyncio
class TestStreamingErrorHandling:
    """Tests for error handling during streaming"""

    async def test_exception_during_streaming_emits_error_event(self):
        """Exceptions during streaming should emit error SSE event"""

        class ExceptionIterator:
            """Iterator that raises an exception"""

            def __init__(self, lines):
                self.lines = lines
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.lines):
                    raise StopAsyncIteration
                line = self.lines[self.index]
                self.index += 1
                if line == "RAISE_ERROR":
                    raise RuntimeError("Test error during streaming")
                return line

        lines = [
            make_antigravity_sse_data([{"text": "Start"}]),
            "RAISE_ERROR",
        ]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            ExceptionIterator(lines),
            model="test",
            message_id="msg_error",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        # Should emit error event
        assert "error" in events_str
        assert "Test error during streaming" in events_str

    async def test_exception_before_message_start_still_emits_message_start(self):
        """Error before message_start should still emit message_start first"""

        class ImmediateExceptionIterator:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise RuntimeError("Immediate error")

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            ImmediateExceptionIterator(),
            model="test",
            message_id="msg_error",
            initial_input_tokens=100,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        # message_start should come before error
        msg_start_pos = events_str.find("message_start")
        error_pos = events_str.find('"type":"error"')
        assert msg_start_pos != -1, "message_start should be present"
        assert error_pos != -1, "error should be present"
        assert msg_start_pos < error_pos, "message_start should come before error"


@pytest.mark.asyncio
class TestThinkingBufferFlush:
    """Tests for thinking buffer flushing at stream end"""

    async def test_thinking_only_stream_flush_to_text(self):
        """Thinking-only content with thinking_to_text should flush at end"""
        data = {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"thought": True, "text": "Deep thought here"}]
                        },
                        "finishReason": "STOP",
                        "usageMetadata": {
                            "promptTokenCount": 100,
                            "candidatesTokenCount": 50,
                        },
                    }
                ],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
            }
        }
        lines = [f"data: {json.dumps(data)}"]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
            client_thinking_enabled=False,
            thinking_to_text=True,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        # Should contain the thinking wrapped in tags
        assert "assistant_thinking" in events_str
        assert "Deep thought here" in events_str


@pytest.mark.asyncio
class TestTokenEstimationEdgeCases:
    """Tests for token estimation edge cases"""

    async def test_invalid_initial_input_tokens_handled(self):
        """Invalid initial_input_tokens should be handled gracefully"""
        data = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Hello"}]},
                        "finishReason": "STOP",
                    }
                ],
            }
        }
        lines = [f"data: {json.dumps(data)}"]

        events = []
        # Pass a string that can't be converted to int
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
            initial_input_tokens="invalid",  # type: ignore
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        # Should still work with fallback to 0
        assert "message_start" in events_str
        assert "Hello" in events_str

    async def test_negative_initial_input_tokens_handled(self):
        """Negative initial_input_tokens should be clamped to 0"""
        data = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Hi"}]},
                        "finishReason": "STOP",
                    }
                ],
            }
        }
        lines = [f"data: {json.dumps(data)}"]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
            initial_input_tokens=-50,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "message_start" in events_str


@pytest.mark.asyncio
class TestMalformedResponseHandling:
    """Tests for handling malformed upstream responses"""

    async def test_none_response_handled(self):
        """None response should be handled gracefully"""
        data = {"response": None}
        lines = [f"data: {json.dumps(data)}"]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
            initial_input_tokens=100,
        ):
            events.append(event)

        # Should complete without error
        events_str = b"".join(events).decode("utf-8")
        assert "message_start" in events_str
        assert "message_stop" in events_str

    async def test_empty_candidates_handled(self):
        """Empty candidates array should be handled gracefully"""
        data = {"response": {"candidates": []}}
        lines = [f"data: {json.dumps(data)}"]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
            initial_input_tokens=100,
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "message_start" in events_str

    async def test_non_dict_part_skipped(self):
        """Non-dict parts should be skipped gracefully"""
        data = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": ["not a dict", {"text": "Valid"}]},
                        "finishReason": "STOP",
                        "usageMetadata": {
                            "promptTokenCount": 100,
                            "candidatesTokenCount": 50,
                        },
                    }
                ],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
            }
        }
        lines = [f"data: {json.dumps(data)}"]

        events = []
        async for event in antigravity_sse_to_anthropic_sse(
            AsyncLinesIterator(lines),
            model="test",
            message_id="msg_123",
        ):
            events.append(event)

        events_str = b"".join(events).decode("utf-8")
        assert "Valid" in events_str


# Run tests with: python -m pytest tests/test_streaming_thinking.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
