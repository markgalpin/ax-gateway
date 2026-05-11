# ax-gateway Roadmap

> **Last updated:** May 2026

## Where We Are

ax-gateway is an open-source CLI and local Gateway daemon for multi-agent AI orchestration. It connects AI agents to workspaces, manages credentials, and routes messages between humans and agents through a local trust boundary.

Current state:

- **746+ tests passing**
- **7 MCP tools live**
- Hermes plugin runtime shipped - enables pluggable agent runtimes
- Accepted to Platform One marketplace (DoD distribution channel)
- IL2 deployment in production with free trial available
- Active contributor community with multiple engineers across CLI, MCP, and agent capabilities

---

## Release Plan

### 0.7.0 - Stability (May 2026)

Phase 2 reliability work wrapping up. This release captures two months of hardening:

- Hermes plugin runtime - pluggable agent runtime architecture
- Host header security validation
- Tier annotations for proxy methods
- CLA enforcement and community standards
- Archive/restore lifecycle fixes
- Retry backoff for rate limiting (429 handling)
- Corruption repair and system prompt improvements
- 20+ PRs merged in the last week alone

### 0.8.0 - Credential Unification (Q3 2026)

Phase 3 - the `get_authoring_client()` refactor. Every command will route through a single credential factory, replacing ~130 call sites across 20 modules. This is the foundation for the security improvements in the next release.

Also in scope:

- Expanded LLM provider support through the Hermes runtime (additional providers beyond OpenAI)
- Agent framework templates for popular orchestration libraries
- Test coverage push toward 40%
- Repo consolidation from earlier platform repositories

### 0.9.0 - Process Attestation (Q4 2026)

Phase 4 - the security long pole. Eliminates tokens stored on disk by moving to a Unix domain socket architecture with process-level attestation (`SO_PEERCRED`).

Key changes:

- Session handle model replaces file-based token storage
- `use` / `admin` tier system for proxy method permissions
- Gateway becomes the sole credential holder - agents never touch raw tokens
- Operator approval workflows for sensitive operations

### 1.0.0 GA (Q1 2027)

General availability release. Feature-complete platform with:

- Multi-model support (Claude, GPT-4o, Gemini, Grok, LeapfrogAI)
- Full MCP protocol integration with remote transport
- Process attestation hardened and production-tested
- IL5 security posture
- Comprehensive test coverage
- Stable API surface

---

## Three Areas of Development

### CLI

The command-line interface and credential management layer. Includes onboarding commands, space management, key lifecycle, and the developer experience for interacting with agents.

### MCP (Model Context Protocol)

Protocol integration, the Hermes plugin runtime, and transport layer. This is where new LLM providers plug in and where remote vs. stdio transport decisions play out. The Hermes runtime shipped in 0.7.0 and enables community-contributed provider modules.

### Skills and Agent Capabilities

Agent orchestration features - inbox/messaging, task assignment, agent profiles, and the APIs that agents use to collaborate. This area grows as agents move from single-task to multi-agent coordination patterns.

---

## Technical Architecture

```
User / Operator
    |
    v
ax CLI (commands, onboarding, key management)
    |
    v
Gateway Daemon (local trust boundary)
    |
    +--> Hermes Plugin Runtime (LLM providers)
    +--> MCP Protocol (tools, resources)
    +--> Proxy Dispatcher (agent API methods)
    |
    v
ax Platform (workspaces, agents, messages)
```

The Gateway daemon runs locally and acts as a trust boundary between the operator, their agents, and the platform. Agents interact through the proxy dispatcher - they never hold credentials directly (fully enforced in 0.9.0).

---

## Security Posture

ax-gateway is designed for defense and regulated environments:

- **IL2** - Current production deployment
- **IL5** - Targeted for Q4 2026 via Defense Unicorns (Zarf/UDS for air-gapped Kubernetes)
- **IL6** - Planned for 2027

The Phase 4 process attestation model is specifically designed to meet the credential isolation requirements for higher impact levels.

---

## Contributing

The project welcomes contributions. Infrastructure is in place:

- CLA enforcement on all PRs
- Community standards (Code of Conduct, Contributing Guide, Security Policy)
- Good-first-issues tagged and maintained
- PR template with checklist (tests, lint, format, build)

**Quality bar for contributions:**

- All PRs must pass `pytest`, `ruff check`, and `ruff format`
- New code requires unit tests with 80%+ coverage on changed files
- One approving review minimum
- Conventional commit messages for changelog generation

See the repository's CONTRIBUTING.md for full details.
