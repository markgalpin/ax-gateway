"""ax qa — API-first regression smoke checks."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
import typer
from rich.table import Table

from ..client import AxClient
from ..config import (
    _global_config_dir,
    _load_user_config,
    _normalize_user_env,
    _user_config_path,
    diagnose_auth_config,
    get_client,
    resolve_space_id,
)
from ..context_keys import build_upload_context_key
from ..output import JSON_OPTION, console, print_json

app = typer.Typer(name="qa", help="Regression and contract smoke checks", no_args_is_help=True)


def _extract_items(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_items(value, keys)
            if nested:
                return nested
    return []


def _count(payload: Any, keys: tuple[str, ...]) -> int:
    if isinstance(payload, dict):
        for key in ("total", "count", "total_count"):
            value = payload.get(key)
            if isinstance(value, int):
                return value
    return len(_extract_items(payload, keys))


def _http_error(exc: httpx.HTTPStatusError) -> dict[str, Any]:
    response = exc.response
    detail: Any
    try:
        detail = response.json()
    except Exception:
        detail = response.text[:500]
    return {
        "status_code": response.status_code,
        "url": str(response.request.url),
        "detail": detail,
    }


def _error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, httpx.HTTPStatusError):
        return _http_error(exc)
    return {
        "type": exc.__class__.__name__,
        "detail": str(exc),
    }


def _run_check(
    checks: list[dict[str, Any]],
    name: str,
    fn: Callable[[], Any],
    *,
    summarize: Callable[[Any], dict[str, Any]] | None = None,
) -> Any:
    started = time.monotonic()
    try:
        payload = fn()
    except Exception as exc:
        checks.append(
            {
                "name": name,
                "ok": False,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "error": _error_payload(exc),
            }
        )
        return None

    check = {
        "name": name,
        "ok": True,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
    if summarize:
        check.update(summarize(payload))
    checks.append(check)
    return payload


def _summarize_collection(keys: tuple[str, ...]) -> Callable[[Any], dict[str, Any]]:
    def summarize(payload: Any) -> dict[str, Any]:
        return {"count": _count(payload, keys)}

    return summarize


def _normalize_upload(upload_data: dict[str, Any]) -> dict[str, Any]:
    raw = upload_data.get("attachment", upload_data)
    if not isinstance(raw, dict):
        raw = {}
    attachment_id = (
        raw.get("id")
        or raw.get("attachment_id")
        or raw.get("file_id")
        or upload_data.get("id")
        or upload_data.get("attachment_id")
        or ""
    )
    return {
        "attachment_id": str(attachment_id),
        "url": str(raw.get("url") or upload_data.get("url") or ""),
        "content_type": str(raw.get("content_type") or upload_data.get("content_type") or ""),
        "size": int(raw.get("size") or upload_data.get("size") or 0),
        "filename": str(raw.get("original_filename") or raw.get("filename") or upload_data.get("original_filename") or ""),
    }


def _attachment_ref(info: dict[str, Any], *, context_key: str) -> dict[str, Any]:
    return {
        "id": info["attachment_id"],
        "filename": info["filename"],
        "content_type": info["content_type"],
        "size": info["size"],
        "size_bytes": info["size"],
        "url": info["url"],
        "kind": "file",
        "context_key": context_key,
    }


def _client_for_env(env_name: str) -> tuple[AxClient, dict[str, Any]]:
    """Return a user-authored client for a named login environment."""
    normalized = _normalize_user_env(env_name)
    cfg = _load_user_config(normalized)
    if not cfg:
        console.print(f"[red]No user login found for env '{normalized}'.[/red]")
        console.print(f"Run: axctl login --env {normalized} --url <base-url>")
        raise typer.Exit(1)

    token = str(cfg.get("token") or "")
    if not token:
        console.print(f"[red]User login env '{normalized}' has no token.[/red]")
        raise typer.Exit(1)
    if token.startswith("axp_a_"):
        console.print(f"[red]User login env '{normalized}' contains an agent PAT.[/red]")
        console.print("`--env` selects user-authored QA credentials. Use an agent profile for agent runtime QA.")
        raise typer.Exit(1)

    base_url = str(cfg.get("base_url") or "http://localhost:8001")
    return AxClient(base_url=base_url, token=token), {**cfg, "environment": normalized}


def _space_id_from_item(item: dict[str, Any]) -> str | None:
    value = item.get("id") or item.get("space_id")
    return str(value) if value else None


def _select_default_space_id(spaces_payload: Any) -> str | None:
    items = _extract_items(spaces_payload, ("spaces", "items", "results"))
    if len(items) == 1:
        return _space_id_from_item(items[0])

    for key in ("is_current", "current", "is_default", "default"):
        matches = [item for item in items if item.get(key) is True]
        if len(matches) == 1:
            return _space_id_from_item(matches[0])

    personal = [
        item
        for item in items
        if item.get("is_personal") is True or str(item.get("space_mode", "")).lower() == "personal"
    ]
    if len(personal) == 1:
        return _space_id_from_item(personal[0])
    return None


def _resolve_env_space_id(client: AxClient, env_cfg: dict[str, Any], *, explicit: str | None) -> str:
    if explicit:
        return explicit
    if env_cfg.get("space_id"):
        return str(env_cfg["space_id"])

    spaces_payload = client.list_spaces()
    selected = _select_default_space_id(spaces_payload)
    if selected:
        return selected

    count = _count(spaces_payload, ("spaces", "items", "results"))
    env_label = env_cfg.get("environment") or "selected"
    console.print(f"[red]No default space is configured for env '{env_label}'.[/red]")
    if count:
        console.print(f"{count} visible spaces found; pass --space-id or rerun axctl login --env {env_label} --space-id <id>.")
    else:
        console.print("No visible spaces found for this credential.")
    raise typer.Exit(1)


def _base_url_env_label(base_url: str | None) -> str | None:
    if not base_url:
        return None
    host = base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    first = host.split(".", 1)[0].strip().lower()
    if first and first not in {"www"}:
        return first
    return None


def _configured_matrix_envs() -> list[str]:
    envs: list[str] = []
    users_dir = _global_config_dir() / "users"
    if users_dir.exists():
        for path in sorted(users_dir.glob("*/user.toml")):
            if path.parent.name.startswith("."):
                continue
            envs.append(path.parent.name)

    default_cfg = _load_user_config("default")
    if default_cfg:
        default_label = _base_url_env_label(str(default_cfg.get("base_url") or "")) or "default"
        if default_label not in envs:
            envs.append(default_label)
        elif "default" not in envs:
            envs.append("default")
    return envs


def _matrix_actual_env(requested: str) -> tuple[str, str]:
    """Return (display_label, env_name_to_load)."""
    normalized = _normalize_user_env(requested)
    if _user_config_path(normalized).exists():
        return normalized, normalized

    default_cfg = _load_user_config("default")
    default_label = _base_url_env_label(str(default_cfg.get("base_url") or "")) if default_cfg else None
    if default_cfg and normalized == default_label:
        return normalized, "default"
    return normalized, normalized


def _parse_space_overrides(values: list[str] | None) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            console.print(f"[red]Invalid --space value '{value}'. Expected env=space-id.[/red]")
            raise typer.Exit(1)
        env_name, space_id = value.split("=", 1)
        env_key = _normalize_user_env(env_name)
        if not space_id.strip():
            console.print(f"[red]Invalid --space value '{value}'. Space id cannot be empty.[/red]")
            raise typer.Exit(1)
        overrides[env_key] = space_id.strip()
    return overrides


def _check_summary(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    summary = []
    for check in result.get("checks", []):
        item = {
            "name": check.get("name"),
            "ok": bool(check.get("ok")),
        }
        if "count" in check:
            item["count"] = check["count"]
        if "error" in check:
            item["error"] = check["error"]
        summary.append(item)
    return summary


def _run_contracts(
    *,
    env_name: str | None,
    space_id: str | None,
    limit: int,
    write: bool,
    upload_file: str | None,
    send_message: bool,
    ttl: int,
    cleanup: bool,
) -> dict[str, Any]:
    selected_env: str | None = None
    if env_name:
        client, env_cfg = _client_for_env(env_name)
        selected_env = str(env_cfg.get("environment") or env_name)
        sid = _resolve_env_space_id(client, env_cfg, explicit=space_id)
    else:
        client = get_client()
        sid = resolve_space_id(client, explicit=space_id)
    checks: list[dict[str, Any]] = []

    whoami_payload = _run_check(checks, "auth.whoami", client.whoami)
    _run_check(checks, "spaces.list", client.list_spaces, summarize=_summarize_collection(("spaces", "items", "results")))
    _run_check(checks, "spaces.get", lambda: client.get_space(sid))
    _run_check(
        checks,
        "spaces.members",
        lambda: client.list_space_members(sid),
        summarize=_summarize_collection(("members", "items", "results")),
    )
    _run_check(
        checks,
        "agents.list",
        lambda: client.list_agents(space_id=sid, limit=max(limit, 1)),
        summarize=_summarize_collection(("agents", "items", "results")),
    )
    _run_check(
        checks,
        "tasks.list",
        lambda: client.list_tasks(limit=max(limit, 1), space_id=sid),
        summarize=_summarize_collection(("tasks", "items", "results")),
    )
    _run_check(
        checks,
        "context.list",
        lambda: client.list_context(space_id=sid),
        summarize=_summarize_collection(("context", "items", "results")),
    )
    _run_check(
        checks,
        "messages.list",
        lambda: client.list_messages(limit=max(limit, 1), space_id=sid),
        summarize=_summarize_collection(("messages", "items", "results")),
    )

    artifacts: dict[str, Any] = {}

    if write:
        key = f"qa:{int(time.time())}:{uuid.uuid4().hex[:12]}"
        value = json.dumps(
            {
                "type": "qa_contract_probe",
                "source": "axctl qa contracts",
                "space_id": sid,
                "created_at_unix": int(time.time()),
            }
        )

        _run_check(checks, "context.set", lambda: client.set_context(sid, key, value, ttl=ttl))
        context_get = _run_check(checks, "context.get", lambda: client.get_context(key, space_id=sid))
        artifacts["context_key"] = key
        if context_get is not None and cleanup:
            _run_check(checks, "context.delete", lambda: client.delete_context(key, space_id=sid))

        if upload_file:
            path = Path(upload_file).expanduser().resolve()

            upload_info = _run_check(
                checks,
                "uploads.create",
                lambda: _normalize_upload(client.upload_file(str(path), space_id=sid)),
                summarize=lambda payload: {
                    "filename": payload.get("filename") or path.name,
                    "content_type": payload.get("content_type"),
                    "size": payload.get("size"),
                },
            )

            if isinstance(upload_info, dict) and upload_info.get("attachment_id"):
                filename = upload_info.get("filename") or path.name
                context_key = build_upload_context_key(filename, upload_info["attachment_id"])
                context_value = {
                    "type": "file_upload",
                    "source": "qa_contract_probe",
                    "attachment_id": upload_info["attachment_id"],
                    "context_key": context_key,
                    "filename": filename,
                    "content_type": upload_info.get("content_type"),
                    "size": upload_info.get("size"),
                    "url": upload_info.get("url"),
                }
                if path.stat().st_size <= 50_000 and str(upload_info.get("content_type", "")).startswith("text/"):
                    context_value["content"] = path.read_text(errors="replace")

                _run_check(
                    checks,
                    "uploads.context.set",
                    lambda: client.set_context(sid, context_key, json.dumps(context_value), ttl=ttl),
                )
                _run_check(checks, "uploads.context.get", lambda: client.get_context(context_key, space_id=sid))
                artifacts["upload_context_key"] = context_key
                artifacts["attachment_id"] = upload_info["attachment_id"]

                if send_message:
                    message_content = f"QA upload contract probe: `{filename}` (context: `{context_key}`)"
                    message = _run_check(
                        checks,
                        "uploads.message.send",
                        lambda: client.send_message(
                            sid,
                            message_content,
                            attachments=[_attachment_ref(upload_info, context_key=context_key)],
                        ),
                    )
                    if isinstance(message, dict):
                        artifacts["message_id"] = message.get("id") or message.get("message", {}).get("id")

                if cleanup:
                    _run_check(
                        checks,
                        "uploads.context.delete",
                        lambda: client.delete_context(context_key, space_id=sid),
                    )

    ok = all(check["ok"] for check in checks)
    result = {
        "ok": ok,
        "environment": selected_env,
        "space_id": sid,
        "principal": {
            "username": whoami_payload.get("username") if isinstance(whoami_payload, dict) else None,
            "principal_type": whoami_payload.get("principal_type") if isinstance(whoami_payload, dict) else None,
            "bound_agent": whoami_payload.get("bound_agent") if isinstance(whoami_payload, dict) else None,
        },
        "mode": "write" if write else "read_only",
        "artifacts": artifacts,
        "checks": checks,
    }
    return result


def _write_artifact(path: str | Path, result: dict[str, Any]) -> Path:
    artifact_path = Path(path).expanduser().resolve()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return artifact_path


def _preflight_result(
    *,
    target: str,
    env_name: str | None,
    space_id: str | None,
    limit: int,
    write: bool,
    upload_file: str | None,
    send_message: bool,
    ttl: int,
    cleanup: bool,
) -> dict[str, Any]:
    result = _run_contracts(
        env_name=env_name,
        space_id=space_id,
        limit=limit,
        write=write,
        upload_file=upload_file,
        send_message=send_message,
        ttl=ttl,
        cleanup=cleanup,
    )
    result["preflight"] = {
        "target": target,
        "passed": bool(result.get("ok")),
        "generated_at_unix": int(time.time()),
        "command": "ax qa preflight",
    }
    return result


def _emit_result(result: dict[str, Any], *, as_json: bool, artifact_path: Path | None = None) -> None:
    ok = bool(result.get("ok"))
    if as_json:
        print_json(result)
    else:
        console.print(f"[bold]aX contract smoke:[/bold] {'PASS' if ok else 'FAIL'}")
        console.print(f"space_id={result.get('space_id')} mode={result.get('mode')}")
        for check in result.get("checks", []):
            status = "[green]PASS[/green]" if check["ok"] else "[red]FAIL[/red]"
            suffix = f" count={check['count']}" if "count" in check else ""
            console.print(f"  {status} {check['name']} ({check['duration_ms']}ms){suffix}")
            if not check["ok"]:
                console.print(f"    [red]{check['error']}[/red]")
        if artifact_path:
            console.print(f"artifact={artifact_path}")

    if not ok:
        raise typer.Exit(1)


@app.command("contracts")
def contracts(
    env_name: Optional[str] = typer.Option(
        None,
        "--env",
        help="Use a named user-login environment created with `axctl login --env`",
    ),
    space_id: Optional[str] = typer.Option(None, "--space-id", help="Override target space"),
    limit: int = typer.Option(10, "--limit", help="Small collection read limit"),
    write: bool = typer.Option(False, "--write", help="Run mutating round-trip checks"),
    upload_file: Optional[str] = typer.Option(None, "--upload-file", help="Upload this file during write checks"),
    send_message: bool = typer.Option(False, "--send-message", help="Send a visible QA message for upload checks"),
    ttl: int = typer.Option(300, "--ttl", help="TTL for temporary context writes"),
    cleanup: bool = typer.Option(True, "--cleanup/--keep", help="Delete temporary context keys after write checks"),
    as_json: bool = JSON_OPTION,
):
    """Run API-first smoke checks against the active environment.

    Default mode is read-only. Use --write when validating dev/staging flows
    that create temporary context, upload files, or emit visible message
    signals.
    """
    result = _run_contracts(
        env_name=env_name,
        space_id=space_id,
        limit=limit,
        write=write,
        upload_file=upload_file,
        send_message=send_message,
        ttl=ttl,
        cleanup=cleanup,
    )
    _emit_result(result, as_json=as_json)


@app.command("preflight")
def preflight(
    target: str = typer.Option(
        "mcp-ui",
        "--for",
        help="Target being gated, e.g. mcp-jam, widget, playwright, ui",
    ),
    env_name: Optional[str] = typer.Option(
        None,
        "--env",
        help="Use a named user-login environment created with `axctl login --env`",
    ),
    space_id: Optional[str] = typer.Option(None, "--space-id", help="Override target space"),
    limit: int = typer.Option(10, "--limit", help="Small collection read limit"),
    write: bool = typer.Option(False, "--write", help="Run mutating round-trip checks"),
    upload_file: Optional[str] = typer.Option(None, "--upload-file", help="Upload this file during write checks"),
    send_message: bool = typer.Option(False, "--send-message", help="Send a visible QA message for upload checks"),
    ttl: int = typer.Option(300, "--ttl", help="TTL for temporary context writes"),
    cleanup: bool = typer.Option(True, "--cleanup/--keep", help="Delete temporary context keys after write checks"),
    artifact: Optional[str] = typer.Option(
        None,
        "--artifact",
        help="Write the preflight result JSON to this path for CI/MCP/UI wrappers",
    ),
    as_json: bool = JSON_OPTION,
):
    """Gate MCP Jam, widget, or Playwright checks on API-first contracts."""
    result = _preflight_result(
        target=target,
        env_name=env_name,
        space_id=space_id,
        limit=limit,
        write=write,
        upload_file=upload_file,
        send_message=send_message,
        ttl=ttl,
        cleanup=cleanup,
    )
    artifact_path = Path(artifact).expanduser().resolve() if artifact else None
    if artifact_path:
        result["preflight"]["artifact"] = str(artifact_path)
        _write_artifact(artifact_path, result)
    _emit_result(result, as_json=as_json, artifact_path=artifact_path)


@app.command("matrix")
def matrix(
    env_names: Optional[list[str]] = typer.Option(
        None,
        "--env",
        "-e",
        help="Named user-login environment to check. Repeatable. Defaults to all configured user logins.",
    ),
    target: str = typer.Option(
        "mcp-ui",
        "--for",
        help="Target being gated, e.g. mcp-jam, widget, playwright, ui",
    ),
    space_id: Optional[str] = typer.Option(None, "--space-id", help="Use this space for every environment"),
    space_overrides: Optional[list[str]] = typer.Option(
        None,
        "--space",
        help="Per-env space override as env=space-id. Repeatable.",
    ),
    limit: int = typer.Option(10, "--limit", help="Small collection read limit"),
    artifact_dir: Optional[str] = typer.Option(
        None,
        "--artifact-dir",
        help="Write one preflight JSON artifact per environment into this directory",
    ),
    as_json: bool = JSON_OPTION,
):
    """Run auth doctor plus QA preflight across environments."""
    requested_envs = list(env_names or _configured_matrix_envs())
    if not requested_envs:
        console.print("[red]No user-login environments found.[/red] Run axctl login --env dev --url <base-url>.")
        raise typer.Exit(1)

    space_map = _parse_space_overrides(space_overrides)
    rows: list[dict[str, Any]] = []
    artifact_root = Path(artifact_dir).expanduser().resolve() if artifact_dir else None
    matrix_started = int(time.time())

    for requested in requested_envs:
        label, actual_env = _matrix_actual_env(requested)
        selected_space = space_map.get(label) or space_map.get(actual_env) or space_id
        doctor = diagnose_auth_config(env_name=actual_env, explicit_space_id=selected_space)
        effective = doctor.get("effective", {})
        preflight_payload: dict[str, Any] | None = None
        preflight_error: dict[str, Any] | None = None
        artifact_path: Path | None = None

        if doctor.get("ok"):
            try:
                preflight_payload = _preflight_result(
                    target=target,
                    env_name=actual_env,
                    space_id=selected_space,
                    limit=limit,
                    write=False,
                    upload_file=None,
                    send_message=False,
                    ttl=300,
                    cleanup=True,
                )
                if artifact_root:
                    artifact_path = artifact_root / f"{label}-preflight.json"
                    preflight_payload["preflight"]["artifact"] = str(artifact_path)
                    _write_artifact(artifact_path, preflight_payload)
            except typer.Exit as exc:
                preflight_error = {"type": "Exit", "code": exc.exit_code}
            except Exception as exc:
                preflight_error = _error_payload(exc)

        row = {
            "env": label,
            "requested_env": requested,
            "selected_env": doctor.get("selected_env"),
            "principal_intent": effective.get("principal_intent"),
            "auth_source": effective.get("auth_source"),
            "base_url": effective.get("base_url"),
            "host": effective.get("host"),
            "space_id": effective.get("space_id"),
            "warnings": doctor.get("warnings", []),
            "doctor_ok": bool(doctor.get("ok")),
            "doctor_problems": doctor.get("problems", []),
            "preflight_ok": bool(preflight_payload and preflight_payload.get("ok")),
            "artifact_path": str(artifact_path) if artifact_path else None,
            "preflight_error": preflight_error,
            "checks": _check_summary(preflight_payload),
        }
        rows.append(row)

    result = {
        "ok": all(row["doctor_ok"] and row["preflight_ok"] for row in rows),
        "target": target,
        "generated_at_unix": matrix_started,
        "envs": rows,
    }

    if artifact_root:
        matrix_path = artifact_root / "matrix.json"
        result["artifact_path"] = str(matrix_path)
        _write_artifact(matrix_path, result)

    if as_json:
        print_json(result)
    else:
        table = Table(show_header=True)
        table.add_column("Env")
        table.add_column("Intent")
        table.add_column("Host")
        table.add_column("Space")
        table.add_column("Auth")
        table.add_column("Doctor")
        table.add_column("Preflight")
        table.add_column("Warnings")
        for row in rows:
            table.add_row(
                str(row["env"]),
                str(row["principal_intent"]),
                str(row["host"]),
                str(row["space_id"]),
                str(row["auth_source"]),
                "PASS" if row["doctor_ok"] else "FAIL",
                "PASS" if row["preflight_ok"] else "FAIL",
                str(len(row["warnings"])),
            )
        console.print(table)
        if artifact_root:
            console.print(f"artifact_dir={artifact_root}")

    if not result["ok"]:
        raise typer.Exit(1)
