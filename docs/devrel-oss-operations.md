# Developer Relations & OSS Operations Playbook

> Last updated: 07-May-2026

## 1. Open Source Strategy

### What We Are

AX is an open-core, MCP-native multi-agent collaboration platform. The OSS  
layer (CLI, MCP server, dashboard, plugins) drives adoption and trust. The  
commercial layer (paxai.app) provides the hosted workspace, routing, and  
management plane that platform teams pay for.

### Who We Serve

Platform engineering teams at companies wiring up multi-agent systems. These
are **consumers and integrators**, not open-source contributors. They evaluate
our repos for:

- **Trust signals** — license, security policy, release cadence, CI status
- **Integration quality** — clear install paths, working examples, stable APIs
- **Operational maturity** — are issues triaged? are PRs reviewed? is anyone home?

They rarely open PRs. They file issues when something blocks them, and they
move on if nobody responds.

### What OSS Does for Us


| Goal                  | How OSS serves it                                                  |
| --------------------- | ------------------------------------------------------------------ |
| Adoption funnel       | `pip install axctl` or clone Agent Studio → try the platform → buy |
| Trust & credibility   | Public code, public security policy, visible release process       |
| Ecosystem integration | MCP registry listing, Claude/ChatGPT/Gemini plugin ecosystem       |
| Hiring signal         | Public repos show how we build                                     |


### What OSS Does NOT Do for Us (Yet)

- Drive community contributions (we have ~3 core contributors)
- Generate revenue directly (no paid tiers on OSS components)
- Serve as primary documentation (docs live at paxai.app and the blog)

## 2. Org Inventory


| Repo               | Role                      | Language   | Status             | Release Vehicle                      |
| ------------------ | ------------------------- | ---------- | ------------------ | ------------------------------------ |
| ax-gateway         | CLI + Gateway runtime     | Python     | **active**         | PyPI (`axctl`) via release-please    |
| ax-agent-studio    | Dashboard / monitoring UI | Python     | **to be archived** | TBD — needs release strategy         |
| ax-platform-mcp    | MCP server definition     | JSON/docs  | **to be archived** | GitHub releases (v1.0.0 exists)      |
| ax-openclaw-plugin | OpenClaw agent plugin     | TypeScript | **to be archived** | None — needs releases                |
| ax-moltworker      | Cloudflare Workers agent  | TypeScript | **to be archived** | None — needs releases                |
| ax-mcp-monitor     | MCP monitoring bot        | Python     | **to be archived** | None                                 |
| ax-mcpjam          | Shell toolkit for agents  | Shell      | **to be archived** | None                                 |
| ax-docs            | Developer documentation   | Docs       | **to be archived** | Decision needed: populate or archive |


## 3. Roles & Responsibilities

### Current Team


| Person       | Handle     | Role                | Focus                                                     |
| ------------ | ---------- | ------------------- | --------------------------------------------------------- |
| madtank      | `@madtank` | Lead maintainer     | Code review, release signoff, architecture                |
| Sean Roberts | `@sarob`   | Operations / DevOps | Repo hygiene, CI/CD, community standards, release process |
| TBD          | —          | +1 contributor      | TBD                                                       |


### RACI for OSS Operations


| Activity                   | Responsible           | Accountable       | Consulted |
| -------------------------- | --------------------- | ----------------- | --------- |
| PR review (code)           | madtank               | madtank           | sarob     |
| PR review (CI/ops/docs)    | sarob                 | sarob             | madtank   |
| Release cut (ax-gateway)   | release-please (auto) | madtank (signoff) | sarob     |
| Release cut (other repos)  | sarob                 | madtank           | —         |
| Issue triage               | sarob                 | sarob             | madtank   |
| Security reports           | sarob                 | madtank           | —         |
| Dependabot PR merge        | sarob                 | sarob             | —         |
| Blog / content             | madtank               | madtank           | sarob     |
| Slack monitoring           | TBD                   | sarob             | —         |
| Org settings / permissions | sarob                 | sarob             | madtank   |


## 4. Operational Cadence

### Maintainers Weekly (30 min) 

- Triage new issues across all repos (close, label, or respond)
- Review and merge/close Dependabot PRs
- Check for stale PRs (>14 days without activity → ping or close)
- Glance at Discord for unanswered questions

### OSS-ops-agent Biweekly (during team sync)

- Review open PR backlog — anything blocked?
- Check CI health — are workflows green on main?
- Review GitHub Insights for traffic/clone trends (leading indicator)

### OSS-ops-agent Monthly

- Audit: do all repos have LICENSE, SECURITY.md, passing CI?
- Review GitHub community profile scores — are we regressing?
- Check Dependabot coverage — any new repos missing it?
- Review blog cadence — has anything been published?
- Cut releases for repos with unreleased changes on main

### OSS-ops-agent Quarterly

- Review this playbook — is it still accurate?
- Assess whether contributor model should change (consumer → contributor)
- Review analytics: PyPI downloads, GitHub stars/forks/clones, Discord members
- Evaluate ax-docs — archive decision if still empty

## 5. Repository Standards

