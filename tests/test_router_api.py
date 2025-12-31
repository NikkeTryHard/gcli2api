"""
Integration tests for antigravity_anthropic_router API endpoints.

These tests cover:
1. /antigravity/v1/messages endpoint - main message handling
2. /antigravity/v1/messages/count_tokens endpoint - token counting
3. Authentication, validation, and error handling
"""

import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/louiskaneko/dev/ccr-forge/gcli2api")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.antigravity_anthropic_router import router


# Helper to create password mock that patches at correct location
def create_password_patch(password: str):
    """Create a patch for get_api_password at config module level"""

    async def mock_get_password():
        return password

    return patch("config.get_api_password", mock_get_password)


def create_cred_manager_patch(credential_data=None):
    """Create a patch for get_credential_manager"""
    mock_cred_mgr = MagicMock()
    if credential_data is None:
        mock_cred_mgr.get_valid_credential = AsyncMock(return_value=None)
    else:
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", credential_data)
        )

    async def mock_get_cred_manager():
        return mock_cred_mgr

    return patch(
        "src.credential_manager.get_credential_manager", mock_get_cred_manager
    ), mock_cred_mgr


@pytest.fixture
def app():
    """Create test FastAPI app with router"""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


class TestAnthropicMessagesAuth:
    """Tests for authentication in /antigravity/v1/messages"""

    def test_missing_auth_returns_403(self, client):
        """Missing authentication should return 403"""
        with create_password_patch("correct_password"):
            response = client.post(
                "/antigravity/v1/messages",
                json={"model": "claude-3", "max_tokens": 1000, "messages": []},
            )
            assert response.status_code == 403

    def test_wrong_password_returns_403(self, client):
        """Wrong password should return 403"""
        with create_password_patch("correct_password"):
            response = client.post(
                "/antigravity/v1/messages",
                json={"model": "claude-3", "max_tokens": 1000, "messages": []},
                headers={"Authorization": "Bearer wrong_password"},
            )
            assert response.status_code == 403

    def test_correct_bearer_auth(self, client):
        """Correct bearer auth should pass authentication"""
        with create_password_patch("test_password"):
            response = client.post(
                "/antigravity/v1/messages",
                json={"model": "claude-3", "max_tokens": 1000, "messages": []},
                headers={"Authorization": "Bearer test_password"},
            )
            # Should pass auth, fail on validation or downstream
            assert response.status_code != 403

    def test_x_api_key_auth(self, client):
        """x-api-key header should work for auth"""
        with create_password_patch("api_key_value"):
            response = client.post(
                "/antigravity/v1/messages",
                json={"model": "claude-3", "max_tokens": 1000, "messages": []},
                headers={"x-api-key": "api_key_value"},
            )
            assert response.status_code != 403


