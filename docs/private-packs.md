# Private packs and runtime-only installs

Two features for people and teams who want the kit's machinery without its default layout:

- a **private pack** keeps your own jobs, rules, templates and language in a folder **outside** this repository (for example a company pack that must not be public);
- a **runtime-only install** puts the job runner, the guard, the jobs and the schedule on a vault you **already have**, without touching your notes.

They work together: a private pack for your jobs and conventions, installed runtime-only on your existing vault.

## Private packs

A private pack is a folder with the same shape as a public pack (see [pack-spec](design/pack-spec.md)): `pack.json`, an optional `vocabulary.json`, `vault/`, `jobs/`, `routines/`. The developer who installs the kit with an answers file names it under `pack_dirs`:

```json
{
  "packs": ["engineering", "acme"],
  "pack_dirs": ["~/acme-control-tower-pack"]
}
```

The pack id comes from its `pack.json` (`"id": "acme"`) and must not reuse a public pack id. Keep the folder in its own private repository.

### Replacing or dropping core files

Only private packs may change the core. In `pack.json`:

```json
{
  "id": "acme",
  "replaces": ["CLAUDE.md", "_system/templates/*", "_system/dashboards/projects.base"],
  "excludes": ["_system/dashboards/people.base", ".claude/skills/time-review"]
}
```

- `replaces`: core files your pack ships its own version of. The pack must contain them under `vault/` (`vault/CLAUDE.md.tmpl`, `vault/_system/templates/daily.md`...). The core copy is not installed.
- `excludes`: core files or folders you do not want at all.

Paths are vault paths as installed (`CLAUDE.md`, not `CLAUDE.md.tmpl`). Patterns work per folder level: `*` never crosses a `/` (`*.base` is a file at the vault root), `**` spans folders (`**/*.base`), and a folder covers everything under it (`_system/dashboards`). Every `replaces` entry must match a file the pack ships, or the install stops. This is how you get a vault in another language: replace `CLAUDE.md`, the templates and the pages, and set your words in `vocabulary.json`.

A pack may never ship installer state, git, Obsidian or Claude settings: `.control-tower/`, `.git/`, `.obsidian/`, `.claude/settings*.json`, `.mcp.json`, `CLAUDE.local.md`. Pack, job and routine ids are lowercase letters, digits and `-`.

`doctor.py` knows what you excluded and does not report it missing. `--update` keeps honouring `replaces` and `excludes`: the core never comes back over your files.

### Jobs in a private pack

Same format as public jobs (`jobs/<id>/job.json` and `prompt.md.tmpl`; only the prompt is copied to the runtime).

<a id="job-permissions"></a>
#### Job permissions

A job may use only what its rules allow: jobs run with `--permission-mode dontAsk`, so anything else is refused. A pack declares what each job needs in `job.json`:

```json
{
  "permissions": {"allow": ["Bash(twg jira workitem query *)", "Bash(slackcli conversations unread *)", "mcp__acme__get_issues"]},
  "network": ["acme.atlassian.net", "slack.com"],
  "sandbox_allow_write": ["~/Library/Logs/slackcli"]
}
```

