"""Tests for LLM client HTTP retry logic on 429 rate limits."""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from freecad_ai.llm.client import LLMClient, LLMError


@pytest.fixture
def client():
    return LLMClient(
        provider_name="test",
        base_url="http://localhost:9999",
        api_key="test-key",
        model="test-model",
    )


class TestHttpPostRetry:
    def test_succeeds_on_first_try(self, client):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client._http_post("http://localhost/api", {}, {})
        assert result == {"ok": True}

    @patch("time.sleep")
    def test_retries_on_429_then_succeeds(self, mock_sleep, client):
        error_429 = urllib.error.HTTPError(
            "http://localhost", 429, "Too Many Requests", {"Retry-After": "1"}, None
        )

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", side_effect=[error_429, mock_resp]):
            result = client._http_post("http://localhost/api", {}, {})

        assert result == {"ok": True}
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] >= 1.0

    @patch("time.sleep")
    def test_raises_after_max_retries(self, mock_sleep, client):
        errors = [
            urllib.error.HTTPError(
                "http://localhost", 429, "Too Many Requests", {}, None
            )
            for _ in range(client._MAX_RETRIES + 1)
        ]

        with patch("urllib.request.urlopen", side_effect=errors):
            with pytest.raises(LLMError, match="429"):
                client._http_post("http://localhost/api", {}, {})

        assert mock_sleep.call_count == client._MAX_RETRIES

    def test_non_429_error_not_retried(self, client):
        error_500 = urllib.error.HTTPError(
            "http://localhost", 500, "Server Error", {}, None
        )

        with patch("urllib.request.urlopen", side_effect=error_500):
            with pytest.raises(LLMError, match="500"):
                client._http_post("http://localhost/api", {}, {})

    @patch("time.sleep")
    def test_respects_retry_after_header(self, mock_sleep, client):
        error_429 = urllib.error.HTTPError(
            "http://localhost", 429, "Too Many Requests",
            {"Retry-After": "10"}, None
        )

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", side_effect=[error_429, mock_resp]):
            client._http_post("http://localhost/api", {}, {})

        assert mock_sleep.call_args[0][0] == 10.0

    @patch("time.sleep")
    def test_exponential_backoff_without_retry_after(self, mock_sleep, client):
        errors = [
            urllib.error.HTTPError(
                "http://localhost", 429, "Too Many Requests", {}, None
            )
            for _ in range(3)
        ]

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", side_effect=errors + [mock_resp]):
            client._http_post("http://localhost/api", {}, {})

        # Each successive delay should be longer (exponential)
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(delays) == 3
        # Base * 2^0 + jitter, Base * 2^1 + jitter, Base * 2^2 + jitter
        # With BASE_BACKOFF=2: ~2, ~4, ~8 (plus jitter 0-1)
        assert delays[0] < delays[1] < delays[2]


class TestHttpStreamRetry:
    @patch("time.sleep")
    def test_retries_on_429_then_succeeds(self, mock_sleep, client):
        error_429 = urllib.error.HTTPError(
            "http://localhost", 429, "Too Many Requests", {"Retry-After": "1"}, None
        )

        mock_resp = MagicMock()
        mock_resp.__iter__ = lambda s: iter([b'data: {"type": "done"}\n'])
        mock_resp.close = MagicMock()

        with patch("urllib.request.urlopen", side_effect=[error_429, mock_resp]):
            chunks = list(client._http_stream("http://localhost/api", {}, {}))

        assert len(chunks) == 1
        mock_sleep.assert_called_once()

    def test_non_429_error_not_retried(self, client):
        error_500 = urllib.error.HTTPError(
            "http://localhost", 500, "Server Error", {}, None
        )

        with patch("urllib.request.urlopen", side_effect=error_500):
            with pytest.raises(LLMError, match="500"):
                list(client._http_stream("http://localhost/api", {}, {}))
