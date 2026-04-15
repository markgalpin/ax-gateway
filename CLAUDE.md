# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`ax-cli` is the Python CLI for the [aX Platform](https://dev.paxai.app) — a multi-agent communication system. It wraps the aX REST API, providing commands for messaging, task management, agent discovery, key management, and SSE event streaming. The entrypoint command is `ax` (the package is published on PyPI as `axctl`).

The goal for this repo: every command works, every error message is actionable, and the docs match reality. Validate changes against a local backend before opening a PR.

## Development Commands

```bash
# Install (editable mode)
pip install -e .

# Run CLI
ax --help
ax auth whoami
ax send "hello"
ax send "quick update" --skip-ax

# Test and lint
uv run pytest
uv run ruff check .
```

## Architecture

**Stack:** Python 3.11+, Typer (CLI framework), httpx (HTTP client), Rich (terminal output)

**Module layout:**

- `ax_cli/main.py` — Typer app definition. Registers all subcommand groups and the top-level `ax send` shortcut.
- `ax_cli/client.py` — `AxClient` class wrapping all aX REST API endpoints. Stateless HTTP client using httpx. Agent identity is passed via `X-Agent-Name` / `X-Agent-Id` headers.
- `ax_cli/config.py` — Config resolution and client factory. Runtime resolution order: CLI flag → env var → project-local `.ax/config.toml` → active profile → global `~/.ax/config.toml`. User login credentials are separate in `~/.ax/user.toml` or `~/.ax/users/<env>/user.toml`. The `get_client()` factory is the standard way to obtain an authenticated runtime client.
- `ax_cli/output.py` — Shared output helpers: `print_json()`, `print_table()`, `print_kv()`, `handle_error()`, `mention_prefix()`. All commands support `--json` for machine-readable output.
- `ax_cli/commands/` — One module per command group (auth, keys, agents, messages, tasks, events). Each creates a `typer.Typer()` sub-app registered in `main.py`.

**Key patterns:**

- Every command gets its client via `config.get_client()` and resolves space/agent from the config cascade.
- API responses are defensively handled — commands check for both list and dict-wrapped response formats.
- `messages send` waits for a reply by default (polls `list_replies` every 1s). Use `--skip-ax` to send without waiting.
- SSE streaming (`events stream`) does manual line-by-line SSE parsing with event-type filtering.

## Config System

Runtime config lives in `.ax/config.toml` (project-local, preferred), named profiles under `~/.ax/profiles/<name>/profile.toml`, or `~/.ax/config.toml` (global fallback for defaults only). Project root is found by walking up to the nearest `.git` directory. Runtime key fields: `token`, `token_file`, `base_url`, `agent_name`, `agent_id`, `space_id`, `principal_type`. Env vars include `AX_TOKEN`, `AX_BASE_URL`, `AX_AGENT_NAME`, `AX_AGENT_ID`, and `AX_SPACE_ID`.

User login credentials are deliberately separate from runtime agent config:

- Default user login: `~/.ax/user.toml`
- Named user login: `~/.ax/users/<env>/user.toml`
- Selection: `AX_ENV`, `AX_USER_ENV`, `axctl login --env`, and user-authored commands that take `--env`

Do not put reusable user PATs in `.ax/config.toml` or `~/.ax/config.toml`. User PATs bootstrap and mint agent credentials; agent runtime work should use agent PAT profiles or project-local agent runtime config.
