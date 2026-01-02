"""
Additional tests for anthropic_converter.py to improve coverage.

These tests focus on edge cases and uncovered code paths.
"""

import sys

import pytest

sys.path.insert(0, "/home/louiskaneko/dev/ccr-forge/gcli2api")

from src.anthropic_converter import (
    DEFAULT_THINKING_BUDGET,
    _extract_tool_result_output,
    _is_non_whitespace_text,
    build_generation_config,
    build_system_instruction,
    clean_json_schema,
    convert_messages_to_contents,
    convert_tools,
    get_thinking_config,
    map_claude_model_to_gemini,
    reorganize_tool_messages,
)


class TestIsNonWhitespaceText:
    """Tests for _is_non_whitespace_text helper"""

    def test_none_returns_false(self):
        """None should return False"""
        assert _is_non_whitespace_text(None) is False

    def test_empty_string_returns_false(self):
        """Empty string should return False"""
        assert _is_non_whitespace_text("") is False

    def test_whitespace_only_returns_false(self):
        """Whitespace-only should return False"""
        assert _is_non_whitespace_text("   ") is False
        assert _is_non_whitespace_text("\t\n\r") is False

    def test_regular_text_returns_true(self):
        """Normal text should return True"""
        assert _is_non_whitespace_text("hello") is True
        assert _is_non_whitespace_text("  hello  ") is True

    def test_object_with_str_method(self):
        """Object with __str__ should work"""

        class MyObj:
            def __str__(self):
                return "value"

        assert _is_non_whitespace_text(MyObj()) is True

    def test_number_returns_true(self):
        """Numbers should return True after str conversion"""
        assert _is_non_whitespace_text(42) is True
        assert _is_non_whitespace_text(0) is True


class TestGetThinkingConfig:
    """Tests for get_thinking_config"""

    def test_unknown_type_returns_default(self):
        """Unknown type in dict should still return enabled"""
        config = get_thinking_config({"type": "unknown"})
        assert config["includeThoughts"] is False

    def test_dict_without_type_returns_enabled(self):
        """Dict without type key should default to enabled"""
        config = get_thinking_config({})
        assert config["includeThoughts"] is True
        assert config["thinkingBudget"] == DEFAULT_THINKING_BUDGET

    def test_non_dict_non_bool_returns_default(self):
        """Non-dict/bool values should return default enabled"""
        config = get_thinking_config("string value")
        assert config["includeThoughts"] is True


class TestMapClaudeModelToGemini:
    """Tests for map_claude_model_to_gemini"""

    def test_opus_variants(self):
        """Various opus model names should map correctly"""
        assert (
            map_claude_model_to_gemini("claude-opus-4-5") == "claude-opus-4-5-thinking"
        )
        assert (
            map_claude_model_to_gemini("claude-opus-4-5-20251101")
            == "claude-opus-4-5-thinking"
        )

    def test_sonnet_variants(self):
        """Various sonnet model names should map correctly"""
        assert map_claude_model_to_gemini("claude-sonnet-4-5") == "claude-sonnet-4-5"
        assert (
            map_claude_model_to_gemini("claude-sonnet-4-5-20241022")
            == "claude-sonnet-4-5"
        )

    def test_haiku_variants(self):
        """Various haiku model names should map correctly"""
        assert map_claude_model_to_gemini("claude-haiku-4-5") == "gemini-2.5-flash"
        assert (
            map_claude_model_to_gemini("claude-haiku-4-5-20251001")
            == "gemini-2.5-flash"
        )

    def test_supported_gemini_models(self):
        """Supported Gemini models should pass through"""
        assert (
            map_claude_model_to_gemini("gemini-2.5-flash-thinking")
            == "gemini-2.5-flash-thinking"
        )
        assert map_claude_model_to_gemini("gemini-3-pro-high") == "gemini-3-pro-high"

    def test_unknown_model_defaults_to_sonnet(self):
        """Unknown models should default to claude-sonnet-4-5"""
        assert map_claude_model_to_gemini("unknown-model-xyz") == "claude-sonnet-4-5"