class TestAnthropicMessagesValidation:
    """Tests for request validation in /antigravity/v1/messages"""

    def _auth_headers(self):
        return {"Authorization": "Bearer test_pw"}

    def test_invalid_json_returns_400(self, client):
        """Invalid JSON should return 400"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages",
                content="not valid json",
                headers={"Content-Type": "application/json", **self._auth_headers()},
            )
            assert response.status_code == 400
            assert "JSON" in response.json()["error"]["message"]

    def test_non_object_body_returns_400(self, client):
        """Non-object body should return 400"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages",
                json=["array", "not", "object"],
                headers=self._auth_headers(),
            )
            assert response.status_code == 400
            assert "object" in response.json()["error"]["message"]

    def test_missing_model_returns_400(self, client):
        """Missing model should return 400"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages",
                json={
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers=self._auth_headers(),
            )
            assert response.status_code == 400
            assert "model" in response.json()["error"]["message"]

    def test_missing_max_tokens_returns_400(self, client):
        """Missing max_tokens should return 400"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages",
                json={
                    "model": "claude-3",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers=self._auth_headers(),
            )
            assert response.status_code == 400
            assert "max_tokens" in response.json()["error"]["message"]

    def test_missing_messages_returns_400(self, client):
        """Missing messages should return 400"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages",
                json={"model": "claude-3", "max_tokens": 1000},
                headers=self._auth_headers(),
            )
            assert response.status_code == 400
            assert "messages" in response.json()["error"]["message"]


class TestAnthropicMessagesHiEndpoint:
    """Tests for the special 'Hi' response"""

    def test_hi_message_returns_canned_response(self, client):
        """Single 'Hi' message should return canned response"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages",
                json={
                    "model": "claude-3",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"Authorization": "Bearer test_pw"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["type"] == "message"
            assert data["role"] == "assistant"
            assert "antigravity" in data["content"][0]["text"]


class TestAnthropicMessagesNonStreaming:
    """Tests for non-streaming /antigravity/v1/messages"""

    def _auth_headers(self):
        return {"Authorization": "Bearer test_pw"}

    def test_successful_non_stream_request(self, client):
        """Successful non-streaming request should return message"""
        mock_response_data = {
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Hello!"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            }
        }

        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", {"project_id": "proj123"})
        )

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.return_value = {
                        "contents": [{"parts": [{"text": "test"}]}],
                        "model": "mapped-model",
                        "system_instruction": None,
                        "tools": None,
                        "generation_config": {},
                    }

                    with patch(
                        "src.antigravity_anthropic_router.send_antigravity_request_no_stream"
                    ) as mock_send:
                        mock_send.return_value = (mock_response_data, "cred_name", None)

                        response = client.post(
                            "/antigravity/v1/messages",
                            json={
                                "model": "claude-3",
                                "max_tokens": 1000,
                                "messages": [{"role": "user", "content": "Hello"}],
                            },
                            headers=self._auth_headers(),
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["type"] == "message"
                        assert data["content"][0]["type"] == "text"
                        assert data["content"][0]["text"] == "Hello!"

    def test_empty_contents_returns_400(self, client):
        """Empty contents after conversion should return 400"""
        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", {"project_id": "proj123"})
        )

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.return_value = {
                        "contents": [],  # Empty contents
                        "model": "mapped-model",
                        "system_instruction": None,
                        "tools": None,
                        "generation_config": {},
                    }

                    response = client.post(
                        "/antigravity/v1/messages",
                        json={
                            "model": "claude-3",
                            "max_tokens": 1000,
                            "messages": [{"role": "user", "content": "   "}],
                        },
                        headers=self._auth_headers(),
                    )

                    assert response.status_code == 400
                    assert "空" in response.json()["error"]["message"]

    def test_no_credentials_returns_500(self, client):
        """No credentials available should return 500"""
        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(return_value=None)

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.return_value = {
                        "contents": [{"parts": [{"text": "test"}]}],
                        "model": "mapped-model",
                        "system_instruction": None,
                        "tools": None,
                        "generation_config": {},
                    }

                    response = client.post(
                        "/antigravity/v1/messages",
                        json={
                            "model": "claude-3",
                            "max_tokens": 1000,
                            "messages": [{"role": "user", "content": "test"}],
                        },
                        headers=self._auth_headers(),
                    )

                    assert response.status_code == 500
                    assert "凭证" in response.json()["error"]["message"]

    def test_conversion_error_returns_400(self, client):
        """Conversion error should return 400"""
        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", {"project_id": "proj123"})
        )

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.side_effect = ValueError("Conversion failed")

                    response = client.post(
                        "/antigravity/v1/messages",
                        json={
                            "model": "claude-3",
                            "max_tokens": 1000,
                            "messages": [{"role": "user", "content": "test"}],
                        },
                        headers=self._auth_headers(),
                    )

                    assert response.status_code == 400
                    assert "转换失败" in response.json()["error"]["message"]

    def test_downstream_error_returns_500(self, client):
        """Downstream request error should return 500"""
        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", {"project_id": "proj123"})
        )

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.return_value = {
                        "contents": [{"parts": [{"text": "test"}]}],
                        "model": "mapped-model",
                        "system_instruction": None,
                        "tools": None,
                        "generation_config": {},
                    }

                    with patch(
                        "src.antigravity_anthropic_router.send_antigravity_request_no_stream"
                    ) as mock_send:
                        mock_send.side_effect = Exception("Network error")

                        response = client.post(
                            "/antigravity/v1/messages",
                            json={
                                "model": "claude-3",
                                "max_tokens": 1000,
                                "messages": [{"role": "user", "content": "test"}],
                            },
                            headers=self._auth_headers(),
                        )

                        assert response.status_code == 500
                        assert "下游请求失败" in response.json()["error"]["message"]


