# NEW: not yet vendored from ax-agents. Pending upstream PR before the next
# vendor sync. See ax_cli/runtimes/hermes/README.md for vendoring guidance.
"""Groq SDK runtime — wraps Groq's chat completions API.

Phase 3: multi-turn agent loop with tool calls. The runtime streams a
chat completion, accumulates text and any tool-call deltas, executes
requested tools via the shared `tools` module, and loops until the
model emits a final text-only reply (or max_turns is hit).

Tool definitions in this codebase are stored in OpenAI Responses-API
shape (flat `name` field). Groq speaks chat completions, which expects
the nested `function: { name, ... }` shape, so we adapt on the way out.

Deferred to Phase 4: SDK_PREAMBLE injection, re-prompt on text-only
first turn, rate-limit backoff polish.

Auth: GROQ_API_KEY environment variable.
Models: https://console.groq.com/docs/models
        (default: llama-3.3-70b-versatile)
"""

from __future__ import annotations

import json
import logging
import os
import time

from . import BaseRuntime, RuntimeResult, StreamCallback, register

log = logging.getLogger("runtime.groq_sdk")

DEFAULT_MODEL = "llama-3.3-70b-versatile"
MAX_TURNS = 25
TOOL_OUTPUT_CAP = 10_000  # bytes of tool output fed back to the model per call


def _to_chat_completion_tool(rd_tool: dict) -> dict:
    """Convert a Responses-API tool definition to chat.completions shape."""
    return {
        "type": "function",
        "function": {
            "name": rd_tool["name"],
            "description": rd_tool.get("description", ""),
            "parameters": rd_tool.get("parameters", {}),
        },
    }


def _tool_display(name: str, args: dict) -> str:
    """Human-readable one-liner for tool activity log."""
    if name in ("read_file", "write_file", "edit_file"):
        p = args.get("path", "")
        verb = {"read_file": "Read", "write_file": "Write", "edit_file": "Edit"}[name]
        tail = p.rsplit("/", 1)[-1] if "/" in p else p
        return f"{verb} {tail}"
    if name == "bash":
        cmd = str(args.get("command", ""))[:60]
        return f"Run: {cmd}"
    if name == "grep":
        return f"Search: {args.get('pattern', '')}"
    if name == "glob_files":
        return f"Find: {args.get('pattern', '')}"
    return name