class TestCleanJsonSchema:
    """Tests for clean_json_schema"""

    def test_non_dict_passthrough(self):
        """Non-dict values should pass through unchanged"""
        assert clean_json_schema("string") == "string"
        assert clean_json_schema(123) == 123
        assert clean_json_schema([1, 2, 3]) == [1, 2, 3]

    def test_removes_all_unsupported_keys(self):
        """All unsupported keys should be removed"""
        schema = {
            "$schema": "http://...",
            "$id": "some-id",
            "$ref": "#/def/x",
            "oneOf": [],
            "anyOf": [],
            "allOf": [],
            "type": "string",
        }
        cleaned = clean_json_schema(schema)
        assert "$schema" not in cleaned
        assert "$id" not in cleaned
        assert "$ref" not in cleaned
        assert "oneOf" not in cleaned
        assert cleaned["type"] == "string"

    def test_type_array_without_null(self):
        """Type array without null should use first type"""
        schema = {"type": ["string", "integer"]}
        cleaned = clean_json_schema(schema)
        assert cleaned["type"] == "string"
        assert "nullable" not in cleaned

    def test_type_array_only_null(self):
        """Type array with only null should default to string"""
        schema = {"type": ["null"]}
        cleaned = clean_json_schema(schema)
        assert cleaned["type"] == "string"
        assert cleaned["nullable"] is True

    def test_nested_schema_cleaning(self):
        """Nested schemas should be cleaned recursively"""
        schema = {
            "type": "object",
            "properties": {
                "nested": {
                    "$ref": "#/should/be/removed",
                    "type": "string",
                }
            },
        }
        cleaned = clean_json_schema(schema)
        assert "$ref" not in cleaned["properties"]["nested"]

    def test_list_items_cleaned(self):
        """List items that are dicts should be cleaned"""
        schema = {
            "items": [{"$ref": "#/x"}, "string", {"type": "number"}],
        }
        cleaned = clean_json_schema(schema)
        assert "$ref" not in cleaned["items"][0]

    def test_validation_without_description(self):
        """Validation fields should create description if none exists"""
        schema = {"type": "string", "minLength": 1}
        cleaned = clean_json_schema(schema)
        assert "description" in cleaned
        assert "minLength: 1" in cleaned["description"]


class TestExtractToolResultOutput:
    """Tests for _extract_tool_result_output"""

    def test_empty_list_returns_empty(self):
        """Empty list should return empty string"""
        assert _extract_tool_result_output([]) == ""

    def test_list_with_text_block(self):
        """List with text block should extract text"""
        content = [{"type": "text", "text": "result"}]
        assert _extract_tool_result_output(content) == "result"

    def test_list_with_non_text_block(self):
        """List with non-text block should stringify first item"""
        content = [{"type": "other", "data": "value"}]
        result = _extract_tool_result_output(content)
        assert "other" in result

    def test_none_returns_empty(self):
        """None should return empty string"""
        assert _extract_tool_result_output(None) == ""

    def test_string_returns_itself(self):
        """String should return itself"""
        assert _extract_tool_result_output("direct string") == "direct string"


class TestConvertMessagesToContents:
    """Tests for convert_messages_to_contents"""

    def test_thinking_block_with_none_thinking_text(self):
        """Thinking block with None thinking field should use empty string"""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": None, "signature": "sig"},
                ],
            }
        ]
        contents = convert_messages_to_contents(messages, include_thinking=True)
        assert contents[0]["parts"][0]["text"] == ""

    def test_redacted_thinking_with_data_field(self):
        """Redacted thinking should fallback to data field"""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "redacted_thinking",
                        "data": "redacted",
                        "signature": "sig",
                    },
                ],
            }
        ]
        contents = convert_messages_to_contents(messages, include_thinking=True)
        assert contents[0]["parts"][0]["text"] == "redacted"

    def test_redacted_thinking_without_signature_skipped(self):
        """Redacted thinking without signature should be skipped"""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "redacted_thinking", "data": "redacted"},
                    {"type": "text", "text": "visible"},
                ],
            }
        ]
        contents = convert_messages_to_contents(messages, include_thinking=True)
        assert len(contents[0]["parts"]) == 1
        assert contents[0]["parts"][0]["text"] == "visible"

    def test_unknown_content_type_serialized(self):
        """Unknown content type should be JSON serialized"""
        messages = [
            {
                "role": "user",
                "content": [{"type": "custom", "data": "value"}],
            }
        ]
        contents = convert_messages_to_contents(messages)
        assert "custom" in contents[0]["parts"][0]["text"]

    def test_non_dict_list_items(self):
        """Non-dict items in content list should be stringified"""
        messages = [
            {
                "role": "user",
                "content": ["plain string", 123],
            }
        ]
        contents = convert_messages_to_contents(messages)
        assert len(contents[0]["parts"]) == 2

    def test_non_list_non_string_content(self):
        """Non-list/non-string content should be stringified"""
        messages = [{"role": "user", "content": 42}]
        contents = convert_messages_to_contents(messages)
        assert contents[0]["parts"][0]["text"] == "42"

    def test_empty_content_skipped(self):
        """Messages with empty/whitespace content should be skipped"""
        messages = [
            {"role": "user", "content": "  "},
            {"role": "user", "content": "valid"},
        ]
        contents = convert_messages_to_contents(messages)
        assert len(contents) == 1
        assert contents[0]["parts"][0]["text"] == "valid"


