# Security and privacy

Scheduled jobs run unattended, so they are locked down by design.

## What a job can do

- Read files inside the vault (with `Read`, `Grep` and `Glob`; no command is allowed by default, and the date comes in the prompt).
- Edit files inside the vault, except protected areas.
- Call the read tools of the adapters you connected, listed by exact name, on a copy of each server's entry as it was when you connected it (a job starts no other MCP server, and none whose entry changed since).

## Enforced, and by what

| Control | Enforced by | Covers | Does not cover |
|---|---|---|---|
| **Allow-list per job.** Base: `Read`, `Grep`, `Glob`, `Edit(<vault>/**)`; plus what the pack job, the chosen adapters and the user's grants add. Everything else is refused. | Claude Code: `--permission-mode dontAsk --setting-sources project --settings <job>/settings.json` (`scheduler/run_job.py`) | Every tool, MCP included | What an allowed tool does with its arguments |
| **No user or local settings in jobs.** User-level rules, hooks and MCP servers, and `.claude/settings.local.json` (where an interactive "don't ask again" goes), do not load. The vault's `.claude/settings.json` does: while it sets rules, hooks or anything else that could widen a job, no job runs. | `--setting-sources project`; `scheduler/run_job.py` | Widening through settings files or interactive approvals | |
| **Deny rules.** `Agent`, `Skill` (a skill can bring its own tools; jobs read skill files with `Read`), reads of secret file names, edits to the vault's protected areas. | Job `settings.json` (`install.job_settings`) | Defence in depth for the file tools | Commands, which the guard and the sandbox cover |
| **Never-list when anything is granted.** Shells, interpreters and wrappers; file-moving and network commands; generic file readers (`date`, `ls`, `cat`, `head`, `grep`, `tar`, `open`...); git other than read subcommands; variables that change which program runs; MCP tools whose name says they act; whole-server or wildcard MCP rules; `WebSearch`; `WebFetch` without one site; `Edit`/`Write` rules; `Skill`. | `plan.permission_problem`, for pack rules, adapters and grants alike | Packs, adapters, users and the owner alike | A read tool with a misleading name |
| **Guard on file tools.** Reads inside the vault only, except the job's own saved tool output; no secret names. Writes inside the vault only, Markdown notes only (`.md`: nothing an MCP server or a tool could run), never in `.claude`, `.control-tower`, `.obsidian`, `.git`, templates, dashboards, `CLAUDE.md` or `.mcp.json`, nested ones included. Globs cannot escape. Fails closed. | `scheduler/guard.py` PreToolUse hook | `Read`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `Grep`, `Glob` | MCP tools and `WebFetch`, limited by the allow-list; a file an allowed command writes (the sandbox limits where) |
| **Guard on outward or destructive commands.** About 20 patterns: `rm -r`, `sudo`, git writes, `curl \| sh`, GitHub writes, cloud, cluster, Terraform, Docker and database writes, credential paths, environment dumps. | `guard.BASH_RULES` (regular expressions, no parsing) | Obvious mistakes and simple injections | Obfuscated commands: a backstop, not the boundary |
| **Sandbox.** Every job with a command rule in its settings. Commands write only in the vault minus its top-level protected folders and files (the guard's list), Claude Code's temporary folder and the per-user log or cache folders a pack declares; never read `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.kube`, `~/.docker`, `~/.claude`; reach only the hosts declared by the job and its adapters. `failIfUnavailable: true`, `allowUnsandboxedCommands: false`. For jobs with a `gh` rule only, `enableWeakerNetworkIsolation` lets commands use the macOS certificate service `gh` needs. The doctor fails for a job that has a command rule and no sandbox. | Claude Code's sandbox (`install.sandbox_settings`) | Any command syntax: options that write a file, redirections, substitutions | File tools and MCP servers; reads of other files outside the vault by an allowed command; a nested `CLAUDE.md` or `.git` (the guard refuses `--output <path>`); a command allowed in the vault's `.claude/settings.json` (flagged by the doctor) |
| **Vault settings.** The vault's `.claude/settings.json` loads into every job: while it sets anything that could widen a job (rules, hooks, env, MCP servers...), the runner refuses to start any job and notifies; the doctor fails. | `scheduler/run_job.py`, `guard.risky_settings` | A settings file pulled from a synced vault or written by a cloud routine | |
| **Run limits.** One run at a time, a time limit (30 minutes by default), the whole process group stopped on timeout. | `scheduler/run_job.py` | Runaway jobs | |
| **Consent.** Every rule beyond the base is shown in plain words and needs a yes: at install, and after a refusal (`/job-permissions`). | Install summary, `installer/configure.py` (refuses never-list rules whatever the skill says) | Silent widening | A user who says yes to an unusual request |

A prefix rule does not cover a redirection: with Claude Code 2.1.332, `Bash(echo f5:*)` refuses `echo f5 > f5.txt` under `dontAsk` (F5 in [runtime facts](design/runtime-facts.md)). The sandbox is still what limits an allowed command, whatever its form. On Linux the sandbox needs `bubblewrap` and `socat`; without them, jobs that run commands refuse to run (the doctor says so), and jobs that use only MCP tools still run.

What a job may use beyond the vault (a command, an MCP tool, a web site) is listed in plain words at install time and granted only when the user says yes; some rules can never be granted, whoever asks. See [permissions](permissions.md).

## Symlinks

Search tools may follow symlinks that sit inside the vault. Do not link folders from outside into the vault; `doctor.py` warns about symlinks that leave it.

## The vault settings caveat

Jobs load the vault's project settings (`--setting-sources project`). Anything set in `<vault>/.claude/settings.json` could widen what jobs can do, so the runner refuses to start any job while it sets more than the harmless keys, and `doctor.py` fails; keep your own rules in your user settings. The guard stops jobs from editing it.

## Secrets

The installer and the guided skill never ask for or store passwords, tokens or keys. Connect tools with OAuth or environment variables you set yourself. Do not put secrets in notes: the vault is read by Claude.

## Privacy

Everything in the vault that Claude reads is sent to Claude. Do not use this setup with data your organisation does not allow to be processed by an AI provider. Check your company policy before connecting internal tools.

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
