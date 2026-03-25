"""Tests for streaming tool call finish_reason handling.

Ensures tool calls are emitted even when the provider returns
finish_reason="stop" instead of "tool_calls" (e.g. Moonshot/Kimi).
"""

import json
from unittest.mock import patch, MagicMock

from freecad_ai.llm.client import LLMClient, LLMStreamEvent


def _make_client():
    return LLMClient(
        provider_name="moonshot",
        base_url="https://api.moonshot.cn/v1",
        api_key="test-key",
        model="kimi-k2-0711",
    )


def _sse_chunks_with_stop_finish():
    """Simulate SSE chunks where tool calls are present but finish_reason is 'stop'."""
    return [
        # Tool call start
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_abc", "function": {"name": "create_body", "arguments": ""}}]}, "finish_reason": None}]},
        # Tool call arguments
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"label":'}}]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ' "Test"}'}}]}, "finish_reason": None}]},
        # Finish with "stop" instead of "tool_calls"
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]


def _sse_chunks_with_tool_calls_finish():
    """Simulate SSE chunks with correct finish_reason='tool_calls'."""
    return [
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_xyz", "function": {"name": "pad_sketch", "arguments": ""}}]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"sketch_name": "Sketch", "length": 10}'}}]}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]


def _sse_chunks_stop_no_tools():
    """Simulate SSE chunks with no tool calls and finish_reason='stop'."""
    return [
        {"choices": [{"delta": {"content": "Hello "}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "world"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]


class TestStreamToolFinishReason:
    def test_tool_calls_emitted_on_stop_finish(self):
        """Tool calls must be emitted even when finish_reason is 'stop'."""
        client = _make_client()
        chunks = _sse_chunks_with_stop_finish()

        with patch.object(client, '_http_stream', return_value=iter(chunks)):
            events = list(client._stream_openai_tools([], "", tools=[]))

        tool_ends = [e for e in events if e.type == "tool_call_end"]
        assert len(tool_ends) == 1
        assert tool_ends[0].tool_call.name == "create_body"
        assert tool_ends[0].tool_call.arguments == {"label": "Test"}

    def test_tool_calls_emitted_on_tool_calls_finish(self):
        """Standard finish_reason='tool_calls' still works."""
        client = _make_client()
        chunks = _sse_chunks_with_tool_calls_finish()

        with patch.object(client, '_http_stream', return_value=iter(chunks)):
            events = list(client._stream_openai_tools([], "", tools=[]))

        tool_ends = [e for e in events if e.type == "tool_call_end"]
        assert len(tool_ends) == 1
        assert tool_ends[0].tool_call.name == "pad_sketch"
        assert tool_ends[0].tool_call.arguments == {"sketch_name": "Sketch", "length": 10}

    def test_stop_without_tools_no_spurious_tool_calls(self):
        """finish_reason='stop' without tool calls should not emit tool_call_end."""
        client = _make_client()
        chunks = _sse_chunks_stop_no_tools()

        with patch.object(client, '_http_stream', return_value=iter(chunks)):
            events = list(client._stream_openai_tools([], "", tools=[]))

        tool_ends = [e for e in events if e.type == "tool_call_end"]
        assert len(tool_ends) == 0

        text_events = [e for e in events if e.type == "text_delta"]
        assert len(text_events) == 2
        assert text_events[0].text == "Hello "
        assert text_events[1].text == "world"

    def test_multiple_tool_calls_emitted_on_stop(self):
        """Multiple tool calls accumulated before 'stop' are all emitted."""
        client = _make_client()
        chunks = [
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "create_body", "arguments": '{"label": "A"}'}}]}, "finish_reason": None}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 1, "id": "c2", "function": {"name": "create_sketch", "arguments": '{"plane": "XY"}'}}]}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ]

        with patch.object(client, '_http_stream', return_value=iter(chunks)):
            events = list(client._stream_openai_tools([], "", tools=[]))

        tool_ends = [e for e in events if e.type == "tool_call_end"]
        assert len(tool_ends) == 2
        assert tool_ends[0].tool_call.name == "create_body"
        assert tool_ends[1].tool_call.name == "create_sketch"