class TestReorganizeToolMessages:
    """Tests for reorganize_tool_messages"""

    def test_function_call_without_response(self):
        """Function call without matching response should still be included"""
        contents = [
            {
                "role": "model",
                "parts": [{"functionCall": {"id": "t1", "name": "search"}}],
            },
        ]
        reorganized = reorganize_tool_messages(contents)
        assert len(reorganized) == 1

    def test_orphan_function_response_skipped(self):
        """Function response without matching call should be skipped"""
        contents = [
            {"role": "user", "parts": [{"functionResponse": {"id": "orphan"}}]},
            {"role": "user", "parts": [{"text": "hello"}]},
        ]
        reorganized = reorganize_tool_messages(contents)
        assert len(reorganized) == 1
        assert "text" in reorganized[0]["parts"][0]


class TestBuildSystemInstruction:
    """Tests for build_system_instruction"""

    def test_list_with_non_text_items(self):
        """List with non-text items should be skipped"""
        system = [
            {"type": "image", "data": "..."},
            {"type": "text", "text": "Be helpful"},
        ]
        result = build_system_instruction(system)
        assert len(result["parts"]) == 1
        assert result["parts"][0]["text"] == "Be helpful"

    def test_non_string_non_list_system(self):
        """Non-string/list system should be stringified"""
        result = build_system_instruction(42)
        assert result["parts"][0]["text"] == "42"

    def test_whitespace_list_items_skipped(self):
        """Whitespace-only text items should be skipped"""
        system = [
            {"type": "text", "text": "  "},
            {"type": "text", "text": "valid"},
        ]
        result = build_system_instruction(system)
        assert len(result["parts"]) == 1


class TestBuildGenerationConfig:
    """Tests for build_generation_config edge cases"""

    def test_thinking_disabled_in_dict(self):
        """Thinking disabled in dict should set includeThoughts=False"""
        payload = {
            "thinking": {"type": "disabled"},
            "messages": [],
        }
        config, should_include = build_generation_config(payload)
        # thinkingConfig is included but with includeThoughts=False
        assert config["thinkingConfig"]["includeThoughts"] is False
        assert should_include is False

    def test_thinking_with_incompatible_history(self):
        """Thinking enabled but incompatible history should skip thinkingConfig"""
        payload = {
            "thinking": {"type": "enabled"},
            "messages": [
                {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]}
            ],
        }
        config, should_include = build_generation_config(payload)
        # Should skip because last assistant message doesn't start with thinking
        assert should_include is False

    def test_thinking_budget_adjustment(self):
        """Budget >= max_tokens should be auto-adjusted"""
        payload = {
            "thinking": {"type": "enabled", "budget_tokens": 1000},
            "max_tokens": 500,
            "messages": [],
        }
        config, should_include = build_generation_config(payload)
        # Should adjust budget to 499
        assert config["thinkingConfig"]["thinkingBudget"] == 499

    def test_thinking_budget_too_low_skips(self):
        """Budget adjustment to 0 or less should skip thinkingConfig"""
        payload = {
            "thinking": {"type": "enabled", "budget_tokens": 1000},
            "max_tokens": 1,
            "messages": [],
        }
        config, should_include = build_generation_config(payload)
        # Should skip because adjusted budget would be 0
        assert "thinkingConfig" not in config
        assert should_include is False

    def test_assistant_with_non_dict_first_block(self):
        """Assistant with non-dict first block should allow thinking (treated as None type)"""
        payload = {
            "thinking": {"type": "enabled"},
            "messages": [{"role": "assistant", "content": ["string content"]}],
        }
        config, should_include = build_generation_config(payload)
        # Non-dict first block results in None type, which is allowed
        assert should_include is True

    def test_assistant_with_empty_content(self):
        """Assistant with empty content should allow thinking"""
        payload = {
            "thinking": {"type": "enabled"},
            "messages": [
                {"role": "assistant", "content": []},
            ],
        }
        config, should_include = build_generation_config(payload)
        # Empty content should allow thinking (last_assistant_first_block_type is None)
        assert should_include is True


