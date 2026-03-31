# Credential Security

ax-cli includes built-in credential fingerprinting and honeypot detection to
protect agent workspaces from unauthorized access.

## Fingerprinting

Every CLI request sends non-sensitive fingerprint headers to the aX platform:

| Header | Value | Purpose |
|--------|-------|---------|
| `X-AX-FP` | SHA-256 hash (24 chars) | Composite hash of working directory + hostname + OS user. Changes if the credential is used from a different location. |
| `X-AX-FP-Token` | SHA-256 hash (16 chars) | Hash of the PAT itself. Detects token modification. |
| `X-AX-FP-OS` | e.g. `Darwin/25.3.0` | Operating system and version. Public info. |
| `X-AX-FP-Arch` | e.g. `arm64` | CPU architecture. Public info. |

**No sensitive data is sent.** Hostnames, usernames, and directory paths are
hashed into a single composite fingerprint. The server never sees the raw
values — it only compares hashes across requests.

### What the server can detect

- **Copied config** — `.ax/config.toml` moved to a different directory.
  The `X-AX-FP` hash changes because the directory component changed.

- **Stolen token** — PAT used from a different machine. The `X-AX-FP`
  hash changes because hostname and user are different.

- **Token replay** — Same token used from two locations simultaneously.
  The server sees two different `X-AX-FP` values for the same `credential_id`.

- **Environment shift** — Same credential suddenly appears on a different
  OS or architecture. May indicate credential exfiltration.

### How detection works

1. On first use, the server stores the fingerprint as the baseline for that credential.
2. On subsequent requests, the server compares the fingerprint.
3. On mismatch, the server logs a security event with the old and new fingerprints.
4. Depending on policy: alert the workspace owner, flag the credential, or auto-revoke.

## Honeypot Keys

ax-cli recognizes credential patterns from other platforms. If a token matching
one of these patterns is used, the CLI immediately alerts the aX platform with
the full fingerprint of whoever triggered it.

### Supported patterns

| Prefix | Provider | Example |
|--------|----------|---------|
| `AKIA` | AWS IAM | `AKIAIOSFODNN7EXAMPLE` |
| `ASIA` | AWS STS | `ASIAXXX...` |
| `ghp_` | GitHub PAT | `ghp_xxxxxxxxxxxx` |
| `gho_` | GitHub OAuth | `gho_xxxxxxxxxxxx` |
| `ghs_` | GitHub App | `ghs_xxxxxxxxxxxx` |
| `sk-` | OpenAI | `sk-proj-xxxx` |
| `sk-ant-` | Anthropic | `sk-ant-xxxx` |
| `xoxb-` | Slack Bot | `xoxb-xxxx` |
| `xoxp-` | Slack User | `xoxp-xxxx` |
| `SG.` | SendGrid | `SG.xxxx` |

### How to use honeypots

1. Generate fake keys that match the patterns above.
2. Plant them in places an attacker would find:
   - `.env` files in repos
   - CI/CD configs
   - Docker images
   - Shared drives or wikis
3. If anyone uses them with ax-cli, the platform gets an instant alert with:
   - Which pattern was triggered (e.g. "aws-iam")
   - Full SHA-256 hash of the token used
   - Fingerprint of the caller (hashed dir/host/user, OS, arch)

### Example: planting a honeypot

```bash
# Create a fake .env that looks like it has real credentials
cat > .env.example << 'EOF'
# AWS credentials (DO NOT COMMIT)
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

# aX Platform
AX_TOKEN=axp_u_FAKE.honeypot_key_do_not_use
EOF
```

If a scanner, bot, or attacker extracts `AKIAIOSFODNN7EXAMPLE` and tries to
use it with ax-cli, the platform knows immediately.

## Privacy

- No raw hostnames, usernames, or paths are transmitted
- All identifying information is hashed (SHA-256, truncated)
- OS version and architecture are the only plaintext values — these are
  non-sensitive and publicly observable
- Honeypot alerts fire only when fake credentials are used — legitimate
  users with real `axp_u_` tokens are never flagged by the honeypot system
- The server IP address is available from the request itself (standard HTTP)
