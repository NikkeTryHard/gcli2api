"""
Shared helper functions for Anthropic API handling.

These utilities are used across multiple modules:
- antigravity_anthropic_router.py
- anthropic_streaming.py
- anthropic_converter.py
"""

import os
from typing import Any, Dict

# Debug flag values that are considered "true"
DEBUG_TRUE = {"1", "true", "yes", "on"}


def remove_nulls_for_tool_input(value: Any) -> Any:
    """
    Recursively remove null/None values from dict/list structures.

    Background: Roo/Kilo in Anthropic native tool path may treat null in
    tool_use.input as actual parameters (e.g., "search in null").
    This function cleans input before output.

    Args:
        value: Any value (dict, list, or primitive)

    Returns:
        Cleaned value with None/null removed from dicts and lists
    """
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in value.items():
            if v is None:
                continue
            cleaned[k] = remove_nulls_for_tool_input(v)
        return cleaned

    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            if item is None:
                continue
            cleaned_list.append(remove_nulls_for_tool_input(item))
        return cleaned_list

    return value


def anthropic_debug_enabled() -> bool:
    """
    Check if Anthropic debug logging is enabled.

    Controlled by ANTHROPIC_DEBUG environment variable.
    Accepts: "1", "true", "yes", "on" (case-insensitive)

    Returns:
        True if debug is enabled, False otherwise
    """
    return str(os.getenv("ANTHROPIC_DEBUG", "")).strip().lower() in DEBUG_TRUE
