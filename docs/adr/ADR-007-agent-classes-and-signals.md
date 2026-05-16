# ADR-007: Agent Classes and Gateway Signaling Contract

**Status:** Accepted — core agent classes reflect current implementation; boundary completion ongoing (see Known Gaps below)

## Context

The Gateway manages a growing set of agent types with fundamentally different
runtime models: some are processes the daemon starts and supervises directly,
others are external processes that report their own state, others are passive
mailboxes, and others are attached sessions the daemon cannot control. Without
a defined classification and signaling contract, each new agent type required
bespoke handling in the daemon sweep, the health derivation logic, and the UI.

This ADR defines the canonical agent classes and specifies what each class is
responsible for reporting to the Gateway registry.

![Gateway status architecture](../images/gateway-status-architecture.svg)

This ADR (ADR-007) defines the left boundary: what each agent class is
responsible for reporting to the Gateway registry.
[ADR-008](ADR-008-agent-status-model.md) defines the right boundary: how the
daemon translates those signals into operator-visible status.

## Decision

### Agent Classes

Five classes cover all current and anticipated agent models:

| Class | Lifecycle ownership | Signaling model | Gateway mode |
|---|---|---|---|
| **Daemon-managed** | Daemon starts, supervises, and stops the process | Daemon sets registry state directly; runtime sends heartbeats from its own listener loop | LIVE |
| **Attached session** | External process started independently; daemon observes but does not own | MCP pings keep `last_seen_at` fresh; agent reports subsystem health via dedicated fields | LIVE |
| **Polling mailbox** | No continuous runtime; agent polls on its own schedule | Check-in on each poll; no continuous heartbeat expected between polls | INBOX |
| **External plugin** | Plugin process managed externally; daemon tracks via periodic heartbeats | Plugin sends heartbeats to `/local/heartbeat`; daemon observes arrival and age | LIVE |
| **On-demand** | Daemon launches on message arrival; process exits when done | Daemon sets state at launch and exit; no heartbeat between launches | ON-DEMAND |

The polling mailbox and attached session classes are the most commonly confused.
The key distinction is delivery model, not runtime sophistication:

![Inbox vs channel delivery](../images/inbox-vs-channel.svg)

The `mode` field that the UI reads to determine delivery model is computed by
the Gateway from two template registration fields:

| `placement` | `activation` | `mode` |
|---|---|---|
| `mailbox` | any | `INBOX` |
| `attached` or `hosted` | `persistent` or `attach_only` | `LIVE` |
| `hosted` | `on_demand` | `ON-DEMAND` |

**For new agent classes:** register with `placement=mailbox` to enter the
polling class; register with `placement=attached` and `activation=attach_only`
for the attached session class; `placement=hosted` with `activation=persistent`
for daemon-managed. The Gateway derives `mode` automatically — do not attempt
to set it directly.


### Current Templates and Runtime Types by Class

| Class | Template ID | Runtime type(s) | Notes |
|---|---|---|---|
| **Daemon-managed** | `echo_test` | `echo` | Built-in test runtime; echoes messages back |
| **Daemon-managed** | `hermes` | `hermes_sentinel` | Hermes sentinel process supervised by daemon; sub-runtimes: `claude_cli`, `openai_sdk`, `codex_cli`, `hermes_sdk`, `groq_sdk` *(not yet vendored)*, `mistral_sdk` *(in progress)* |
| **Daemon-managed** | `sentinel_cli` | `sentinel_cli` | Direct CLI sentinel subprocess |
| **Daemon-managed** | *(exec template)* | `exec` | Generic subprocess launcher; fallback for unknown templates |
| **Attached session** | `claude_code_channel` | `claude_code_channel` | MCP stdio bridge; attached by Claude Code or compatible client |
| **Polling mailbox** | `pass_through` | `inbox` | Polling mailbox for pass-through agents |
| **Polling mailbox** | `inbox` | `inbox` | System inbox; used for switchboard and notification agents |
| **Polling mailbox** | `service_account` | *(no runtime)* | Outbound-only service account; no runtime process |
| **External plugin** | `hermes` | `hermes_plugin` | Hermes plugin process managed outside the daemon |
| **On-demand** | `ollama` | `hermes_sentinel` (via hermes) | Ollama bridge; launched on send, exits when done |

### Signaling Contract

Each agent class is responsible for keeping the following registry fields
current. The Gateway daemon derives `liveness`, `presence`, `confidence`, and
`reachability` from these inputs — agents must not attempt to set those derived
fields directly.

#### Daemon-managed

| Field | Who sets it | When |
|---|---|---|
| `effective_state` | Daemon | On every lifecycle transition |
| `last_seen_at` | Runtime (via `send_heartbeat`) | Continuously, while listener loop is running |
| `current_status` / `current_activity` | Runtime | On work state transitions |

The daemon owns `effective_state` authoritatively. If the process crashes, the
daemon sets `effective_state=error`. The runtime's own heartbeats are
supplementary — their absence causes staleness escalation, but the daemon's
direct state writes are the primary authority.

#### Attached session

