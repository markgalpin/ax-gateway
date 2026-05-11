# NEW: not yet vendored from ax-agents. Pending upstream PR before the next
# vendor sync. See ax_cli/runtimes/hermes/README.md for vendoring guidance.
"""Groq SDK runtime — wraps Groq's chat completions API.

Phase 1 skeleton: single non-streaming chat call, no tool support, no
agent loop. Streaming, history reuse, and tool calls land in subsequent
phases (mirror the patterns in openai_sdk.py).

Auth: GROQ_API_KEY environment variable.
Models: https://console.groq.com/docs/models
        (default: llama-3.3-70b-versatile)
"""

from __future__ import annotations

import logging
import os
import time

from . import BaseRuntime, RuntimeResult, StreamCallback, register

log = logging.getLogger("runtime.groq_sdk")

DEFAULT_MODEL = "llama-3.3-70b-versatile"


@register("groq_sdk")
class GroqSDKRuntime(BaseRuntime):
    """Runs agent turns via the Groq Python SDK.

    Phase 1: single non-streaming chat completion, no tool calls,
    no multi-turn agent loop. Returns the model's first reply as
    final text. Sufficient to prove registration + discovery and
    smoke-test the API surface.
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
        from groq import Groq

        cb = stream_cb or StreamCallback()
        model = model or DEFAULT_MODEL
        instructions = system_prompt or "You are a helpful coding assistant."

        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            log.error("groq_sdk: GROQ_API_KEY not set in environment")
            return RuntimeResult(
                text="Agent could not authenticate with Groq (GROQ_API_KEY not set).",
                exit_reason="crashed",
                elapsed_seconds=0,
            )

        start_time = time.time()
        history: list[dict] = list((extra_args or {}).get("history", []))
        history.append({"role": "user", "content": message})

        try:
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": instructions},
                    *history,
                ],
                stream=False,
            )
        except Exception as e:
            log.error(f"groq_sdk: API error: {e}")
            return RuntimeResult(
                text="Agent encountered an API error and could not complete the task.",
                history=history,
                exit_reason="crashed",
                elapsed_seconds=int(time.time() - start_time),
            )

        final_text = (response.choices[0].message.content or "").strip()
        history.append({"role": "assistant", "content": final_text})
        cb.on_text_complete(final_text)

        elapsed = int(time.time() - start_time)
        log.info(f"groq_sdk: done in {elapsed}s, {len(final_text)} chars")

        return RuntimeResult(
            text=final_text,
            history=history,
            session_id=None,
            tool_count=0,
            files_written=[],
            exit_reason="done",
            elapsed_seconds=elapsed,
        )
