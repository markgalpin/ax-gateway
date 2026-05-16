# ADR-008: Agent Status Model — Operator Intent, Liveness Escalation, and UI Tone

**Status:** Accepted — implemented in `fix/gateway-agent-status-colors`

**Depends on:** [ADR-007: Agent Classes and Gateway Signaling Contract](ADR-007-agent-classes-and-signals.md)

## Context

The Gateway UI and CLI need to communicate agent health to operators clearly
and consistently across all agent classes defined in ADR-007. Early
implementations derived display state from observed runtime signals alone —
presence, heartbeat age, connection flags — without a consistent semantic
model. This produced several problems:

- A `claude_code_channel` agent with a dead SSE subscription showed GREEN
  because MCP pings kept the heartbeat fresh and the process PID was alive.
- An agent the operator had stopped showed the same gray as an agent that had
  crashed — "intentionally off" and "broken" were visually indistinguishable.
- An agent that had been unreachable for five minutes looked the same as one
  that had missed a single heartbeat thirty seconds ago.
- Agent-type-specific branches in the UI accumulated over time, making it
  harder to reason about how new agent types would render.

## Decision

### 1. Operator intent is evaluated before any health signal

Three registry fields express operator intent and are checked in priority order
before any runtime health signal:

1. `lifecycle_phase == "hidden"` or `lifecycle_phase == "archived"` → gray
   immediately, regardless of observed runtime state. Operators hide or archive
   agents to explicitly remove them from active operation — a common reason is
   that the agent did not record its shutdown correctly and still appears yellow
   or red. The operator's decision overrides the signal.
2. `desired_state == "stopped"` AND `connected == false` → gray ("Stopped")
3. `desired_state == "stopped"` AND `connected == true` → yellow ("Stopping",
   transition in progress)
4. `desired_state == "running"` → all subsequent health checks apply

All agent classes defined in ADR-007 pass through these checks before any
class-specific logic.

### 2. Four tones with explicit semantic boundaries

| Tone | Color | Meaning |
|------|-------|---------|
| `muted` | gray | Operator has intentionally taken this agent out of active operation: stopped, hidden, or archived. |
| `warning` | yellow | Agent needs attention: transitioning, pending approval, or degraded. |
| `error` | red | Agent is desired=running but cannot function. |
| `ok` | green | Agent is healthy and ready. |

Gray is reserved exclusively for intentional-off states. Any agent that is
desired=running but not working correctly renders red, not gray.

### 3. Two-threshold liveness escalation in the daemon sweep

The Gateway daemon sweep (`_derive_liveness`) applies two thresholds uniformly
across all agent classes:

- **75 seconds** without a heartbeat → `liveness = "stale"` → yellow
- **300 seconds** without a heartbeat → `liveness = "offline"` → red (for LIVE
  mode agents)

This escalation runs in the daemon and writes to the registry. The UI reads
the pre-computed `liveness` and `presence` fields — no time-based logic in
JavaScript. Polling mailbox and on-demand agents are exempt from escalation
via the INBOX/ON-DEMAND mode bypass described in ADR-007.

### 4. OFFLINE presence is meaningful only for LIVE mode agents

`_derive_presence()` maps `liveness = "offline"` to presence `OFFLINE` only
when `mode == "LIVE"`. For INBOX and ON-DEMAND agents, availability is defined
by queue access or launch capability — not an active connection — so offline
liveness falls through to `IDLE`. This preserves the semantic accuracy of the
presence field: OFFLINE means "was supposed to be connected and isn't", which
only applies to always-on listeners.

### 5. Gateway computes health; UI reads it

Health state (liveness, presence, confidence, reachability) is computed by the
Gateway daemon sweep and stored in the registry. The UI renders whatever the
daemon computed. This keeps class-specific logic in one place and makes new
agent classes automatically compatible with the status model as long as they
follow the signaling contract in ADR-007.

## Known Gaps