- `LICENSE` file (MIT, unless inherited license prevents it)
- `README.md` with: what it is, install instructions, usage example, license badge
- Branch protection on `main` (require PR review, require status checks, block force-push)
- CI workflow that runs on PR (even if it's just a lint or syntax check)
- Repo description set in GitHub settings
- Topics set for discoverability (`mcp`, `ai-agents`, `multi-agent`, etc.)

### Set on monorepo

- `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1
- `SECURITY.md` — vulnerability disclosure via `security@paxai.app`
- `profile/README.md` — org-level README with component map

- `CONTRIBUTING.md`
- `CODEOWNERS`
- `.github/dependabot.yml`
- `.github/PULL_REQUEST_TEMPLATE.md`
- Automated releases (release-please or equivalent)
- `CHANGELOG.md` (auto-generated via release tooling)

- CLA workflow
- Detailed contributor guides with dev environment setup
- SUPPORT.md (point to Discussions in README)

## 6. Release Process

- release-please on `main` creates release PRs automatically
- madtank signoff required before merge
- Merge triggers PyPI publish via `publish.yml`
- Package: `axctl` on PyPI, command: `ax`

## 7. Public Channels

### Active


| Channel              | URL                    | Purpose                       | Owner                        |
| -------------------- | ---------------------- | ----------------------------- | ---------------------------- |
| GitHub (ax-platform) | github.com/ax-platform | Code, issues, releases        | sarob (ops) / madtank (code) |
| Blog                 | ax-platform.com/blog   | Thought leadership, tutorials | madtank                      |
| PyPI                 | pypi.org/project/axctl | CLI distribution              | automated                    |
| MCP Registry         | —                      | Discovery                     | —                            |


### Exists but Status Unclear


| Channel  | URL              | Status           | Action Needed                           |
| -------- | ---------------- | ---------------- | --------------------------------------- |
| Slack    |                  |                  | Decide: revive or remove link from site |
| LinkedIn | linked from site | Unknown activity | Audit                                   |
| TikTok   | linked from site | Unknown activity | Audit                                   |
|          |                  |                  |                                         |


### Not Yet Created


| Channel            | Recommendation                              | Priority |
| ------------------ | ------------------------------------------- | -------- |
| Org `.github` repo | Create for shared health files + org README | **P0**   |
| GitHub org profile | Fill in description, website, email         | **P0**   |
| Public roadmap     | GitHub Projects board or roadmap.md         | P3       |


## 8. Community Interaction Model

### Issue Response SLA


| Severity                      | Target Response               | Target Resolution                  |
| ----------------------------- | ----------------------------- | ---------------------------------- |
| Security report (SECURITY.md) | 48 hours                      | 7 days (patch), 30 days (full fix) |
| Bug blocking integration      | 3 business days               | Best effort                        |
| Feature request               | 5 business days (acknowledge) | Triage to backlog                  |
| General question              | 5 business days               | Point to docs/Discord              |


"Response" means acknowledgment + label, not resolution. The goal is "someone
is home" — integrators evaluating the platform check issue response times.

### PR Policy

- External PRs: welcome but not expected. Review within 5 business days.
- Dependabot PRs: merge weekly (sarob).
- Bot PRs (release-please, Claude): review per normal process.
- Stale threshold: 14 days without activity → ping author. 30 days → close with "feel free to reopen" message.

### What We Don't Do (Yet)

- Office hours or live community calls
- Contributor onboarding programs
- Swag / recognition programs
- Conference sponsorships
- Ambassador programs

These become relevant if/when the model shifts from consumer to contributor.
Revisit quarterly.

## 9. Metrics


| Metric                                | Source                    | Why It Matters                         |
| ------------------------------------- | ------------------------- | -------------------------------------- |
| PyPI downloads (axctl)                | pypistats.org             | Adoption of CLI                        |
| GitHub clones (ax-gateway)            | GitHub Insights → Traffic | Interest / evaluation                  |
| GitHub clones (ax-agent-studio)       | GitHub Insights → Traffic | Interest in dashboard                  |
| GitHub stars (all repos)              | GitHub API                | Vanity, but correlates with visibility |
| Open issue count                      | GitHub                    | Triage health                          |
| Mean time to first response on issues | Manual spot-check         | "Is anyone home?" signal               |
| Slack member count                    | Slack                     | Community size                         |
| Blog post cadence                     | ax-platform.com/blog      | Content velocity                       |


### Current Baselines (2026-05-06)

**Convert idle users and stars from archived repos to ax-gateway**


| Repo               | Stars | Forks | Open Issues | Open PRs               |
| ------------------ | ----- | ----- | ----------- | ---------------------- |
| ax-agent-studio    | 17    | 11    | 0           | 5 (4 stale Dependabot) |
| ax-platform-mcp    | 6     | 3     | 0           | 0                      |
| ax-openclaw-plugin | 4     | 3     | 0           | 1 (stale)              |
| ax-moltworker      | 4     | 2     | 0           | 2 (stale)              |
| ax-gateway         | 4     | 6     | 12          | 10                     |
| ax-mcp-monitor     | 1     | 0     | 0           | 0                      |
| ax-docs            | 0     | 0     | 0           | 0                      |
| ax-mcpjam          | 0     | 0     | 0           | 0                      |


## 10. Account & Access Hygiene

### Org Members — Action Items


| Handle         | Status                              | Action                                          |
| -------------- | ----------------------------------- | ----------------------------------------------- |
| `@madtank`     | Public member                       | None                                            |
| `@anvil`       | In CODEOWNERS but not public member | Make public, confirm access level               |
| `@mschecht88`  | In CLA allowlist                    | Confirm if active contributor, add to org if so |
| `@heathdorn00` | CEO, in CLA allowlist               | Keep in org, no code expectations               |
| `@iHelperPro`  | CLA agent                           |                                                 |
| `@iHelper30`   | CLA agent                           | dup?                                            |