- `permissions.allow`: the commands, MCP tools and web sites the job uses. The person installing sees them in plain words and says yes or no per job (the guided installer asks one question; the report has `permissions_summary`, also in `install.py --json`). A job that is refused is installed disabled.
- `network` (optional): the hosts the job's commands reach. A job with a command runs it in Claude Code's sandbox, which lets it reach these hosts and nothing else.
- `sandbox_allow_write` (optional): folders a sandboxed command must write to (a CLI's own log folder). Only per-user log and cache folders: `~/Library/Logs/`, `~/Library/Caches/`, `~/.cache/`, `~/.local/state/`.

A command also gets the addresses and folders of `adapters/commands.json` (known tools such as `gh`, `twg`, `slackcli`) and of the `commands` answers, `{"twg": {"network": ["acme.atlassian.net"], "allow_write": ["~/.cache/twg"]}}`, `/job-permissions` records `network` when a developer grants an unknown command (see [adapters](adapters.md#command-line-tools-in-jobs)). An address recorded for a command applies to every job that is allowed that command. The same checks apply: exact public host names, a tool's own folder under a per-user log or cache folder, and never a command on the never-list.

Later, a user grants a job more access by answering `/job-permissions` in the vault: the skill records the answer as `job_permissions` in `<vault>/.control-tower/answers.json` and re-runs the installer (see [permissions](permissions.md)). Nobody edits a rule by hand.

The installer checks every rule on the final text (after `{{ct.*}}` tokens are filled in), before anything is written, whoever asked for it (the pack, the chosen tool adapters, the user). Well-formed rules are accepted: `Read`, `Grep`, `Glob`, `TodoWrite`, `Bash(<command> ...)` for a plain command name (company CLIs included), one exact `mcp__<server>__<tool>`, `WebFetch(domain:<host>)`. These are refused for everyone, always:

| Never | Why |
|---|---|
| `Edit`, `Write`, `MultiEdit`, `NotebookEdit` rules | the installer grants the vault write itself, scoped to the vault |
| `Skill` | a skill can bring its own tools; a job reads the skill file with `Read` and follows it |
| bare `Bash`, `Bash(*)`, bare `WebFetch`, `WebSearch` | everything at once |
| whole MCP servers or wildcards (`mcp__x`, `mcp__*`, `mcp__x__*`) | one tool at a time |
| MCP tools whose name says they act: send, post, create, update, delete, remove, write, edit, merge, close, publish, upload, comment, reply, react, transition, assign, invite, share, trigger, deploy, add, set, manage, move, archive, respond, approve, submit, call, invoke, insert, upsert, put, patch, save, cancel, drop, navigate, click, fill, draft, destructive, sql (`createIssue`, `chat.postMessage` and `send_message` alike) | jobs only read |
| shell operators, quotes, substitutions in a `Bash` rule; a path as the command | one plain command per rule |
| shells, interpreters and file or network tools: `sh`, `bash`, `zsh`, `python`, `node`, `perl`, `ruby`, `osascript`, `curl`, `wget`, `nc`, `ssh`, `scp`, `rsync`, `cp`, `mv`, `rm`, `dd`, `tee`, `chmod`, `chown`, `sudo`, `env`, `xargs`, `eval`, `timeout`, `find`, `awk`, `sed`... | they run any code or move files by themselves |
| generic file readers: `date`, `ls`, `cat`, `head`, `tail`, `less`, `more`, `grep`, `rg`, `strings`, `od`, `xxd`, `base64`, `tar`, `zip`, `unzip`, `open`, and their variants (`gdate`, `ggrep`, `zcat`, `egrep`, `bat`...) | jobs read files with `Read`, `Grep` and `Glob`, which stay in the vault; dates are in the prompt's Run context |
| `git` other than `log`, `show`, `diff`, `status`, `rev-parse`, `shortlog`, `blame`, `ls-files`, `describe` | read history only |
| `VAR=value` prefixes for `PATH`, `PAGER`, `EDITOR`, `HOME`, `SHELL`, `ENV`, `BASH_ENV`, `GIT_*`, `GH_*`, `LD_*`, `DYLD_*`, `*PROXY*`... | they change which program runs |

Answers files from older versions may still hold `trusted_commands`, `trusted_env`, `trusted_mcp_tools` or `trusted_domains`: they are ignored.

At run time, the guard hook checks every call whatever the rules say: file-tool reads stay in the vault and never touch secrets, file-tool writes stay in the vault and never touch its settings, templates, git or Claude files (nested ones included), and outward or destructive commands are refused (`git push`, `gh pr create`, `gh api -X`, cloud and cluster writes, `rm -r`, `sudo`, reading credential files...). Every shell command also runs in Claude Code's sandbox, whatever its syntax: its writes stay in the vault and it reaches only the declared hosts (see [permissions](permissions.md#the-sandbox)).

What a pack may not contain: symlinks (a `vault/` or `jobs/` folder that is itself a link included), a vocabulary file outside the pack, anything the guard protects except skills, rules, templates and dashboards (so no `.claude/settings*.json`, hooks, agents or commands, no `.git`, `.github`, `.vscode`, `.obsidian`, `.control-tower`, `.mcp.json`), and the same names nested deeper. Only private packs may ship `CLAUDE.md`. These checks ignore case, as macOS and Windows do.

## Runtime-only installs

```bash
python3 installer/install.py --answers my-answers.json --runtime-only --dry-run
python3 installer/install.py --answers my-answers.json --runtime-only
```

(or `"vault_mode": "runtime"` in the answers). The vault must exist already. The mode is remembered: later runs and `--update` stay runtime-only even if your answers file does not say so. To switch to a full install, set `"vault_mode": "full"` explicitly.

| | Full install | Runtime-only |
|---|---|---|
| Core vault, pack vault files, adapter notes, Obsidian settings | installed | **not installed** |
| In your vault | the kit's files | only `.control-tower/` (manifest and answers, used by `--update`, the doctor and the uninstaller) |
| Runtime (`~/.control-tower/`: runner, guard, jobs, schedule) | installed | installed |
| Setup notes | `library/setup-next-steps.md` | `~/.control-tower/setup-next-steps.md` |
| `doctor.py` | checks the vault and the runtime | checks the runtime only |
| `uninstall.py` | removes the runtime and the kit files you did not edit | removes the runtime only |

Jobs run inside your vault and load its project settings (`<vault>/.claude/settings.json`). If that file allows commands or defines hooks for your own sessions, every unattended job inherits them: the installer warns about it in runtime-only mode, and `doctor.py` flags the file. Keep it empty and put your own rules in your user settings.

Public-pack jobs expect the kit's folders (`journal/reports/`, `work/`...). In runtime-only mode the installer warns when you install them: use them only if your vault has the same layout, or write your own jobs in a private pack.

Adapter notes are not written in runtime-only mode, so a job cannot read `.claude/adapters/<capability>.md`: put the tool instructions in the job prompt itself.

## Moving an existing setup onto the kit

1. Write a private pack with your jobs (prompts, exact tool permissions, schedules).
2. Install it runtime-only on your vault, with `scheduler: none`. Run each job by hand (`run_job.py --job <id>`) and compare with your current reports.
3. Switch the schedule: unload your old scheduled jobs, then re-run with `--apply-schedule`.
4. Later, if you want the kit's vault features too, move your templates and rules into the pack (`replaces`), then run a full install: your notes are never overwritten.