@register("groq_sdk")
class GroqSDKRuntime(BaseRuntime):
    """Runs agent turns via the Groq Python SDK.

    Phase 3: multi-turn loop with tool calling. Streams text deltas
    through StreamCallback.on_text_delta, accumulates tool_call deltas
    by index, executes tools through the shared `tools` module, and
    loops until the model produces a final text-only reply or MAX_TURNS
    is reached.
    """

    def execute(
        self,
        message: str,
        *,
        workdir: str,
        model: str | None = None,
        system_prompt: str | None = None,
        session_id: str | None = None,
        stream_cb: StreamCallback | None = None,
        timeout: int = 300,
        extra_args: dict | None = None,
    ) -> RuntimeResult:
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            log.error("groq_sdk: GROQ_API_KEY not set in environment")
            return RuntimeResult(
                text="Agent could not authenticate with Groq (GROQ_API_KEY not set).",
                exit_reason="crashed",
                elapsed_seconds=0,
            )

        from groq import Groq
        # Relative import from the sibling tools package. openai_sdk.py uses the
        # absolute `from tools import ...` which relies on hermes-agent putting
        # tools/ on sys.path root in production. We use the relative form so the
        # runtime works in local dev too. Upstream may choose to switch to the
        # absolute form during PR review.
        from ..tools import TOOL_DEFINITIONS, execute_tool

        cb = stream_cb or StreamCallback()
        model = model or DEFAULT_MODEL
        instructions = system_prompt or "You are a helpful coding assistant."

        tools = [_to_chat_completion_tool(t) for t in TOOL_DEFINITIONS]

        start_time = time.time()
        history: list[dict] = list((extra_args or {}).get("history", []))
        history.append({"role": "user", "content": message})

        final_text = ""
        tool_count = 0
        files_written: list[str] = []
        client = Groq(api_key=api_key)

        for turn in range(MAX_TURNS):
            log.info(f"groq_sdk: turn {turn + 1}, {len(history)} messages")

            try:
                stream = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": instructions},
                        *history,
                    ],
                    tools=tools,
                    stream=True,
                )
            except Exception as e:
                error_str = str(e)
                log.error(f"groq_sdk: API error opening stream: {error_str}")
                is_rate_limit = (
                    "429" in error_str
                    or "rate" in error_str.lower()
                    or "usage_limit" in error_str.lower()
                )
                if is_rate_limit:
                    return RuntimeResult(
                        text="",
                        history=history,
                        tool_count=tool_count,
                        files_written=files_written,
                        exit_reason="rate_limited",
                        elapsed_seconds=int(time.time() - start_time),
                    )
                return RuntimeResult(
                    text=final_text or "Agent encountered an API error and could not complete the task.",
                    history=history,
                    tool_count=tool_count,
                    files_written=files_written,
                    exit_reason="crashed",
                    elapsed_seconds=int(time.time() - start_time),
                )

            # Accumulate text and tool_call deltas across the stream.
            turn_text = ""
            tool_calls_acc: dict[int, dict] = {}

            try:
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    content = getattr(delta, "content", None)
                    if content:
                        turn_text += content
                        cb.on_text_delta(content)

                    tc_deltas = getattr(delta, "tool_calls", None) or []
                    for tc_d in tc_deltas:
                        idx = getattr(tc_d, "index", 0)
                        slot = tool_calls_acc.setdefault(
                            idx,
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        tc_id = getattr(tc_d, "id", None)
                        if tc_id:
                            slot["id"] = tc_id
                        fn_delta = getattr(tc_d, "function", None)
                        if fn_delta is not None:
                            fn_name = getattr(fn_delta, "name", None)
                            if fn_name:
                                slot["function"]["name"] = fn_name
                            fn_args = getattr(fn_delta, "arguments", None)
                            if fn_args:
                                slot["function"]["arguments"] += fn_args
            except Exception as e:
                log.error(f"groq_sdk: stream error after {len(turn_text)} chars: {e}")
                partial = turn_text.strip()
                if partial:
                    history.append({"role": "assistant", "content": partial})
                return RuntimeResult(
                    text=partial or "Agent encountered a stream error mid-response.",
                    history=history,
                    tool_count=tool_count,
                    files_written=files_written,
                    exit_reason="crashed",
                    elapsed_seconds=int(time.time() - start_time),
                )

            tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]

            # If the model requested tools, execute them and continue the loop.
            if tool_calls:
                history.append(
                    {
                        "role": "assistant",
                        "content": turn_text or None,
                        "tool_calls": tool_calls,
                    }
                )

                for tc in tool_calls:
                    tool_count += 1
                    name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}

                    summary = _tool_display(name, args)
                    log.info(
                        f"groq_sdk: tool {name}({json.dumps(args, default=str)[:80]})"
                    )
                    cb.on_tool_start(name, summary)
                    result = execute_tool(name, args, workdir)

                    if name == "write_file" and not result.is_error:
                        files_written.append(args.get("path", ""))

                    short = result.output[:200] if result.output else ""
                    cb.on_tool_end(name, short)

                    history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": (result.output or "")[:TOOL_OUTPUT_CAP],
                        }
                    )

                cb.on_status("thinking")
                continue  # Next turn: model sees tool results.

            # No tool calls — text-only response. Treat as final.
            visible = turn_text.strip()
            if visible:
                final_text = visible
                cb.on_text_complete(final_text)
                history.append({"role": "assistant", "content": visible})
            break

        elapsed = int(time.time() - start_time)
        log.info(
            f"groq_sdk: done in {elapsed}s, {tool_count} tools, "
            f"{len(final_text)} chars"
        )
        return RuntimeResult(
            text=final_text,
            history=history,
            session_id=None,
            tool_count=tool_count,
            files_written=files_written,
            exit_reason="done",
            elapsed_seconds=elapsed,
        )
