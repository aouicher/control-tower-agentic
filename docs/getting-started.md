# Getting started

## Prerequisites

| Need | Why | Check |
|---|---|---|
| macOS or Linux | Windows is not supported yet (WSL2 should work, untested) | `uname -s` |
| Python 3.9+ | The installer and the job runner use only the standard library (`zoneinfo` converts job times) | `python3 --version` |
| git | Cloning this repository | `git --version` |
| [Claude Code](https://claude.com/claude-code) | Skills, guided installer and scheduled jobs | `claude --version` |
| [Obsidian](https://obsidian.md) | Reading and editing the vault | open the app |
| Obsidian **Tasks** plugin | Task queries in the cockpit (Community plugins) | Settings, Community plugins |

Optional: accounts for the tools you want to connect (see [adapters](adapters.md)). You can start with none and add them later.

## Install

### Option A: guided (recommended)

```bash
git clone https://github.com/<owner>/control-tower-agentic.git
cd control-tower-agentic
claude
```

In Claude Code type `/install-control-tower`. It will:

1. check your machine,
2. ask which profile(s) fit you, your name, handle, timezone and vault folder,
3. ask which tool you use for each capability (tracker, code, calendar...),
4. run a **dry run** and show what will be created,
5. install only after you say yes,
6. run the health check and list what is left for you to do.

It never asks for passwords, tokens or API keys, and never changes your Claude Code settings or loads a schedule without an explicit yes.

### Option B: terminal wizard

```bash
python3 installer/install.py --interactive
```

### Option C: answers file (repeatable, good for teams)

Copy one of [examples/answers](../examples/answers), edit it, then:

```bash
python3 installer/install.py --answers my-answers.json --dry-run
python3 installer/install.py --answers my-answers.json
```

Fields: `owner_name`, `owner_handle`, `timezone`, `vault_path`, `ct_home`, `packs`, `tools` (capability to tool or `none`), `scheduler` (`auto`, `launchd`, `cron`, `none`), optional `jobs` overrides (`{"morning-prs": {"time": "07:15", "days": "mon,wed"}}`), `claude_bin`, `permissions`.

### What the installer does and does not do

- Creates the vault, skills, adapter notes, job files and a manifest at `<vault>/.control-tower/manifest.json`.
- Never overwrites an existing file: running it again is safe and only adds what is missing.
- Seeds `.obsidian/` only if it does not exist yet.
- Writes the commands you need (connect tools, schedule) to `<vault>/library/setup-next-steps.md`. It does not run them.
- Loads a schedule only with `--apply-schedule`.

## After installing

1. Open the vault folder in Obsidian and enable the Tasks plugin.
2. Open `cockpit.md`.
3. Follow `library/setup-next-steps.md` to connect your tools, one at a time. Each adapter note says how to verify the connection.
4. In the vault folder start Claude Code and try `/today`.
5. Run a job by hand once before scheduling it:

```bash
python3 ~/.control-tower/bin/run_job.py --job morning-prs --ct-home ~/.control-tower
```

6. When you are happy, apply the schedule:

```bash
python3 installer/install.py --answers my-answers.json --apply-schedule
```

## Health check

```bash
python3 installer/doctor.py --vault ~/control-tower-vault --ct-home ~/.control-tower
```

Prints `ok`, `warn` or `FAIL` per check and exits 1 on failure.

## Uninstall

```bash
python3 installer/uninstall.py --ct-home ~/.control-tower --vault ~/control-tower-vault --remove-vault-files        # dry run
python3 installer/uninstall.py --ct-home ~/.control-tower --vault ~/control-tower-vault --remove-vault-files --yes  # apply
```

Removes the runtime and schedule, and only the vault files you have not edited. Your notes are never removed.
