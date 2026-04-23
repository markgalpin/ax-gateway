"""Gateway runtime backends and operator-facing templates.

Runtime types are the low-level execution adapters used by the Gateway.
Templates are the higher-level, user-facing choices presented in CLI and UI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _gateway_setup_skill_path() -> Path:
    return _repo_root() / "skills" / "gateway-agent-setup" / "SKILL.md"


def _shared_signals() -> dict[str, str]:
    return {
        "delivery": "Gateway confirms when a message was queued or claimed.",
        "liveness": "Gateway heartbeat and reconnect logic determine connected or stale state.",
    }


def runtime_type_catalog() -> dict[str, dict[str, Any]]:
    repo_root = _repo_root()
    return {
        "echo": {
            "id": "echo",
            "label": "Echo",
            "description": "Built-in test runtime for proving delivery, queueing, and reply flow.",
            "kind": "builtin",
            "passive": False,
            "requires": [],
            "form_fields": [],
            "examples": [],
            "signals": {
                **_shared_signals(),
                "activity": "Gateway emits built-in working and completed phases for echo replies.",
                "tools": "No tool-call telemetry. Echo is intentionally simple.",
            },
        },
        "exec": {
            "id": "exec",
            "label": "Command Bridge",
            "description": (
                "Gateway-owned command execution for bridges and adapters that print "
                "AX_GATEWAY_EVENT lines."
            ),
            "kind": "exec",
            "passive": False,
            "requires": ["exec_command"],
            "form_fields": [
                {
                    "name": "exec_command",
                    "label": "Exec Command",
                    "required": True,
                    "placeholder": "python3 examples/hermes_sentinel/hermes_bridge.py",
                },
                {
                    "name": "workdir",
                    "label": "Workdir",
                    "required": False,
                    "placeholder": str(repo_root),
                },
            ],
            "examples": [
                {
                    "label": "Gateway Probe",
                    "exec_command": "python3 examples/gateway_probe/probe_bridge.py",
                    "workdir": str(repo_root),
                },
                {
                    "label": "Codex Bridge",
                    "exec_command": "python3 examples/codex_gateway/codex_bridge.py",
                    "workdir": str(repo_root),
                },
                {
                    "label": "Hermes Sentinel",
                    "exec_command": "python3 examples/hermes_sentinel/hermes_bridge.py",
                    "workdir": str(repo_root),
                    "note": "Requires a local hermes-agent checkout plus auth setup.",
                },
                {
                    "label": "Ollama",
                    "exec_command": "python3 examples/gateway_ollama/ollama_bridge.py",
                    "workdir": str(repo_root),
                    "note": "Requires a local Ollama server and model.",
                },
            ],
            "signals": {
                **_shared_signals(),
                "activity": (
                    "Gateway can surface live activity when the bridge prints AX_GATEWAY_EVENT lines. "
                    "Without that, the operator still gets pickup and final completion."
                ),
                "tools": "Gateway can record tool usage when the bridge emits tool events.",
            },
        },
        "inbox": {
            "id": "inbox",
            "label": "Passive Inbox",
            "description": "Passive Gateway-managed identity that receives and queues work without auto-replying.",
            "kind": "builtin",
            "passive": True,
            "requires": [],
            "form_fields": [],
            "examples": [],
            "signals": {
                **_shared_signals(),
                "activity": "Gateway reports queued state only. This runtime is passive by design.",
                "tools": "No tool-call telemetry. Inbox runtimes do not execute work.",
            },
        },
    }


def runtime_type_definition(runtime_type: str) -> dict[str, Any]:
    normalized = runtime_type.lower().strip()
    if normalized == "command":
        normalized = "exec"
    catalog = runtime_type_catalog()
    if normalized not in catalog:
        raise KeyError(runtime_type)
    return catalog[normalized]


def runtime_type_list() -> list[dict[str, Any]]:
    catalog = runtime_type_catalog()
    ordered_ids = ["echo", "exec", "inbox"]
    return [catalog[runtime_id] for runtime_id in ordered_ids if runtime_id in catalog]


def agent_template_catalog() -> dict[str, dict[str, Any]]:
    repo_root = _repo_root()
    skill_path = _gateway_setup_skill_path()
    runtime_signals = {key: runtime_type_definition(key)["signals"] for key in ("echo", "exec", "inbox")}
    return {
        "echo_test": {
            "id": "echo_test",
            "label": "Echo (Test)",
            "description": "Fastest way to prove the Gateway is connected and replying correctly.",
            "availability": "ready",
            "launchable": True,
            "runtime_type": "echo",
            "asset_class": "interactive_agent",
            "intake_model": "live_listener",
            "trigger_sources": ["direct_message"],
            "return_paths": ["inline_reply"],
            "telemetry_shape": "basic",
            "suggested_name": "echo-bot",
            "operator_summary": "Best first test. No local setup required.",
            "recommended_test_message": "gateway test ping",
            "what_you_need": [],
            "setup_skill": "gateway-agent-setup",
            "setup_skill_path": str(skill_path),
            "defaults": {
                "runtime_type": "echo",
            },
            "signals": runtime_signals["echo"],
            "advanced": {
                "adapter_label": "Built-in echo runtime",
                "supports_command_override": False,
            },
        },
        "ollama": {
            "id": "ollama",
            "label": "Ollama",
            "description": "Local model runtime managed by Gateway.",
            "availability": "ready",
            "launchable": True,
            "runtime_type": "exec",
            "asset_class": "interactive_agent",
            "intake_model": "launch_on_send",
            "trigger_sources": ["direct_message"],
            "return_paths": ["inline_reply"],
            "telemetry_shape": "basic",
            "suggested_name": "ollama-bot",
            "operator_summary": "Good for a local model with pickup, liveness, and streaming activity.",
            "recommended_test_message": "Reply with exactly: Gateway test OK. Then mention which local model answered.",
            "what_you_need": [
                "Run a local Ollama server on this machine.",
                "Have at least one Ollama model pulled locally. Gateway can suggest an installed model when the server is reachable.",
            ],
            "setup_skill": "gateway-agent-setup",
            "setup_skill_path": str(skill_path),
            "defaults": {
                "runtime_type": "exec",
                "exec_command": "python3 examples/gateway_ollama/ollama_bridge.py",
                "workdir": str(repo_root),
            },
            "signals": runtime_signals["exec"],
            "advanced": {
                "adapter_label": "Gateway command bridge",
                "supports_command_override": True,
            },
        },
        "hermes": {
            "id": "hermes",
            "label": "Hermes",
            "description": "Local Hermes agent bridge with strong activity and tool telemetry.",
            "availability": "setup_required",
            "launchable": True,
            "runtime_type": "exec",
            "asset_class": "interactive_agent",
            "intake_model": "live_listener",
            "trigger_sources": ["direct_message"],
            "return_paths": ["inline_reply"],
            "telemetry_shape": "rich",
            "suggested_name": "hermes-bot",
            "operator_summary": "Best path for a capable local agent with tool use and rich progress.",
            "recommended_test_message": "Pause for 5 seconds, narrate activity as you go, and end with: Gateway test OK.",
            "what_you_need": [
                "A local hermes-agent checkout, usually at ~/hermes-agent or via HERMES_REPO_PATH.",
                "Hermes auth or model credentials such as ~/.hermes/auth.json or provider env vars.",
            ],
            "setup_skill": "gateway-agent-setup",
            "setup_skill_path": str(skill_path),
            "defaults": {
                "runtime_type": "exec",
                "exec_command": "python3 examples/hermes_sentinel/hermes_bridge.py",
                "workdir": str(repo_root),
            },
            "signals": runtime_signals["exec"],
            "advanced": {
                "adapter_label": "Gateway command bridge",
                "supports_command_override": True,
            },
        },
        "claude_code_channel": {
            "id": "claude_code_channel",
            "label": "Claude Code Channel",
            "description": "Live Claude Code session bridged through aX channel delivery.",
            "availability": "coming_soon",
            "launchable": False,
            "runtime_type": "exec",
            "asset_class": "interactive_agent",
            "intake_model": "live_listener",
            "trigger_sources": ["direct_message"],
            "return_paths": ["inline_reply"],
            "telemetry_shape": "basic",
            "suggested_name": "cc-channel",
            "operator_summary": "Planned managed channel adapter. Pickup and liveness first, richer activity where possible.",
            "recommended_test_message": "Reply with exactly: Gateway test OK.",
            "what_you_need": [
                "A dedicated managed-daemon adapter so Gateway can supervise a live ax channel session cleanly.",
            ],
            "setup_skill": "gateway-agent-setup",
            "setup_skill_path": str(skill_path),
            "defaults": {
                "runtime_type": "exec",
            },
            "signals": {
                **runtime_signals["exec"],
                "activity": (
                    "Today the channel is usually sparse while working. Gateway should still provide reliable "
                    "pickup and liveness even when the adapter emits little activity."
                ),
            },
            "advanced": {
                "adapter_label": "Managed daemon adapter",
                "supports_command_override": False,
            },
        },
        "inbox": {
            "id": "inbox",
            "label": "Passive Inbox",
            "description": "Passive receiver identity for queue demos, operator flows, and non-replying endpoints.",
            "availability": "advanced",
            "launchable": True,
            "runtime_type": "inbox",
            "asset_class": "background_worker",
            "intake_model": "queue_accept",
            "worker_model": "queue_drain",
            "trigger_sources": ["queued_job", "manual_trigger"],
            "return_paths": ["summary_post"],
            "telemetry_shape": "basic",
            "suggested_name": "inbox-bot",
            "operator_summary": "Advanced testing and operator-only flow.",
            "recommended_test_message": "Queue this test job, mark it received, and do not reply inline.",
            "what_you_need": [],
            "setup_skill": "gateway-agent-setup",
            "setup_skill_path": str(skill_path),
            "defaults": {
                "runtime_type": "inbox",
            },
            "signals": runtime_signals["inbox"],
            "advanced": {
                "adapter_label": "Built-in passive inbox runtime",
                "supports_command_override": False,
            },
        },
    }


def agent_template_definition(template_id: str) -> dict[str, Any]:
    normalized = template_id.lower().strip()
    catalog = agent_template_catalog()
    if normalized not in catalog:
        raise KeyError(template_id)
    return catalog[normalized]


def agent_template_list(*, include_advanced: bool = False) -> list[dict[str, Any]]:
    catalog = agent_template_catalog()
    ordered_ids = ["echo_test", "ollama", "hermes", "claude_code_channel", "inbox"]
    templates = [catalog[template_id] for template_id in ordered_ids if template_id in catalog]
    if include_advanced:
        return templates
    return [item for item in templates if str(item.get("availability") or "") != "advanced"]