class TestAnthropicMessagesThinking:
    """Tests for thinking handling in /antigravity/v1/messages"""

    def _auth_headers(self):
        return {"Authorization": "Bearer test_pw"}

    def test_thinking_enabled_passes_to_converter(self, client):
        """thinking.type=enabled should pass client_thinking_enabled=True"""
        mock_response_data = {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "thought": True,
                                    "text": "Thinking...",
                                    "thoughtSignature": "sig",
                                },
                                {"text": "Answer"},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            }
        }

        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", {"project_id": "proj123"})
        )

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.return_value = {
                        "contents": [{"parts": [{"text": "test"}]}],
                        "model": "mapped-model",
                        "system_instruction": None,
                        "tools": None,
                        "generation_config": {},
                    }

                    with patch(
                        "src.antigravity_anthropic_router.send_antigravity_request_no_stream"
                    ) as mock_send:
                        mock_send.return_value = (mock_response_data, "cred_name", None)

                        response = client.post(
                            "/antigravity/v1/messages",
                            json={
                                "model": "claude-3",
                                "max_tokens": 1000,
                                "messages": [{"role": "user", "content": "test"}],
                                "thinking": {"type": "enabled", "budget_tokens": 10000},
                            },
                            headers=self._auth_headers(),
                        )

                        assert response.status_code == 200
                        data = response.json()
                        # Should have thinking block
                        assert data["content"][0]["type"] == "thinking"
                        assert data["content"][0]["signature"] == "sig"

    def test_thinking_disabled_strips_thinking(self, client):
        """thinking.type=disabled should strip thinking blocks"""
        mock_response_data = {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": True, "text": "Thinking..."},
                                {"text": "Answer"},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            }
        }

        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", {"project_id": "proj123"})
        )

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.return_value = {
                        "contents": [{"parts": [{"text": "test"}]}],
                        "model": "mapped-model",
                        "system_instruction": None,
                        "tools": None,
                        "generation_config": {},
                    }

                    with patch(
                        "src.antigravity_anthropic_router.send_antigravity_request_no_stream"
                    ) as mock_send:
                        mock_send.return_value = (mock_response_data, "cred_name", None)

                        response = client.post(
                            "/antigravity/v1/messages",
                            json={
                                "model": "claude-3",
                                "max_tokens": 1000,
                                "messages": [{"role": "user", "content": "test"}],
                                "thinking": {"type": "disabled"},
                            },
                            headers=self._auth_headers(),
                        )

                        assert response.status_code == 200
                        data = response.json()
                        # Should have thinking converted to text
                        assert data["content"][0]["type"] == "text"
                        assert "<assistant_thinking>" in data["content"][0]["text"]

    def test_nothinking_model_variant(self, client):
        """Model with -nothinking suffix should convert thinking to text"""
        mock_response_data = {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": True, "text": "My thoughts..."},
                                {"text": "The answer."},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            }
        }

        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", {"project_id": "proj123"})
        )

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.return_value = {
                        "contents": [{"parts": [{"text": "test"}]}],
                        "model": "mapped-model",
                        "system_instruction": None,
                        "tools": None,
                        "generation_config": {},
                    }

                    with patch(
                        "src.antigravity_anthropic_router.send_antigravity_request_no_stream"
                    ) as mock_send:
                        mock_send.return_value = (mock_response_data, "cred_name", None)

                        response = client.post(
                            "/antigravity/v1/messages",
                            json={
                                "model": "claude-3-nothinking",
                                "max_tokens": 1000,
                                "messages": [{"role": "user", "content": "test"}],
                            },
                            headers=self._auth_headers(),
                        )

                        assert response.status_code == 200
                        data = response.json()
                        # Should have thinking as text
                        text = data["content"][0]["text"]
                        assert "<assistant_thinking>" in text
                        assert "My thoughts..." in text

    def test_thinking_false_value(self, client):
        """thinking=False should disable thinking"""
        mock_response_data = {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": True, "text": "Hidden"},
                                {"text": "Visible"},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            }
        }

        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", {"project_id": "proj123"})
        )

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.return_value = {
                        "contents": [{"parts": [{"text": "test"}]}],
                        "model": "mapped-model",
                        "system_instruction": None,
                        "tools": None,
                        "generation_config": {},
                    }

                    with patch(
                        "src.antigravity_anthropic_router.send_antigravity_request_no_stream"
                    ) as mock_send:
                        mock_send.return_value = (mock_response_data, "cred_name", None)

                        response = client.post(
                            "/antigravity/v1/messages",
                            json={
                                "model": "claude-3",
                                "max_tokens": 1000,
                                "messages": [{"role": "user", "content": "test"}],
                                "thinking": False,
                            },
                            headers=self._auth_headers(),
                        )

                        assert response.status_code == 200
                        data = response.json()
                        # Should convert to text
                        assert "<assistant_thinking>" in data["content"][0]["text"]