One case in the status table currently requires a class-specific check in the
UI — marked *(gap)* in the table below. This is a consequence of the Gateway
not yet computing a fully generic semantic field for that case. The root cause
and discussion of a possible future improvement is documented in
[ADR-007 § Known Gaps](ADR-007-agent-classes-and-signals.md#known-gaps).

## Consequences

- **Positive:** Operators get consistent, predictable status signals across all
  agent classes. Gray means "I stopped this." Red means "this is broken."
- **Positive:** New agent classes require no UI changes to render correctly,
  provided they follow the signaling contract in ADR-007.
- **Positive:** Transient heartbeat gaps show yellow before escalating to red,
  reducing false alarms.
- **Positive:** The `desired_state` / `lifecycle_phase` checks eliminate
  separate "stopped" and "hidden" branches in class-specific code paths.
- **Negative:** The 300-second escalation threshold is fixed. Agents with
  legitimately long quiet periods between heartbeats may incorrectly escalate
  — though INBOX and ON-DEMAND agents are protected by the LIVE-mode-only
  OFFLINE rule.
- **Negative:** The two thresholds (75s, 300s) are not yet configurable per
  agent class. They are conservative defaults intended to work generically.

## Notes

The `sse_connected` field introduced for `claude_code_channel` is a specialised
extension of this model: it allows an attached session to report SSE
subscription health separately from process liveness, surfacing `sse_disconnected`
reachability when the MCP process is alive but the platform SSE stream is broken.
This follows the same principle — Gateway computes health from agent-reported
signals, UI reads the result. See the attached session signaling contract in
ADR-007 for details.

### Status mapping before and after this ADR

| Condition | Gateway signal | UI class check | Label (before) | Tone (before) | Label (after) | Tone (after) | Notes |
|---|---|---|---|---|---|---|---|
| `lifecycle_phase == "hidden"` | `lifecycle_phase` | generic | *(not handled)* | *(live dot shown)* | "Hidden" | gray | New — operator intent override |
| `lifecycle_phase == "archived"` | `lifecycle_phase` | generic | *(not handled)* | *(live dot shown)* | "Archived" | gray | New — operator intent override |
| External plugin, `desired=stopped`, actually stopped | `desired_state`, `connected` | generic | "Plugin stopped" | yellow | "Stopped" | gray | Stopped = gray |
| External plugin, `desired=stopped`, still running | `desired_state`, `connected` | generic | "Plugin stopping" | yellow | "Stopping" | yellow | Unchanged |
| External plugin, `desired=running`, not connected | `external_runtime_managed`, `connected` | `externalManaged` *(gap)* | "Plugin not attached" | yellow | "Plugin not attached" | red | Red — desired=running but broken |
| External plugin, `desired=running`, connected | *(falls through)* | generic | *(falls through)* | green | *(falls through)* | green | Unchanged — treated as active |
| `desired=stopped`, `connected=false` | `desired_state`, `connected` | generic | "Stopped" | gray | "Stopped" | gray | Unchanged |
| `desired=stopped`, `connected=true` | `desired_state`, `connected` | generic | "Stopped" | gray | "Stopping" | yellow | New — transition shown as yellow |
| Approval pending | `approval_state` | generic | "Needs approval" | yellow | "Needs approval" | yellow | Unchanged |
| Approval rejected | `approval_state` | generic | "Rejected" | red | "Rejected" | red | Unchanged |
| Setup error | `presence`, `confidence_reason` | generic | "Setup error" | red | "Setup error" | red | Unchanged |
| `BLOCKED` + binding drift | `confidence`, `confidence_reason` | generic | "Needs approval" | yellow | "Needs approval" | yellow | Unchanged |
| `BLOCKED` (other) | `confidence` | generic | "Blocked" | yellow | "Blocked" | red | Red — gateway blocking = broken |
| Attach in progress | `current_status`, `connected` | generic | "Starting" | yellow | "Starting" | yellow | Unchanged |
| Mailbox with pending work | `backlog_depth` / `queue_depth` | `isMailboxRuntime` (uses `mode=INBOX`) | "N messages" | yellow | "N messages" | yellow | Unchanged |
| Mailbox idle | *(no specific signal)* | `isMailboxRuntime` (uses `mode=INBOX`) | "Inbox" | gray | "Inbox" | green | Green — healthy passive state |
| Attached + SSE disconnected | `reachability=sse_disconnected` | `isAttachedRuntime` *(gap)* | "SSE down" | red | "SSE down" | red | Unchanged (see companion PR #32) |
| Attached runtime + `presence=STALE` | `reachability=attach_required` | generic | "Stopped" | gray | "Not running" | red | Red — process gone, new label |
| `presence=STALE` (other runtimes) | `presence` (from `liveness`) | generic | "Stale" | yellow | "Stale" | yellow | Unchanged |
| `presence=OFFLINE` | `presence` (from `liveness`) | generic | "Offline" | gray | "Offline" | red | Red — desired=running but unreachable |
| `presence=ACTIVE/LIVE` or `connected=true` | `presence`, `connected` | generic | "Active" | green | "Active" | green | Unchanged |
| `confidence=MEDIUM`, `launch_available` | `confidence`, `confidence_reason` | generic | "Ready" | green | "Ready" | green | Unchanged |
| `confidence=HIGH` | `confidence` | generic | "Ready" | green | "Ready" | green | Unchanged |
| `presence=IDLE` | `presence` | generic | "Idle" | gray | "Idle" | green | Green — connected, healthy, quiet |
| Fallback (unrecognised state) | *(none)* | generic | "Idle" | gray | "Unknown" | yellow | Yellow — needs attention |
