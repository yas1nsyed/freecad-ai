"""Tests for API key resolution (file:, cmd:, literal)."""

import os
import tempfile

from freecad_ai.llm.client import LLMClient


def _make_client(api_key: str) -> LLMClient:
    return LLMClient(
        provider_name="custom",
        base_url="http://localhost",
        api_key=api_key,
        model="test",
    )


class TestResolveApiKey:
    def test_literal_key(self):
        client = _make_client("sk-abc123")
        assert client._resolve_api_key() == "sk-abc123"

    def test_empty_key(self):
        client = _make_client("")
        assert client._resolve_api_key() == ""

    def test_file_prefix(self, tmp_path):
        token_file = tmp_path / "token.txt"
        token_file.write_text("my-oauth-token-xyz\n")
        client = _make_client(f"file:{token_file}")
        assert client._resolve_api_key() == "my-oauth-token-xyz"

    def test_file_prefix_strips_whitespace(self, tmp_path):
        token_file = tmp_path / "token.txt"
        token_file.write_text("  token-with-spaces  \n\n")
        client = _make_client(f"file:{token_file}")
        assert client._resolve_api_key() == "token-with-spaces"

    def test_file_prefix_missing_file(self):
        client = _make_client("file:/nonexistent/path/token.txt")
        assert client._resolve_api_key() == ""

    def test_file_prefix_empty_file(self, tmp_path):
        token_file = tmp_path / "token.txt"
        token_file.write_text("")
        client = _make_client(f"file:{token_file}")
        assert client._resolve_api_key() == ""

    def test_file_prefix_tilde_expansion(self, tmp_path, monkeypatch):
        token_file = tmp_path / "token.txt"
        token_file.write_text("tilde-token")
        monkeypatch.setenv("HOME", str(tmp_path))
        client = _make_client("file:~/token.txt")
        assert client._resolve_api_key() == "tilde-token"

    def test_cmd_prefix(self):
        client = _make_client("cmd:echo my-token")
        assert client._resolve_api_key() == "my-token"

    def test_cmd_prefix_strips_whitespace(self):
        client = _make_client("cmd:echo '  spaced-token  '")
        assert client._resolve_api_key() == "spaced-token"

    def test_cmd_prefix_failure(self):
        client = _make_client("cmd:false")
        assert client._resolve_api_key() == ""

    def test_cmd_prefix_nonexistent_command(self):
        client = _make_client("cmd:nonexistent_command_xyz_12345")
        assert client._resolve_api_key() == ""

    def test_file_rereads_on_each_call(self, tmp_path):
        """Token file is re-read each call, picking up refreshed tokens."""
        token_file = tmp_path / "token.txt"
        token_file.write_text("token-v1")
        client = _make_client(f"file:{token_file}")
        assert client._resolve_api_key() == "token-v1"

        token_file.write_text("token-v2")
        assert client._resolve_api_key() == "token-v2"

    def test_headers_use_resolved_key(self, tmp_path):
        """OpenAI headers use the resolved key, not the raw prefix."""
        token_file = tmp_path / "token.txt"
        token_file.write_text("resolved-bearer-token")
        client = _make_client(f"file:{token_file}")
        headers = client._openai_headers()
        assert headers["Authorization"] == "Bearer resolved-bearer-token"