class TestAnthropicMessagesStreaming:
    """Tests for streaming /antigravity/v1/messages"""

    def _auth_headers(self):
        return {"Authorization": "Bearer test_pw"}

    def test_streaming_request_returns_event_stream(self, client):
        """Streaming request should return text/event-stream"""
        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", {"project_id": "proj123"})
        )

        # Create mock stream resources
        mock_response = AsyncMock()
        mock_response.__aiter__ = lambda self: self
        mock_response.__anext__ = AsyncMock(side_effect=StopAsyncIteration)

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aexit__ = AsyncMock()

        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.return_value = {
                        "contents": [{"parts": [{"text": "test"}]}],
                        "model": "mapped-model",
                        "system_instruction": None,
                        "tools": None,
                        "generation_config": {},
                    }

                    with patch(
                        "src.antigravity_anthropic_router.send_antigravity_request_stream"
                    ) as mock_send:
                        mock_send.return_value = (
                            (mock_response, mock_stream_ctx, mock_client),
                            "cred_name",
                            None,
                        )

                        with patch(
                            "src.antigravity_anthropic_router.antigravity_sse_to_anthropic_sse"
                        ) as mock_sse:
                            # Return empty async generator
                            async def empty_gen(*args, **kwargs):
                                return
                                yield  # Make it a generator

                            mock_sse.return_value = empty_gen()

                            response = client.post(
                                "/antigravity/v1/messages",
                                json={
                                    "model": "claude-3",
                                    "max_tokens": 1000,
                                    "messages": [{"role": "user", "content": "test"}],
                                    "stream": True,
                                },
                                headers=self._auth_headers(),
                            )

                            assert response.status_code == 200
                            assert (
                                "text/event-stream" in response.headers["content-type"]
                            )

    def test_streaming_error_returns_500(self, client):
        """Streaming request error should return 500"""
        mock_cred_mgr = MagicMock()
        mock_cred_mgr.get_valid_credential = AsyncMock(
            return_value=("cred_name", {"project_id": "proj123"})
        )

        async def mock_get_cred_manager():
            return mock_cred_mgr

        with create_password_patch("test_pw"):
            with patch(
                "src.credential_manager.get_credential_manager",
                mock_get_cred_manager,
            ):
                with patch(
                    "src.antigravity_anthropic_router.convert_anthropic_request_to_antigravity_components"
                ) as mock_convert:
                    mock_convert.return_value = {
                        "contents": [{"parts": [{"text": "test"}]}],
                        "model": "mapped-model",
                        "system_instruction": None,
                        "tools": None,
                        "generation_config": {},
                    }

                    with patch(
                        "src.antigravity_anthropic_router.send_antigravity_request_stream"
                    ) as mock_send:
                        mock_send.side_effect = Exception("Stream connection failed")

                        response = client.post(
                            "/antigravity/v1/messages",
                            json={
                                "model": "claude-3",
                                "max_tokens": 1000,
                                "messages": [{"role": "user", "content": "test"}],
                                "stream": True,
                            },
                            headers=self._auth_headers(),
                        )

                        assert response.status_code == 500