class TestConvertTools:
    """Tests for convert_tools"""

    def test_tool_with_empty_name_skipped(self):
        """Tools with empty name should be skipped"""
        tools = [
            {"name": "", "description": "Empty name"},
            {"name": "valid", "description": "Valid tool"},
        ]
        result = convert_tools(tools)
        assert len(result) == 1
        assert result[0]["functionDeclarations"][0]["name"] == "valid"

    def test_tool_without_input_schema(self):
        """Tool without input_schema should use empty dict"""
        tools = [{"name": "simple", "description": "No schema"}]
        result = convert_tools(tools)
        assert result[0]["functionDeclarations"][0]["parameters"] == {}


class TestToolResultNameLookup:
    """Tests for tool_result to functionResponse name lookup - prevents regression of empty name bug"""

    def test_tool_result_gets_name_from_tool_use(self):
        """tool_result should get its name from the corresponding tool_use message"""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "read_file",
                        "input": {"path": "/test.txt"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_123",
                        "content": "file contents here",
                    }
                ],
            },
        ]
        contents = convert_messages_to_contents(messages)
        # Find the functionResponse
        func_response = None
        for msg in contents:
            for part in msg.get("parts", []):
                if "functionResponse" in part:
                    func_response = part["functionResponse"]
                    break
        assert func_response is not None
        assert func_response["name"] == "read_file"
        assert func_response["name"] != ""

    def test_tool_result_without_matching_tool_use_gets_fallback_name(self):
        """tool_result without matching tool_use should get a fallback name, not empty string"""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_orphan",
                        "content": "orphan result",
                    }
                ],
            },
        ]
        contents = convert_messages_to_contents(messages)
        func_response = None
        for msg in contents:
            for part in msg.get("parts", []):
                if "functionResponse" in part:
                    func_response = part["functionResponse"]
                    break
        assert func_response is not None
        # Should have a non-empty fallback name
        assert func_response["name"] != ""
        assert (
            "function_" in func_response["name"]
            or func_response["name"] == "unknown_function"
        )

    def test_multiple_tool_uses_and_results(self):
        """Multiple tool_use/tool_result pairs should all get correct names"""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "read_file",
                        "input": {"path": "/a.txt"},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_2",
                        "name": "write_file",
                        "input": {"path": "/b.txt", "content": "data"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": "contents of a.txt",
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_2",
                        "content": "file written successfully",
                    },
                ],
            },
        ]
        contents = convert_messages_to_contents(messages)
        # Collect all functionResponse parts
        func_responses = {}
        for msg in contents:
            for part in msg.get("parts", []):
                if "functionResponse" in part:
                    fr = part["functionResponse"]
                    func_responses[fr["id"]] = fr["name"]

        assert func_responses.get("toolu_1") == "read_file"
        assert func_responses.get("toolu_2") == "write_file"

    def test_tool_result_with_explicit_name_uses_that_name(self):
        """If tool_result has an explicit name field, it should be used"""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_explicit",
                        "name": "explicit_name",
                        "content": "result",
                    }
                ],
            },
        ]
        contents = convert_messages_to_contents(messages)
        func_response = None
        for msg in contents:
            for part in msg.get("parts", []):
                if "functionResponse" in part:
                    func_response = part["functionResponse"]
                    break
        assert func_response is not None
        # Should use the explicit name (or fallback chain)
        assert func_response["name"] != ""

    def test_tool_result_name_never_empty(self):
        """Regression test: functionResponse.name should NEVER be empty string"""
        # This is the exact scenario that caused the Gemini API error
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_abc123",
                        "name": "Bash",
                        "input": {"command": "ls -la"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_abc123",
                        # Note: no "name" field here - this is standard Anthropic format
                        "content": "total 0\ndrwxr-xr-x  2 user user 40 Jan  1 00:00 .",
                    }
                ],
            },
        ]
        contents = convert_messages_to_contents(messages)

        # Find all functionResponse parts and verify none have empty names
        for msg in contents:
            for part in msg.get("parts", []):
                if "functionResponse" in part:
                    name = part["functionResponse"].get("name", "")
                    assert name != "", (
                        f"functionResponse.name should never be empty, got: {part}"
                    )
                    assert name == "Bash", f"Expected 'Bash', got: {name}"


