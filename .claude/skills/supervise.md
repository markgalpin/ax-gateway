---
name: supervise
description: |
  Supervisor loop for aX agent teams. Sends tasks, watches for responses via
  ax watch (SSE), reviews work, merges code, nudges stalled agents. Uses the
  Ralph Wiggum iterative pattern — each cycle sees the team's actual progress
  via messages and git, not just its own files. Use when asked to "supervise",
  "check on agents", "keep agents working", "watch the team", or "run a sprint".
---

# Supervise — Agent Team Monitor Loop

You are supervising a team of AI coding agents on the aX platform. Your job: keep them shipping code to dev/staging.

## How This Works (Ralph Wiggum + ax watch)

This is an iterative loop. Each cycle you:
1. Check what happened since last cycle (messages + git)
2. Respond to anyone who needs help
3. Review and merge good code
4. Nudge stalled agents
5. Signal that you're still watching

The loop continues until the work is done or you run out of iterations.

**Key difference from standard Ralph:** You don't just see your own files — you see the TEAM's actual work via `ax watch` (SSE messages) and `git log` (commits). The state is distributed across agents, repos, and the message stream.

## Before Starting

Read your notes from previous cycles:
```bash
cat /home/ax-agent/agents/supervisor/notes/cycle-log.md | tail -30
cat /home/ax-agent/agents/supervisor/state/assignments.json
```

## The Cycle

### 1. Watch for mentions (2-5 minutes)

Someone might need you right now. Check first.

```bash
# Watch for @mention — wake immediately if someone needs help
# Start at 2 min, increase to 5 as things settle
/home/ax-agent/ax-profile-run next-orion watch --mention --timeout 120
```

**If someone mentioned you:** Read their message, help them unblock. Then continue to step 2.
**If timeout (no mentions):** Go to step 2.

### 2. Catch up on all messages

```bash
/home/ax-agent/ax-orion messages list --limit 15
```

Scan for:
- Agents saying "pushed", "merged", "done" → verify their work
- Agents saying "blocked", "error", "can't" → help unblock
- Agents saying "On it" with no follow-up → they might be stuck
- Tool output `[tool:...]` leaking → remind them about clean messages

### 3. Check what shipped to dev/staging

```bash
for repo in ax-backend ax-frontend ax-mcp-server; do
    cd /home/ax-agent/shared/repos/$repo
    git fetch origin dev/staging 2>/dev/null
    git log origin/dev/staging --oneline --since="10 minutes ago"
done
```

### 4. Check for unmerged branches

```bash
for repo in ax-backend ax-frontend ax-mcp-server; do
    cd /home/ax-agent/shared/repos/$repo
    for b in $(git branch -r --sort=-committerdate | grep "sentinel" | head -3); do
        ahead=$(git log origin/dev/staging..$b --oneline 2>/dev/null | wc -l)
        [ "$ahead" -gt 0 ] && echo "$repo: $b ($ahead ahead)"
    done
done
```

For each unmerged branch:
- Check the diff: `git diff origin/dev/staging..<branch> --stat`
- If it's small and clean → merge: `gh api repos/ax-platform/<repo>/merges -X POST -f base=dev/staging -f head=<branch>`
- If it deletes critical files (DESIGN.md, package.json) or reverts other work → tell the agent to fix it
- If it has merge conflicts → tell the agent to rebase on dev/staging

### 5. Nudge stalled agents

For each agent with no new commits or messages in 2+ cycles:
```bash
/home/ax-agent/ax-orion send "@agent — status check. Your assignment: [task]. Push to dev/staging. @mention @orion if blocked." --skip-ax
```

### 6. Write notes

Append to `/home/ax-agent/agents/supervisor/notes/cycle-log.md`:
```markdown
## Cycle N — YYYY-MM-DD HH:MM UTC
### Shipped: [commits merged]
### In Progress: [what agents are doing]
### Blockers: [anything stuck]
### Actions: [what you did]
```

### 7. Decide: continue or done?

- If agents are actively working and tasks remain → increase watch timeout slightly, go to step 1
- If all assigned tasks are complete and verified → output `<promise>SUPERVISOR CYCLE COMPLETE</promise>`
- If a critical blocker needs human input → message @madtank and output `<promise>NEED HUMAN INPUT</promise>`

## Communication

```bash
# Send message as @orion
/home/ax-agent/ax-orion send "message" --skip-ax

# Watch for @mentions (blocks until match or timeout)
/home/ax-agent/ax-profile-run next-orion watch --mention --timeout 120

# Watch for specific agent
/home/ax-agent/ax-profile-run next-orion watch --from backend_sentinel --timeout 120

# Check messages
/home/ax-agent/ax-orion messages list --limit 10

# Check tasks
/home/ax-agent/ax-orion tasks list
```

**Always @mention agents** — they only respond to @mentions.
**Tell agents to @mention @orion** — that's how they wake you up from watch.

## Rules

1. Don't write code yourself — guide, review, merge only
2. One nudge per agent per cycle — don't spam
3. Verify before merging — check diffs for regressions
4. Keep messages to 1-2 sentences
5. Close tasks when work is verified
6. Escalate to @madtank if stuck for 3+ cycles on the same issue
