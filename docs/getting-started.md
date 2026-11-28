# Getting started

## What you need

| Need | Why |
|---|---|
| A Mac (or Linux) | Windows is not supported yet (WSL2 should work, untested) |
| The [Claude desktop app](https://claude.com/download), signed in | Claude installs the kit, then runs your reports |
| [Obsidian](https://obsidian.md) 1.9 or newer | Reading and editing the vault; the dashboards use the core **Bases** plugin, added in 1.9 |

Accounts for the tools you want to connect are optional (see [adapters](adapters.md)): you can start with none and add them later. If Python or git is missing on a Mac, the system offers to install them in a dialog during the install: click Install.

**Where to put the vault (macOS).** Keep the default, a folder in your home folder such as `~/control-tower-vault`. A vault inside iCloud Drive, Documents or Desktop may be blocked for scheduled reports by the macOS privacy rules, and they then fail without a window to ask you.

## Install

In the Claude desktop app, open the **Code** tab, choose any folder (your home folder is fine) and paste this sentence:

> Install the Control Tower kit from https://github.com/aouicher/control-tower-agentic into ~/control-tower-kit and follow its install skill.

Claude asks before downloading the kit, then asks four questions:

1. which describes your work (one or more profiles);
2. which tools you use at work, named in your own words ("Jira and Amplitude"); a tool you name twice for one job ("Jira, Linear") gets one more question, and a tool the kit does not know is connected later;
3. where the vault goes;
4. whether reports run automatically on this computer.

Your name, handle and timezone come from the computer. Claude then shows what it will install: the vault, each report with its time and what it may read. It installs after your yes, which is also your consent to what the reports read. It checks the result and offers to open the vault in Obsidian, and, if you like, reports that run on claude.ai.

It never asks for passwords, tokens or API keys, and never changes your Claude Code settings or loads a schedule without an explicit yes. Existing files are never overwritten.

## After installing

Everything else happens in your vault. In the Claude app, start a new Code session and choose the **control-tower-vault** folder (it stays in your recent folders), then say **hello control tower**. From there you can say:

- "connect Amplitude" (or any tool): Claude adds the connection, you sign in, and the reports that use it can read it;
- "every Monday, sum up my tickets": Claude writes a report, tries it and schedules it;
- "move the triage to 9:00", "stop the debt review", "add the product profile": change the setup;
- "fix my job" when a notification says a report was blocked;
- "update the kit", "uninstall".

In Obsidian, open `cockpit.md`, and turn on the Tasks plugin (Settings, Community plugins, Browse, "Tasks", Install, then Enable). Try `/today` in the vault session. `library/setup-next-steps.md` in the vault lists what is left for each tool.

## For developers: answers files

Repeatable installs for teams, private packs and scripts. You need Python 3.9+, git and the Claude Code CLI.

```bash
git clone https://github.com/aouicher/control-tower-agentic.git
cd control-tower-agentic
python3 installer/install.py --answers my-answers.json --dry-run
python3 installer/install.py --answers my-answers.json
python3 installer/doctor.py --vault ~/control-tower-vault --ct-home ~/.control-tower
```

Start from one of [examples/answers](../examples/answers). Fields: `owner_name`, `owner_handle`, `timezone` (all three taken from the computer when left out), `vault_path`, `ct_home`, `packs`, `tools` (capability to tool or `none`), `scheduler` (`auto`, `launchd`, `cron`, `none`), optional `jobs` overrides (`{"morning-prs": {"time": "07:15", "days": "mon,wed"}}`), `claude_bin`, `job_permissions`. `install.py --match-tools "Jira, Amplitude" --packs marketing` shows how the guided install reads tool names (adapter ids and their `aliases`). Typing `/install-control-tower <answers file>` in the kit folder runs the same install with Claude's summary and checks.

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
