# Security and privacy

Scheduled jobs run unattended, so they are locked down by design.

## What a job can do

- Read files inside the vault.
- Edit files inside the vault, except protected areas.
- Call the read tools of the adapters you connected, listed by exact name.

## What a job cannot do

| Blocked | Enforced by |
|---|---|
| Spawning sub-agents | `deny: Agent` |
| Writing outside the vault | permission rules and the guard hook |
| Editing `.claude/`, `.control-tower/`, `.obsidian/`, `_system/templates`, `_system/dashboards`, `CLAUDE.md`, `CLAUDE.local.md`, `.mcp.json` | permission rules and the guard hook (case-insensitive) |
| Reading outside the vault (`~/.ssh`, `~/.aws`, `~/.claude`, `/etc`...) | guard hook: the search root and the static prefix of any glob must stay inside the vault; `{ } [ ] \` syntax and `..` are refused; fails closed |
| Reading `.env`, keys, credentials | guard hook |
| Git writes, `sudo`, recursive delete, `curl | sh`, `chmod`, environment dumps | guard hook (Bash) |
| Writes on GitHub, AWS, kubectl, Terraform, Docker, databases | guard hook plus allow-lists |

The guard (`scheduler/guard.py`) is a defence in depth, not a sandbox: it blocks known dangerous patterns, and the allow-list (`dontAsk`) is the primary control. For stronger isolation, turn on strict mode (`"strict": true`: Claude Code's sandbox around every shell command, see [permissions](permissions.md#strict-mode-optional)), or run jobs under a dedicated OS user or in a container.

What a job may use beyond the vault (a command, an MCP tool, a web site) is listed in plain words at install time and granted only when the user says yes; some rules can never be granted, whoever asks. See [permissions](permissions.md).

## Symlinks

Search tools may follow symlinks that sit inside the vault. Do not link folders from outside into the vault; `doctor.py` warns about symlinks that leave it.

## The vault settings caveat

Jobs load the vault's project settings (`--setting-sources project`). Anything you allow in `<vault>/.claude/settings.json` widens what jobs can do, so keep it empty or review it; `doctor.py` warns when such a file exists. The guard stops jobs from editing it.

## Secrets

The installer and the guided skill never ask for or store passwords, tokens or keys. Connect tools with OAuth or environment variables you set yourself. Do not put secrets in notes: the vault is read by Claude.

## Privacy

Everything in the vault that Claude reads is sent to Claude. Do not use this setup with data your organisation does not allow to be processed by an AI provider. Check your company policy before connecting internal tools.

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
