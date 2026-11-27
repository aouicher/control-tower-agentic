# Getting started

## Prerequisites

| Need | Why | Check |
|---|---|---|
| macOS or Linux | Windows is not supported yet (WSL2 should work, untested) | `uname -s` |
| Python 3.9+ | The installer and the job runner use only the standard library (`zoneinfo` converts job times) | `python3 --version` |
| git | Cloning this repository | `git --version` |
| [Claude Code](https://claude.com/claude-code) | Skills, guided installer and scheduled jobs | `claude --version` |
| [Obsidian](https://obsidian.md) 1.9 or newer | Reading and editing the vault; the dashboards use the core **Bases** plugin, added in 1.9 | Settings, About |
| Obsidian **Tasks** plugin | Task queries in the cockpit. Install it from `obsidian://show-plugin?id=obsidian-tasks-plugin` (paste it in your browser with Obsidian open) | Settings, Community plugins |

Optional: accounts for the tools you want to connect (see [adapters](adapters.md)). You can start with none and add them later.

> **New to the terminal?**
> 1. Open the Terminal app (macOS: Applications > Utilities > Terminal).
> 2. Install Claude Code by following its official guide: https://claude.com/claude-code
> 3. Type `claude` once and sign in with your Claude account when asked.
> 4. To work in your vault later: `cd ~/control-tower-vault && claude`.
> 5. Prefer an app? The Claude desktop app can also open the vault folder.

**Where to put the vault (macOS).** Prefer a folder in your home directory, such as `~/control-tower-vault`. A vault inside iCloud Drive, Documents or Desktop may be blocked for scheduled jobs by the macOS privacy rules, and the jobs then fail without a window to ask you.

## Install

### Option A: guided (recommended)

```bash
git clone https://github.com/aouicher/control-tower-agentic.git
cd control-tower-agentic
claude
```

In Claude Code type `/install-control-tower`. It will:

1. check your machine,
2. ask which profile(s) fit you, your name, handle, timezone and vault folder,
3. ask which tool you use for each capability (tracker, code, calendar...),
4. run a **dry run** and show what will be created,
5. install only after you say yes,
6. run the health check and list what is left for you to do,
7. offer the cloud routines that fit your tools and create the ones you tick on your claude.ai account.

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
python3 ~/.control-tower/bin/run_job.py --job <job id from library/setup-next-steps.md> --ct-home ~/.control-tower
```

6. Optional: create cloud routines with `/install-control-tower routines` (see [scheduling](scheduling.md#cloud-routines)).
7. When you are happy, apply the schedule:

```bash
python3 installer/install.py --answers <vault>/.control-tower/answers.json --apply-schedule
```

The installer saved your answers in `<vault>/.control-tower/answers.json`, whichever install option you used.

## Health check

```bash
python3 installer/doctor.py --vault ~/control-tower-vault --ct-home ~/.control-tower
```

Prints `ok`, `warn` or `FAIL` per check and exits 1 on failure.

## Already have a vault?

Install only the job machinery on it with `--runtime-only`, and keep your own jobs and conventions in a private pack: see [private packs](private-packs.md).

## Update

When the kit gets a new version: `git pull` in the kit folder, then `python3 installer/install.py --answers <vault>/.control-tower/answers.json --update`. Files you edited are never overwritten. Details in [updating](updating.md).

## Uninstall

Open Claude Code in your vault and say "uninstall" to `/control-tower`. It asks how much to remove: stop the automatic reports only, or remove the kit and keep all your notes; then, separately, whether to remove the tool connections it added for you, and whether to delete the kit's own folder. Your notes are never removed.

For developers, the same from a terminal (each command is a dry run until `--yes`; `--schedule-only`, `--remove-connections` and `--remove-kit` are the other levels):

```bash
python3 installer/uninstall.py --ct-home ~/.control-tower --vault ~/control-tower-vault --remove-vault-files        # dry run
python3 installer/uninstall.py --ct-home ~/.control-tower --vault ~/control-tower-vault --remove-vault-files --yes  # apply
```

Removes the runtime and schedule, and only the vault files you have not edited. Your notes are never removed.
