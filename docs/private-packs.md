# Private packs and runtime-only installs

Two features for people and teams who want the kit's machinery without its default layout:

- a **private pack** keeps your own jobs, rules, templates and language in a folder **outside** this repository (for example a company pack that must not be public);
- a **runtime-only install** puts the job runner, the guard, the jobs and the schedule on a vault you **already have**, without touching your notes.

They work together: a private pack for your jobs and conventions, installed runtime-only on your existing vault.

## Private packs

A private pack is a folder with the same shape as a public pack (see [pack-spec](design/pack-spec.md)): `pack.json`, an optional `vocabulary.json`, `vault/`, `jobs/`, `routines/`. List it in your answers file:

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

Same format as public jobs (`jobs/<id>/job.json` and `prompt.md.tmpl`). A pack is often written by someone else than the person who installs it, so the installer checks every `permissions.allow` entry **before writing anything**, on the final text (after `{{ct.*}}` tokens are filled in), and stops on the first one that would widen what an unattended job can do. The check is an allow-list: anything not listed below is refused.

| Allowed | Notes |
|---|---|
| `Read`, `Grep`, `Glob`, `Read(<path>)` | the guard still confines reads to the vault and blocks secrets |
| `Bash(<command> ...)` for `date`, `ls`, `wc`, `sort`, `uniq`, `jq`, `cut`, `tr`, `column` | text tools for data the job already has |
| `Bash(git log ...)` and the other read-only git subcommands | `log`, `show`, `diff`, `status`, `rev-parse`, `shortlog`, `blame`, `ls-files` |
| `Bash(gh pr list ...)` and the other read-only gh subcommands | `pr list/view/checks/diff`, `issue list/view`, `release list/view`, `run list/view`, `repo view`, `api` (GET only) |
| `Bash(<tool> ...)` for a tool **you** trust | list it in the answers under `trusted_commands` |
| `mcp__<server>__<tool>`, one read tool | the server must be in `trusted_mcp_servers`; tools named like actions (`send_`, `create_`, `update_`...) are refused |
| `WebFetch(domain:<host>)` | the host must be in `trusted_domains` (a fetch can carry vault text in its URL) |

Always refused: `Edit`/`Write` (the installer grants the vault write itself), bare `Bash`, `WebFetch` or `WebSearch`, whole MCP servers and wildcards, shell operators, quotes and substitutions, paths as commands, options that write or send (`-o`, `-c`, `--output`, `--exec`, `--method`, `-f`/`-F`...), and `VAR=value` prefixes unless the variable is in `trusted_env` (never `PATH`, `PAGER`, `GIT_*`, `LD_*`...).

The trust lists belong to the person installing, in the answers file:

```json
{
  "trusted_commands": ["twg", "slackcli"],
  "trusted_env": ["TWG_AGENT_DEFAULTS"],
  "trusted_mcp_servers": ["claude_ai_acme-assistant"],
  "trusted_domains": ["status.acme.example"]
}
```

MCP tools you list yourself under `permissions` in the answers count as trusted. The guard and the per-job settings then apply exactly as for public jobs: read and write only inside the vault, protected areas, no outward action.

A pack may not contain symlinks: they would copy files from anywhere on disk into your vault.

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

Public-pack jobs expect the kit's folders (`journal/reports/`, `work/`...). In runtime-only mode the installer warns when you install them: use them only if your vault has the same layout, or write your own jobs in a private pack.

Adapter notes are not written in runtime-only mode, so a job cannot read `.claude/adapters/<capability>.md`: put the tool instructions in the job prompt itself.

## Moving an existing setup onto the kit

1. Write a private pack with your jobs (prompts, exact tool permissions, schedules).
2. Install it runtime-only on your vault, with `scheduler: none`. Run each job by hand (`run_job.py --job <id>`) and compare with your current reports.
3. Switch the schedule: unload your old scheduled jobs, then re-run with `--apply-schedule`.
4. Later, if you want the kit's vault features too, move your templates and rules into the pack (`replaces`), then run a full install: your notes are never overwritten.