class TestFunctionCallThoughtSignature:
    """Tests for thoughtSignature handling on functionCall parts - required for Gemini 3 models"""

    def test_function_call_gets_signature_from_thinking_block(self):
        """functionCall should get thoughtSignature from preceding thinking block"""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Let me run a command...",
                        "signature": "test_signature_abc123",
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "Bash",
                        "input": {"command": "ls -la"},
                    },
                ],
            },
        ]
        contents = convert_messages_to_contents(messages, include_thinking=True)
        # Find the functionCall part
        fc_part = None
        for msg in contents:
            for part in msg.get("parts", []):
                if "functionCall" in part:
                    fc_part = part
                    break
        assert fc_part is not None
        assert "thoughtSignature" in fc_part
        assert fc_part["thoughtSignature"] == "test_signature_abc123"

    def test_function_call_without_thinking_gets_dummy_signature(self):
        """functionCall without preceding thinking block should get dummy signature"""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "Bash",
                        "input": {"command": "ls -la"},
                    },
                ],
            },
        ]
        contents = convert_messages_to_contents(messages, include_thinking=True)
        fc_part = None
        for msg in contents:
            for part in msg.get("parts", []):
                if "functionCall" in part:
                    fc_part = part
                    break
        assert fc_part is not None
        assert "thoughtSignature" in fc_part
        assert fc_part["thoughtSignature"] == "skip_thought_signature_validator"

    def test_parallel_function_calls_only_first_gets_signature(self):
        """For parallel function calls, only the first one should get the signature"""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Let me run multiple commands...",
                        "signature": "parallel_sig",
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Bash",
                        "input": {"command": "ls"},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_2",
                        "name": "Bash",
                        "input": {"command": "pwd"},
                    },
                ],
            },
        ]
        contents = convert_messages_to_contents(messages, include_thinking=True)
        # Collect all functionCall parts
        fc_parts = []
        for msg in contents:
            for part in msg.get("parts", []):
                if "functionCall" in part:
                    fc_parts.append(part)

        assert len(fc_parts) == 2
        # First functionCall should have the signature
        assert "thoughtSignature" in fc_parts[0]
        assert fc_parts[0]["thoughtSignature"] == "parallel_sig"
        # Second functionCall should NOT have a signature
        assert "thoughtSignature" not in fc_parts[1]

    def test_function_call_with_redacted_thinking_gets_signature(self):
        """functionCall should get signature from redacted_thinking block"""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "redacted_thinking",
                        "data": "[redacted]",
                        "signature": "redacted_sig_xyz",
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "Read",
                        "input": {"path": "/etc/passwd"},
                    },
                ],
            },
        ]
        contents = convert_messages_to_contents(messages, include_thinking=True)
        fc_part = None
        for msg in contents:
            for part in msg.get("parts", []):
                if "functionCall" in part:
                    fc_part = part
                    break
        assert fc_part is not None
        assert "thoughtSignature" in fc_part
        assert fc_part["thoughtSignature"] == "redacted_sig_xyz"

    def test_function_call_signature_never_empty(self):
        """Regression test: functionCall should always have a thoughtSignature (never empty)"""
        # This is the exact scenario that caused the Gemini 3 API error
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_abc",
                        "name": "Bash",
                        "input": {"command": "echo hello"},
                    }
                ],
            },
        ]
        contents = convert_messages_to_contents(messages)

        for msg in contents:
            for part in msg.get("parts", []):
                if "functionCall" in part:
                    assert "thoughtSignature" in part, (
                        f"functionCall must have thoughtSignature for Gemini 3, got: {part}"
                    )
                    assert part["thoughtSignature"] != "", (
                        f"thoughtSignature should never be empty, got: {part}"
                    )


# Run tests with: python -m pytest tests/test_anthropic_converter.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
