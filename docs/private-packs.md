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

Same format as public jobs (`jobs/<id>/job.json` and `prompt.md.tmpl`; only the prompt is copied to the runtime). A pack is often written by someone else than the person who installs it, so permissions are checked twice:

1. **At install, before anything is written**, on the final text (after `{{ct.*}}` tokens are filled in): every `permissions.allow` entry, and the `allowed-tools` of every skill the pack ships, must name something on the list below. The install stops otherwise.
2. **At run time, on every call**, by the guard hook: a rule such as `Bash(sort:*)` is a prefix, so the guard checks the real command. Only the allowed commands and the ones you trust may run. Options that write a file, run code or send data are refused (`sort -o`, `git log --output`, `git diff --no-index`, `git blame --contents`, `jq --rawfile`, `jq env`, `gh api -X`/`-f`/`-F`/`--method`, `gh api graphql`, any URL or other host for `gh`...). Every file argument, option value included, must resolve inside the vault (symlinks followed). Output redirection goes to `/dev/null` only. Variables, substitutions, subshells, `cd`, brace expansion and here-strings are refused. Jobs may not create `.git`, `.claude`, `.obsidian`, `.vscode`, `CLAUDE.md` or `.mcp.json` anywhere in the vault, since a later git command or a later job would act on them.

   Known limit: a `jq` filter may not contain `{a,b}` (the guard cannot tell it from shell brace expansion); build objects with `{a: .x} + {b: .y}`.

| A pack may grant | Condition |
|---|---|
| `Read`, `Grep`, `Glob`, `Read(<path>)`, `TodoWrite`, `Skill` | the guard confines reads to the vault and blocks secrets; a pack's skills may not grant tools (`allowed-tools` is refused) |
| `Bash(<command> ...)` for `date`, `ls`, `wc`, `sort`, `uniq`, `cut`, `tr`, `column`, `jq` | arguments checked at run time |
| `Bash(git <sub> ...)` | `log`, `show`, `diff`, `status`, `rev-parse`, `shortlog`, `blame`, `ls-files`; no option before the subcommand |
| `Bash(gh <sub> ...)` | `pr list/view/checks/diff`, `issue list/view`, `release list/view`, `run list/view`, `repo view`, `api` (read-only: enforced at run time) |
| `Bash(<tool> ...)` for another tool | only if **you** list it under `trusted_commands` |
| `mcp__<server>__<tool>` | only the exact tools **you** list under `trusted_mcp_tools` (or under `permissions` in your answers); a trusted tool that sends data can carry vault text out, so trust read tools only |
| `WebFetch(domain:<host>)` | only hosts **you** list under `trusted_domains` (a fetch can carry vault text in its URL) |

Always refused: `Edit` and `Write` (the installer grants the vault write itself), bare `Bash`, `WebFetch` or `WebSearch`, whole MCP servers and wildcards, shell operators, quotes, paths as commands, and `VAR=value` prefixes unless the variable is under `trusted_env` (never `PATH`, `PAGER`, `GIT_*`, `LD_*`...).

The trust lists belong to the person installing, in the answers file:

```json
{
  "trusted_commands": ["twg", "slackcli"],
  "trusted_env": ["TWG_AGENT_DEFAULTS"],
  "trusted_mcp_tools": ["mcp__claude_ai_acme-assistant__sonarqube_get_issues"],
  "trusted_domains": ["status.acme.example"]
}
```

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
