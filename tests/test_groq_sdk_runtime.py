"""Tests for the Groq SDK runtime adapter.

The Groq SDK is mocked via sys.modules so these tests run offline and
do not consume API credits. Coverage spans registration discovery, the
missing-API-key path, the happy streaming path (callback fan-out,
RuntimeResult shape, history accumulation), system prompt threading,
and partial-failure handling when the stream raises mid-response.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

import pytest  # noqa: F401  (pytest is the test runner; import keeps tooling happy)

# The Hermes sentinel prepends ax_cli/runtimes/hermes to sys.path in production
# so vendored runtimes can do `from tools import ...` as an absolute import.
# Replicate that here so the same import path resolves under pytest.
_HERMES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ax_cli", "runtimes", "hermes",
)
if _HERMES_DIR not in sys.path:
    sys.path.insert(0, _HERMES_DIR)

# Importing the module triggers `@register("groq_sdk")` at module load time,
# so the runtime is in REGISTRY regardless of which other tests in the suite
# may have already populated it (get_runtime's auto-discovery only fires when
# REGISTRY is fully empty).
from ax_cli.runtimes.hermes.runtimes import groq_sdk  # noqa: F401, E402


# ── Helpers ────────────────────────────────────────────────────────────────

def _fake_chunk(content: str | None):
    """Build a duck-typed chat.completions chunk holding a single delta."""
    delta = types.SimpleNamespace(content=content, tool_calls=None)
    choice = types.SimpleNamespace(delta=delta, finish_reason=None)
    return types.SimpleNamespace(choices=[choice])


def _fake_tool_call_delta(index, *, call_id=None, name=None, arguments=None):
    """Build one tool_call delta entry as the SDK yields it inside a chunk."""
    fn = types.SimpleNamespace(name=name, arguments=arguments)
    return types.SimpleNamespace(
        index=index,
        id=call_id,
        type="function" if call_id else None,
        function=fn,
    )


def _fake_chunk_with_tool_calls(tool_call_deltas):
    """Build a chat.completions chunk that carries tool_call deltas (no text)."""
    delta = types.SimpleNamespace(content=None, tool_calls=tool_call_deltas)
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


def test_groq_sdk_dispatches_tool_call_and_continues_to_final_answer(monkeypatch):
    """Model emits a tool_call streamed across chunks; runtime executes it, threads
    the result into history with role=tool, and finalizes on the next turn."""
    from ax_cli.runtimes.hermes.runtimes import get_runtime
    # Production code imports `from tools import ...` (absolute) because the
    # hermes sentinel puts ax_cli/runtimes/hermes on sys.path. We do the same
    # in module setup above, so this import lands on the same module object
    # that the runtime will read.
    import tools as tools_mod

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    # Turn 1: tool_call streamed across two chunks. First chunk carries
    # id + name; second chunk only accumulates arguments.
    turn1 = iter([
        _fake_chunk_with_tool_calls([
            _fake_tool_call_delta(0, call_id="call_abc", name="read_file", arguments=""),
        ]),
        _fake_chunk_with_tool_calls([
            _fake_tool_call_delta(0, arguments='{"path": "/etc/hostname"}'),
        ]),
    ])
    # Turn 2: plain text finalization.
    turn2 = iter([_fake_chunk("The hostname is foo.")])

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [turn1, turn2]
    _install_fake_groq(monkeypatch, fake_client)

    # Stub execute_tool so we do not touch the real filesystem.
    monkeypatch.setattr(
        tools_mod,
        "execute_tool",
        lambda name, args, workdir: tools_mod.ToolResult(output=f"stubbed {name}({args})"),
    )

    rt = get_runtime("groq_sdk")
    cb = _RecordingCallback()
    result = rt.execute("Read /etc/hostname.", workdir="/tmp", stream_cb=cb)

    assert result.exit_reason == "done"
    assert result.text == "The hostname is foo."
    assert result.tool_count == 1
    # Two turns = two API calls.
    assert fake_client.chat.completions.create.call_count == 2

    # History shape: user, assistant-with-tool-calls, tool result, final assistant.
    roles = [h.get("role") for h in result.history]
    assert roles == ["user", "assistant", "tool", "assistant"]
    # Tool call assembled correctly across the two chunks.
    assistant_with_tools = result.history[1]
    tc = assistant_with_tools["tool_calls"][0]
    assert tc["id"] == "call_abc"
    assert tc["function"]["name"] == "read_file"
    assert tc["function"]["arguments"] == '{"path": "/etc/hostname"}'
    # Tool message references the call_id.
    assert result.history[2]["tool_call_id"] == "call_abc"
    assert "stubbed read_file" in result.history[2]["content"]
    # Final assistant carries the visible reply.
    assert result.history[3]["content"] == "The hostname is foo."
    # Tool execution surfaces through the callback.
    assert cb.statuses == ["thinking"]


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


def test_groq_sdk_handles_missing_groq_package_gracefully(monkeypatch):
    """If the `groq` SDK is not installed, return a clean RuntimeResult
    instead of letting ModuleNotFoundError kill the sentinel."""
    from ax_cli.runtimes.hermes.runtimes import get_runtime

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    # Force `from groq import Groq` to raise ModuleNotFoundError by setting
    # the entry in sys.modules to None (Python treats this as "not importable").
    monkeypatch.setitem(sys.modules, "groq", None)

    rt = get_runtime("groq_sdk")
    result = rt.execute("hello", workdir="/tmp")

    assert result.exit_reason == "crashed"
    # Message should mention the missing package so the operator can act.
    assert "groq" in result.text.lower()
    assert "pip install" in result.text


def test_groq_sdk_returns_iteration_limit_when_max_turns_exhausted(monkeypatch):
    """If the model keeps producing tool calls and never finalizes, the runtime
    should exit with exit_reason='iteration_limit' rather than a misleading 'done'."""
    from ax_cli.runtimes.hermes.runtimes import get_runtime
    import tools as tools_mod
    from ax_cli.runtimes.hermes.runtimes.groq_sdk import MAX_TURNS

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    counter = {"n": 0}

    def one_turn_with_tool_call(*_args, **_kwargs):
        counter["n"] += 1
        return iter([
            _fake_chunk_with_tool_calls([
                _fake_tool_call_delta(
                    0,
                    call_id=f"call_{counter['n']}",
                    name="bash",
                    arguments='{"command":"ls"}',
                ),
            ]),
        ])

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = one_turn_with_tool_call
    _install_fake_groq(monkeypatch, fake_client)
    monkeypatch.setattr(
        tools_mod,
        "execute_tool",
        lambda name, args, workdir: tools_mod.ToolResult(output="stubbed"),
    )

    rt = get_runtime("groq_sdk")
    result = rt.execute("loop forever", workdir="/tmp")

    assert result.exit_reason == "iteration_limit"
    assert result.tool_count == MAX_TURNS
    assert fake_client.chat.completions.create.call_count == MAX_TURNS
    # User-visible message should reflect the bounded-loop exit.
    assert "turn limit" in result.text.lower()
