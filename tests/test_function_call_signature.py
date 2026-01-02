"""
Tests for thoughtSignature in functionCall parts.

Gemini 3 models require a thoughtSignature on functionCall parts.
These tests ensure that all code paths that create functionCall parts
include the required thoughtSignature field.

See: https://ai.google.dev/gemini-api/docs/thought-signatures
"""

import json
import sys

import pytest

sys.path.insert(0, "/home/louiskaneko/dev/ccr-forge/gcli2api")

from src.antigravity_router import openai_messages_to_antigravity_contents
from src.openai_transfer import openai_request_to_gemini_payload
from src.models import (
    ChatCompletionRequest,
    OpenAIChatMessage,
    OpenAIToolCall,
    OpenAIToolFunction,
)


class TestAntigravityRouterFunctionCallSignature:
    """Tests for thoughtSignature in antigravity_router.py"""

    def test_function_call_has_thought_signature(self):
        """functionCall parts should have thoughtSignature"""
        # Create a message with tool_calls
        messages = [
            type(
                "Message",
                (),
                {
                    "role": "user",
                    "content": "Hello",
                    "tool_calls": None,
                    "tool_call_id": None,
                },
            )(),
            type(
                "Message",
                (),
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        type(
                            "ToolCall",
                            (),
                            {
                                "id": "call_123",
                                "function": type(
                                    "Function",
                                    (),
                                    {
                                        "name": "test_function",
                                        "arguments": '{"arg": "value"}',
                                    },
                                )(),
                            },
                        )()
                    ],
                    "tool_call_id": None,
                },
            )(),
        ]

        contents = openai_messages_to_antigravity_contents(messages)

        # Find the model message with functionCall
        model_messages = [c for c in contents if c.get("role") == "model"]
        assert len(model_messages) == 1

        parts = model_messages[0].get("parts", [])
        function_call_parts = [p for p in parts if "functionCall" in p]
        assert len(function_call_parts) == 1

        # Verify thoughtSignature is present
        fc_part = function_call_parts[0]
        assert "thoughtSignature" in fc_part
        assert fc_part["thoughtSignature"] == "skip_thought_signature_validator"

    def test_multiple_function_calls_have_thought_signatures(self):
        """Multiple functionCall parts should all have thoughtSignature"""
        messages = [
            type(
                "Message",
                (),
                {
                    "role": "user",
                    "content": "Hello",
                    "tool_calls": None,
                    "tool_call_id": None,
                },
            )(),
            type(
                "Message",
                (),
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        type(
                            "ToolCall",
                            (),
                            {
                                "id": "call_1",
                                "function": type(
                                    "Function",
                                    (),
                                    {"name": "func1", "arguments": "{}"},
                                )(),
                            },
                        )(),
                        type(
                            "ToolCall",
                            (),
                            {
                                "id": "call_2",
                                "function": type(
                                    "Function",
                                    (),
                                    {"name": "func2", "arguments": "{}"},
                                )(),
                            },
                        )(),
                    ],
                    "tool_call_id": None,
                },
            )(),
        ]

        contents = openai_messages_to_antigravity_contents(messages)

        model_messages = [c for c in contents if c.get("role") == "model"]
        assert len(model_messages) == 1

        parts = model_messages[0].get("parts", [])
        function_call_parts = [p for p in parts if "functionCall" in p]
        assert len(function_call_parts) == 2

        # All function call parts should have thoughtSignature
        for fc_part in function_call_parts:
            assert "thoughtSignature" in fc_part
            assert fc_part["thoughtSignature"] == "skip_thought_signature_validator"


class TestOpenAITransferFunctionCallSignature:
    """Tests for thoughtSignature in openai_transfer.py"""

    @pytest.mark.asyncio
    async def test_function_call_has_thought_signature(self):
        """functionCall parts should have thoughtSignature"""
        request = ChatCompletionRequest(
            model="gemini-2.5-flash",
            messages=[
                OpenAIChatMessage(role="user", content="Hello"),
                OpenAIChatMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        OpenAIToolCall(
                            id="call_123",
                            type="function",
                            function=OpenAIToolFunction(
                                name="test_function",
                                arguments='{"arg": "value"}',
                            ),
                        )
                    ],
                ),
            ],
        )

        result = await openai_request_to_gemini_payload(request)

        contents = result.get("request", {}).get("contents", [])
        model_messages = [c for c in contents if c.get("role") == "model"]
        assert len(model_messages) == 1

        parts = model_messages[0].get("parts", [])
        function_call_parts = [p for p in parts if "functionCall" in p]
        assert len(function_call_parts) == 1

        # Verify thoughtSignature is present
        fc_part = function_call_parts[0]
        assert "thoughtSignature" in fc_part
        assert fc_part["thoughtSignature"] == "skip_thought_signature_validator"

    @pytest.mark.asyncio
    async def test_multiple_function_calls_have_thought_signatures(self):
        """Multiple functionCall parts should all have thoughtSignature"""
        request = ChatCompletionRequest(
            model="gemini-2.5-flash",
            messages=[
                OpenAIChatMessage(role="user", content="Hello"),
                OpenAIChatMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        OpenAIToolCall(
                            id="call_1",
                            type="function",
                            function=OpenAIToolFunction(name="func1", arguments="{}"),
                        ),
                        OpenAIToolCall(
                            id="call_2",
                            type="function",
                            function=OpenAIToolFunction(name="func2", arguments="{}"),
                        ),
                    ],
                ),
            ],
        )

        result = await openai_request_to_gemini_payload(request)

        contents = result.get("request", {}).get("contents", [])
        model_messages = [c for c in contents if c.get("role") == "model"]
        assert len(model_messages) == 1

        parts = model_messages[0].get("parts", [])
        function_call_parts = [p for p in parts if "functionCall" in p]
        assert len(function_call_parts) == 2

        # All function call parts should have thoughtSignature
        for fc_part in function_call_parts:
            assert "thoughtSignature" in fc_part
            assert fc_part["thoughtSignature"] == "skip_thought_signature_validator"

    @pytest.mark.asyncio
    async def test_function_call_with_text_content(self):
        """functionCall with text content should have thoughtSignature"""
        request = ChatCompletionRequest(
            model="gemini-2.5-flash",
            messages=[
                OpenAIChatMessage(role="user", content="Hello"),
                OpenAIChatMessage(
                    role="assistant",
                    content="Let me call a function",
                    tool_calls=[
                        OpenAIToolCall(
                            id="call_123",
                            type="function",
                            function=OpenAIToolFunction(
                                name="test_function",
                                arguments='{"arg": "value"}',
                            ),
                        )
                    ],
                ),
            ],
        )

        result = await openai_request_to_gemini_payload(request)

        contents = result.get("request", {}).get("contents", [])
        model_messages = [c for c in contents if c.get("role") == "model"]
        assert len(model_messages) == 1

        parts = model_messages[0].get("parts", [])

        # Should have both text and functionCall parts
        text_parts = [p for p in parts if "text" in p]
        function_call_parts = [p for p in parts if "functionCall" in p]

        assert len(text_parts) == 1
        assert len(function_call_parts) == 1

        # Verify thoughtSignature is present on functionCall
        fc_part = function_call_parts[0]
        assert "thoughtSignature" in fc_part
        assert fc_part["thoughtSignature"] == "skip_thought_signature_validator"
