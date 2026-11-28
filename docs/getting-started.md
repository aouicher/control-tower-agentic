# Getting started

## What you need

| Need | Why |
|---|---|
| A Mac (or Linux) | Windows is not supported yet (WSL2 should work, untested) |
| The [Claude desktop app](https://claude.com/download), signed in | Claude installs the kit, then runs your reports |
| [Obsidian](https://obsidian.md) 1.9 or newer | Reading and editing the vault; the dashboards use the core **Bases** plugin, added in 1.9 |

Accounts for the tools you want to connect are optional (see [adapters](adapters.md)): you can start with none and add them later. If Python or git is missing on a Mac, the system offers to install them in a dialog during the install: click Install.

## Install and first steps

The install, opening the vault in Obsidian and the first session in it are in the README: [Use Control Tower](../README.md#part-1-use-control-tower). In the vault session, `library/setup-next-steps.md` lists what is left for each tool, and "check my setup" says what needs your attention.

## For developers: answers files

Repeatable installs for teams, private packs and scripts. You need Python 3.9+, git and the Claude Code CLI.

```bash
git clone https://github.com/aouicher/control-tower-agentic.git
cd control-tower-agentic
python3 installer/install.py --answers my-answers.json --dry-run
python3 installer/install.py --answers my-answers.json
python3 installer/doctor.py --vault ~/control-tower-vault --ct-home ~/.control-tower
```

Start from one of [examples/answers](../examples/answers). Fields: `owner_name`, `owner_handle`, `timezone` (all three taken from the computer when left out), `language` (of notes and reports, default `English`), `vault_path`, `ct_home`, `packs`, `tools` (capability to tool or `none`), `scheduler` (`auto`, `launchd`, `cron`, `none`), optional `jobs` overrides (`{"morning-prs": {"time": "07:15", "days": "mon,wed"}}`), `claude_bin`, `job_permissions`. `install.py --match-tools "Jira, Amplitude" --packs marketing` shows how the guided install reads tool names (adapter ids and their `aliases`). Typing `/install-control-tower <answers file>` in the kit folder runs the same install with Claude's summary and checks.

What the installer does and does not do:

- Creates the vault, skills, adapter notes, job files and a manifest at `<vault>/.control-tower/manifest.json`, and saves the answers in `<vault>/.control-tower/answers.json`.
- Never overwrites an existing file: running it again is safe and only adds what is missing.
- Seeds `.obsidian/` only if it does not exist yet.
- Writes the commands you need (connect tools, schedule) to `<vault>/library/setup-next-steps.md`. It does not run them.
- Loads a schedule only with `--apply-schedule`. Run a job by hand with `python3 ~/.control-tower/bin/run_job.py --job <id> --ct-home ~/.control-tower`.
- Already have a vault? `--runtime-only` installs only the job machinery on it; keep your own jobs in a private pack: see [private packs](private-packs.md).

The doctor prints `ok`, `warn` or `FAIL` per check and exits 1 on failure. Updates: [updating](updating.md).

Uninstall from a terminal. Each command is a dry run until `--yes`; `--schedule-only`, `--remove-connections` and `--remove-kit` are the other levels. It removes the runtime and the schedule, and only the vault files you have not edited; your notes are never removed:

```bash
python3 installer/uninstall.py --ct-home ~/.control-tower --vault ~/control-tower-vault --remove-vault-files        # dry run
python3 installer/uninstall.py --ct-home ~/.control-tower --vault ~/control-tower-vault --remove-vault-files --yes  # apply
```