class TestCountTokensEndpoint:
    """Tests for /antigravity/v1/messages/count_tokens"""

    def _auth_headers(self):
        return {"Authorization": "Bearer test_pw"}

    def test_missing_auth_returns_403(self, client):
        """Missing auth should return 403"""
        with create_password_patch("correct_password"):
            response = client.post(
                "/antigravity/v1/messages/count_tokens",
                json={"model": "claude-3", "messages": []},
            )
            assert response.status_code == 403

    def test_invalid_json_returns_400(self, client):
        """Invalid JSON should return 400"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages/count_tokens",
                content="not json",
                headers={"Content-Type": "application/json", **self._auth_headers()},
            )
            assert response.status_code == 400
            assert "JSON" in response.json()["error"]["message"]

    def test_non_object_returns_400(self, client):
        """Non-object body should return 400"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages/count_tokens",
                json=["list", "not", "object"],
                headers=self._auth_headers(),
            )
            assert response.status_code == 400

    def test_missing_model_returns_400(self, client):
        """Missing model should return 400"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages/count_tokens",
                json={"messages": []},
                headers=self._auth_headers(),
            )
            assert response.status_code == 400
            assert "model" in response.json()["error"]["message"]

    def test_missing_messages_returns_400(self, client):
        """Missing messages should return 400"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages/count_tokens",
                json={"model": "claude-3"},
                headers=self._auth_headers(),
            )
            assert response.status_code == 400
            assert "messages" in response.json()["error"]["message"]

    def test_successful_count_returns_tokens(self, client):
        """Successful count should return input_tokens"""
        with create_password_patch("test_pw"):
            with patch(
                "src.antigravity_anthropic_router.estimate_input_tokens"
            ) as mock_estimate:
                mock_estimate.return_value = 42

                response = client.post(
                    "/antigravity/v1/messages/count_tokens",
                    json={
                        "model": "claude-3",
                        "messages": [{"role": "user", "content": "Hello world"}],
                    },
                    headers=self._auth_headers(),
                )

                assert response.status_code == 200
                assert response.json()["input_tokens"] == 42

    def test_estimation_error_returns_zero(self, client):
        """Estimation error should return 0"""
        with create_password_patch("test_pw"):
            with patch(
                "src.antigravity_anthropic_router.estimate_input_tokens"
            ) as mock_estimate:
                mock_estimate.side_effect = Exception("Estimation failed")

                response = client.post(
                    "/antigravity/v1/messages/count_tokens",
                    json={
                        "model": "claude-3",
                        "messages": [{"role": "user", "content": "Hello"}],
                    },
                    headers=self._auth_headers(),
                )

                assert response.status_code == 200
                assert response.json()["input_tokens"] == 0

    def test_thinking_info_logged(self, client):
        """Thinking info should be logged correctly"""
        with create_password_patch("test_pw"):
            with patch(
                "src.antigravity_anthropic_router.estimate_input_tokens"
            ) as mock_estimate:
                mock_estimate.return_value = 100

                # Test with dict thinking
                response = client.post(
                    "/antigravity/v1/messages/count_tokens",
                    json={
                        "model": "claude-3",
                        "messages": [{"role": "user", "content": "test"}],
                        "thinking": {"type": "enabled", "budget_tokens": 5000},
                    },
                    headers=self._auth_headers(),
                )

                assert response.status_code == 200

    def test_non_dict_thinking_handled(self, client):
        """Non-dict thinking value should be handled"""
        with create_password_patch("test_pw"):
            with patch(
                "src.antigravity_anthropic_router.estimate_input_tokens"
            ) as mock_estimate:
                mock_estimate.return_value = 50

                # Test with boolean thinking
                response = client.post(
                    "/antigravity/v1/messages/count_tokens",
                    json={
                        "model": "claude-3",
                        "messages": [{"role": "user", "content": "test"}],
                        "thinking": False,
                    },
                    headers=self._auth_headers(),
                )

                assert response.status_code == 200


class TestDebugLogging:
    """Tests for debug logging functionality"""

    def _auth_headers(self):
        return {"Authorization": "Bearer test_pw"}

    def test_debug_logging_enabled(self, client, monkeypatch):
        """Debug logging should work when enabled"""
        monkeypatch.setenv("ANTHROPIC_DEBUG", "1")
        monkeypatch.setenv("ANTHROPIC_DEBUG_BODY", "1")

        with create_password_patch("test_pw"):
            # Test with Hi message to get a quick response
            response = client.post(
                "/antigravity/v1/messages",
                json={
                    "model": "claude-3",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers=self._auth_headers(),
            )

            assert response.status_code == 200


class TestClientInfo:
    """Tests for client info extraction"""

    def _auth_headers(self):
        return {"Authorization": "Bearer test_pw"}

    def test_client_info_logged(self, client):
        """Client info should be extracted and logged"""
        with create_password_patch("test_pw"):
            response = client.post(
                "/antigravity/v1/messages",
                json={
                    "model": "claude-3",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={**self._auth_headers(), "User-Agent": "TestClient/1.0"},
            )

            assert response.status_code == 200


# Run tests with: python -m pytest tests/test_router_api.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
