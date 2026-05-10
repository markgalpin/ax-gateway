# ADR-002: Proxy Uses a Flat Allowlist, Not Per-Agent ACLs

**Status:** Accepted (Phase 4 will replace with `use`/`admin` tiers)

## Context

Gateway proxies API calls from local agent sessions through the `/local/proxy`
endpoint. The proxy needs to control which `AxClient` methods an agent can
invoke — unrestricted proxy access would let any local agent session perform
admin operations using the operator's credentials.

Two approaches were considered:

1. **Per-agent ACLs** — each agent registration declares which methods it may
   call. The proxy checks the agent's ACL before dispatching.
2. **Flat allowlist** — a single `_LOCAL_PROXY_METHODS` dict shared by all
   agents. Any method not in the list is rejected.

## Decision

Use a flat allowlist (`_LOCAL_PROXY_METHODS` in `ax_cli/commands/gateway.py`,
line 540). All agent sessions share the same allowed methods.

Current allowlist: `whoami`, `list_spaces`, `list_agents`,
`list_agents_availability`, `list_context`, `get_context`, `list_messages`,
`get_message`, `search_messages`, `list_tasks`, `get_task`, `update_task`.

Write operations (`send_message`, `create_task`, `upload_file`) go through
dedicated endpoints (`/local/send`, `/local/tasks`) with additional validation.

## Consequences

- **Positive:** Simple to understand and audit. One dict, one check.
- **Positive:** No per-agent configuration surface to get wrong.
- **Negative:** No granularity — an echo-test agent has the same proxy access as
  a coding sentinel. An inbox agent can call `update_task` even if it should
  only read messages.
- **Negative:** Adding a sensitive method to the allowlist grants it to all
  agents. `upload_file` is intentionally excluded because an inbox agent with
  unrestricted file upload is a trust boundary violation.

## Replacement Plan

Issue #146 proposes a `use`/`admin` tier model. Each proxy method gets a tier
annotation. Agent registrations declare their tier. The proxy checks
`agent_tier >= method_tier` before dispatching. This preserves the simplicity
of a central list while adding per-agent granularity.
