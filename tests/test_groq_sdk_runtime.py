"""Tests for the Groq SDK runtime adapter.

The Groq SDK is mocked via sys.modules so these tests run offline and
do not consume API credits. Coverage spans registration discovery, the
missing-API-key path, the happy streaming path (callback fan-out,
RuntimeResult shape, history accumulation), system prompt threading,
and partial-failure handling when the stream raises mid-response.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest  # noqa: F401  (pytest is the test runner; import keeps tooling happy)

# Importing the module triggers `@register("groq_sdk")` at module load time,
# so the runtime is in REGISTRY regardless of which other tests in the suite
# may have already populated it (get_runtime's auto-discovery only fires when
# REGISTRY is fully empty).
from ax_cli.runtimes.hermes.runtimes import groq_sdk  # noqa: F401, E402


# ── Helpers ────────────────────────────────────────────────────────────────

def _fake_chunk(content: str | None):
    """Build a duck-typed chat.completions chunk holding a single delta."""
    delta = types.SimpleNamespace(content=content)
    choice = types.SimpleNamespace(delta=delta, finish_reason=None)
    return types.SimpleNamespace(choices=[choice])


def _install_fake_groq(monkeypatch, fake_client):
    """Swap `groq` in sys.modules so `from groq import Groq` returns our mock."""
    fake_module = types.ModuleType("groq")
    fake_module.Groq = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "groq", fake_module)
    return fake_module


class _RecordingCallback:
    """Minimal StreamCallback implementation that records what it sees."""

    def __init__(self):
        self.deltas: list[str] = []
        self.complete: str | None = None
        self.statuses: list[str] = []

    def on_text_delta(self, text: str) -> None:
        self.deltas.append(text)

    def on_text_complete(self, text: str) -> None:
        self.complete = text

    def on_tool_start(self, *_args, **_kwargs) -> None:
        pass

    def on_tool_end(self, *_args, **_kwargs) -> None:
        pass

    def on_status(self, status: str) -> None:
        self.statuses.append(status)


# ── Tests ──────────────────────────────────────────────────────────────────

def test_groq_sdk_registers_under_expected_name():
    from ax_cli.runtimes.hermes.runtimes import get_runtime

    rt = get_runtime("groq_sdk")
    assert type(rt).__name__ == "GroqSDKRuntime"
    assert rt.name == "groq_sdk"


def test_groq_sdk_returns_crashed_when_api_key_missing(monkeypatch):
    """No API key in env should short-circuit before any groq import."""
    from ax_cli.runtimes.hermes.runtimes import get_runtime

    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    rt = get_runtime("groq_sdk")
    result = rt.execute("hello", workdir="/tmp")

    assert result.exit_reason == "crashed"
    assert "GROQ_API_KEY" in result.text
    assert result.elapsed_seconds == 0


def test_groq_sdk_streams_chunks_and_accumulates_history(monkeypatch):
    """Happy path: deltas fire on the callback, history grows, RuntimeResult is shaped."""
    from ax_cli.runtimes.hermes.runtimes import get_runtime

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter([
        _fake_chunk("Hello "),
        _fake_chunk("world."),
    ])
    _install_fake_groq(monkeypatch, fake_client)

    rt = get_runtime("groq_sdk")
    cb = _RecordingCallback()
    result = rt.execute(
        "Say hello.",
        workdir="/tmp",
        stream_cb=cb,
    )

    # Stream deltas received in order.
    assert cb.deltas == ["Hello ", "world."]
    # on_text_complete fires with the assembled text.
    assert cb.complete == "Hello world."
    # RuntimeResult fields.
    assert result.exit_reason == "done"
    assert result.text == "Hello world."
    assert result.tool_count == 0
    assert result.files_written == []
    # History records the round trip: user prompt + assistant reply.
    assert len(result.history) == 2
    assert result.history[0] == {"role": "user", "content": "Say hello."}
    assert result.history[1] == {"role": "assistant", "content": "Hello world."}
    # The runtime requested streaming explicitly.
    assert fake_client.chat.completions.create.call_args.kwargs["stream"] is True


def test_groq_sdk_threads_system_prompt_into_messages(monkeypatch):
    """The system_prompt arg should become the first message with role=system."""
    from ax_cli.runtimes.hermes.runtimes import get_runtime

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter([_fake_chunk("ok")])
    _install_fake_groq(monkeypatch, fake_client)

    rt = get_runtime("groq_sdk")
    rt.execute(
        "Question.",
        workdir="/tmp",
        system_prompt="You are a strict reviewer.",
    )

    messages = fake_client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a strict reviewer."
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Question."


def test_groq_sdk_preserves_partial_text_on_mid_stream_error(monkeypatch):
    """If the stream raises mid-response, already-received text must not be lost."""
    from ax_cli.runtimes.hermes.runtimes import get_runtime

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    def explode_after_two():
        yield _fake_chunk("Partial ")
        yield _fake_chunk("reply")
        raise RuntimeError("stream broke")

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = explode_after_two()
    _install_fake_groq(monkeypatch, fake_client)

    rt = get_runtime("groq_sdk")
    cb = _RecordingCallback()
    result = rt.execute("Say hello.", workdir="/tmp", stream_cb=cb)

    # Partial text preserved in both the RuntimeResult and history.
    assert result.text == "Partial reply"
    assert result.exit_reason == "crashed"
    assert any(
        h.get("role") == "assistant" and h.get("content") == "Partial reply"
        for h in result.history
    )
    # Deltas fired before the error.
    assert cb.deltas == ["Partial ", "reply"]
