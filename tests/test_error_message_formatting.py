"""
Tests for error message formatting to ensure meaningful error messages.

These tests verify that exception logging includes the exception type,
especially for exceptions like httpx timeouts that have empty string representations.
"""

import pytest
import sys

sys.path.insert(0, "/home/louiskaneko/dev/ccr-forge/gcli2api")


class TestErrorMessageFormatting:
    """Tests for error message formatting with empty exception messages"""

    def test_httpx_timeout_has_empty_str(self):
        """Verify that httpx timeout exceptions have empty str representation"""
        import httpx

        # This is the root cause of the issue - httpx timeouts have empty str
        exc = httpx.ReadTimeout("")
        assert str(exc) == ""
        assert type(exc).__name__ == "ReadTimeout"

    def test_httpx_connect_timeout_has_empty_str(self):
        """Verify that httpx ConnectTimeout has empty str representation"""
        import httpx

        exc = httpx.ConnectTimeout("")
        assert str(exc) == ""
        assert type(exc).__name__ == "ConnectTimeout"

    def test_error_msg_fallback_pattern(self):
        """Test the error message fallback pattern used in antigravity_api.py"""
        import httpx

        # Simulate the pattern used in the code
        def format_error(e: Exception) -> str:
            error_msg = str(e) or type(e).__name__
            return f"{type(e).__name__}: {error_msg}"

        # Test with empty message exception
        exc = httpx.ReadTimeout("")
        result = format_error(exc)
        assert "ReadTimeout" in result
        assert result != ": "  # Should not be empty

        # Test with normal exception
        exc2 = ValueError("test error")
        result2 = format_error(exc2)
        assert "ValueError" in result2
        assert "test error" in result2

    def test_error_msg_with_regular_exception(self):
        """Test that regular exceptions still format correctly"""

        def format_error(e: Exception) -> str:
            error_msg = str(e) or type(e).__name__
            return f"{type(e).__name__}: {error_msg}"

        exc = Exception("Something went wrong")
        result = format_error(exc)
        assert "Exception" in result
        assert "Something went wrong" in result

    def test_error_msg_with_empty_regular_exception(self):
        """Test that even regular exceptions with empty messages are handled"""

        def format_error(e: Exception) -> str:
            error_msg = str(e) or type(e).__name__
            return f"{type(e).__name__}: {error_msg}"

        exc = Exception("")
        result = format_error(exc)
        assert "Exception" in result
        # Should fallback to type name
        assert result == "Exception: Exception"


class TestAntigravityApiErrorFormatting:
    """Integration tests for error formatting in antigravity_api.py"""

    def test_error_format_pattern_exists_in_code(self):
        """Verify the error formatting pattern exists in antigravity_api.py"""
        import os

        api_file = os.path.join(os.path.dirname(__file__), "..", "src", "antigravity_api.py")
        with open(api_file, "r") as f:
            content = f.read()

        # Check that the improved error formatting pattern is present
        assert "type(e).__name__" in content
        assert "error_msg = str(e) or type(e).__name__" in content

    def test_error_format_pattern_exists_in_anthropic_router(self):
        """Verify the error formatting pattern exists in antigravity_anthropic_router.py"""
        import os

        router_file = os.path.join(os.path.dirname(__file__), "..", "src", "antigravity_anthropic_router.py")
        with open(router_file, "r") as f:
            content = f.read()

        # Check that the improved error formatting pattern is present
        assert "type(e).__name__" in content
        assert "error_msg = str(e) or type(e).__name__" in content


class TestLogLevelForRateLimiting:
    """Tests for appropriate log levels for rate limiting (429) errors"""

    def test_429_logged_as_warning_in_antigravity_api(self):
        """Verify that 429 errors are logged as WARNING, not ERROR"""
        import os

        api_file = os.path.join(os.path.dirname(__file__), "..", "src", "antigravity_api.py")
        with open(api_file, "r") as f:
            content = f.read()

        # Check that 429 is logged as warning with appropriate message
        assert 'log.warning(f"[ANTIGRAVITY] Rate limited (429):' in content

        # Verify the pattern: 429 -> warning, other errors -> error
        assert "if response.status_code == 429:" in content
        assert "# 429 is expected rate limiting" in content