| Field | Who sets it | When |
|---|---|---|
| `effective_state` | Agent (via `_touch_gateway_channel_entry`) | On attach; stays `running` while MCP process is alive |
| `last_seen_at` | Agent (via MCP ping handler) | On every MCP ping from the client (continuous) |
| `sse_connected` | Agent (via `_sse_loop` and `_sse_heartbeat_loop`) | On SSE connect/failure; refreshed every 30s |

**Critical constraint:** `effective_state=running` must not be used to represent
overall health. If a critical subsystem (such as the platform SSE subscription)
is broken, this must be reported via a dedicated field (`sse_connected=false`)
rather than by holding `effective_state` at a healthy value. The daemon cannot
directly observe the internal state of an attached session.

#### Polling mailbox

| Field | Who sets it | When |
|---|---|---|
| `backlog_depth` / `queue_depth` | Gateway (on message arrival) | When a message is queued |
| `last_work_received_at` | Agent (on poll) | On each successful poll |

The liveness escalation thresholds do not meaningfully apply to polling mailbox
agents because quiet periods between polls are expected and normal. The Gateway
uses INBOX mode to bypass liveness-based confidence scoring for these agents —
queue availability, not heartbeat freshness, determines their health.

#### External plugin

| Field | Who sets it | When |
|---|---|---|
| `external_runtime_state` | Plugin process (via `/local/heartbeat`) | Periodically while running |
| `external_runtime_managed` | Set at registration | Once |
| `last_seen_at` | Updated on each heartbeat | Continuously |

A gap in plugin heartbeats causes `liveness=stale`, then `liveness=offline`
after the escalation threshold. The Gateway derives `reachability=unavailable`
for external plugins that have gone stale or offline (see Known Gaps for a
possible future improvement).

#### On-demand

| Field | Who sets it | When |
|---|---|---|
| `effective_state` | Daemon | At launch (`running`) and exit (`stopped` or `error`) |

Between launches, `effective_state` is not `running`, so the liveness
escalation does not fire. The daemon sets `reachability=launch_available` for
healthy on-demand agents regardless of whether a process is currently running.

Every managed agent has three layers of state that the signaling contract
operates on — desired, lifecycle phase, and effective:

![Agent lifecycle states](../images/agent-lifecycle-states.svg)

### Registry Signals vs Platform Heartbeats

The signaling contract described in this ADR covers two distinct communication
paths that must not be confused:

| | Registry signals | Platform heartbeats |
|---|---|---|
| **Destination** | Local Gateway registry (`~/.ax/gateway/`) | aX platform (`paxai.app`) |
| **Purpose** | Gateway derives local health state (liveness, confidence, UI display) | Platform updates agent presence visible to other users and agents |
| **Who sends** | Agent process or Gateway daemon | Agent runtime using an **agent-bound** token |
| **Token required** | N/A — local filesystem write | Agent-bound PAT/JWT; user tokens are rejected with 400 |
| **Examples** | `effective_state`, `last_seen_at`, `sse_connected` | `send_heartbeat(status="connected")`, `send_heartbeat(status="offline")` |
| **Defined in** | This ADR (ADR-007) | [ADR-009](ADR-009-platform-heartbeat-contract.md) |

### What agents must NOT do

- Set `effective_state=running` while a critical subsystem is broken. Use
  dedicated fields for subsystem health.
- Rely on the UI to infer agent class from raw fields (`template_id`,
  `runtime_type`, `external_runtime_managed`). Class-specific health signals
  must be translated by the Gateway into generic semantic fields (`liveness`,
  `reachability`, `presence`, `confidence`) before the UI reads them.
- Send heartbeats faster than necessary. The stale threshold is 75 seconds;
  heartbeats every 30 seconds are sufficient for all current agent classes.

## Known Gaps

The following cases represent places where the Gateway does not yet fully
uphold its side of the contract — it has not computed a generic semantic field
that would allow the UI to operate without class-specific knowledge. As a
consequence, the UI currently contains type-specific checks that compensate
(documented in [ADR-008](ADR-008-agent-status-model.md)):

- **External plugin not attached**: the UI checks `externalManaged && !connected`
  directly rather than a gateway-computed reachability value. This is a known
  violation of the principle that all health logic is computed by the gateway.
  A `reachability=plugin_not_attached` value was explored but reverted: the UI
  still needs to combine with `presence` to differentiate stale (yellow, may
  self-reconnect) from offline (red, persistent failure), and
  `external_runtime_managed` is itself a gateway-provided flag rather than
  type-specific logic inferred by the UI. The added complexity of a new
  reachability value did not justify the marginal boundary improvement. The
  correct long-term fix is for the gateway to emit a richer reachability value
  that encodes both the class and the severity, eliminating both checks.


## Consequences

- **Positive:** New agent types can be classified into one of the five classes
  and immediately inherit the correct signaling contract without bespoke
  handling.
- **Positive:** The Gateway's health derivation logic (`_derive_liveness`,
  `_derive_reachability`, `_derive_confidence`) can be written generically
  against the contract rather than against individual agent types.
- **Negative:** The class boundary for attached sessions is soft — the daemon
  cannot enforce that an attached session reports `sse_connected` accurately.
  The contract is advisory for agent implementations the daemon does not own.
- **Negative:** On-demand agents with long launch times may appear briefly
  stale before the daemon updates `effective_state`. This is a known gap;
  operators should interpret stale on-demand agents as launching, not failed.
