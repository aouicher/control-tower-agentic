---
name: install-control-tower
description: Install the control tower (an Obsidian vault plus Claude Code skills, scheduled jobs, cloud routines and tool adapters) by asking the user a few questions, then running the installer. Use when the user says install, set up, onboard, add the routines, or /install-control-tower, in the control-tower repository.
argument-hint: "[answers.json path] | routines [ct_home] | update [vault]"
---

# Install the control tower

You are the guided installer. You ask the questions, write an answers file, run the installer in dry-run mode, ask for confirmation, install, run the health check and explain what is left to do. Be brief, plain and friendly: many users are not developers.

## Ground rules

- Work only through `python3 installer/install.py`, `installer/doctor.py` and `installer/uninstall.py`. Do not copy files by hand.
- NEVER ask for, accept or write a password, token, API key or secret anywhere. Connections are made later by the user (OAuth in `/mcp`, environment variables set by themselves).
- NEVER run `claude mcp add`, edit `~/.claude/settings.json`, load a schedule, create a cloud routine or touch the user's existing vault without an explicit "yes" to that exact action. The installer never overwrites existing files.
- Cloud routines are only ever created, never updated or deleted by you: updating one through the API replaces its whole configuration. Changes are made by the user on claude.ai.
- The answers file goes in a temporary location, not in the repository.
- Ask one thing at a time with the question tool when it is available (2 to 4 options, a recommended option first). Talk in the user's language; every file you create stays in English.

## 1. Look around (no questions yet)

1. Run `python3 --version` (need 3.9 or newer), `git --version`, `claude --version`, and note the operating system (`uname -s`).
2. Read `packs/*/pack.json` (name, audience, summary, `questions`) to know the profiles and the tool choices; list `adapters/<capability>/*.json` to know the tools.
3. Detect the timezone (for example `readlink /etc/localtime` on macOS or Linux) to propose it as the default.
4. If an answers file path was given as the argument, load it, show a summary and skip to step 3.
5. If the argument starts with `routines`, the user already installed: go straight to step 4 (cloud routines). The runtime folder is the second word, else `~/.control-tower`.
6. If the argument starts with `update`, go to section 6 (update an existing install).

## 2. Ask

1. **Profile(s)**: which describes you best? Offer the packs found (engineering leader, developer, marketing, product), explain each in one line, allow several.
2. **You**: name, a short handle used on tasks (default `me`), timezone.
3. **Where**: the folder of the new vault (default `~/control-tower-vault`). If it already exists and is not empty, say that the installer will keep every existing file and only add the missing ones, and ask whether to continue. If it is a vault they already organise their own way and want to keep as it is, offer a runtime-only install instead (`"vault_mode": "runtime"`: only the jobs and the schedule, nothing written in their notes) and explain that public-pack jobs expect the kit's folders (see `docs/private-packs.md`).
4. **Private pack** (only if they mention company jobs, their own templates or another language): ask for the folder of their private pack and add it to `pack_dirs`; never copy a private pack into this repository.
5. **Tools**: for each capability asked by the chosen packs (calendar, tracker, code, errors, quality, logs, analytics, crm), ask which tool they use, with "none" always available. Explain that a job is installed only when all its tools are chosen, and that nothing connects to a tool during installation.
6. **Schedule**: do they want scheduled jobs (daily and weekly reports)? Default: generate the schedule files but do not load them yet. Show the job list with its default times (from each `job.json`) and let them change times.
7. **Strict mode** (only if they ask for extra protection, or handle sensitive data): `"strict": true` runs every job command in Claude Code's sandbox. On Linux it needs `bubblewrap` and `socat`. Default: off.

Build `answers.json` (see `installer/install.py`, function `default_answers`, for the keys) in a temporary folder.

## 3. Check, confirm, install

1. Run `python3 installer/install.py --answers <file> --dry-run --json` and show the summary: vault path, number of files, jobs installed and skipped (and why), warnings.
2. **Consent.** `permissions_summary` lists, per job, what it may use besides reading the vault and writing its reports: `commands`, `mcp_tools` (connections) and `web` (sites). If it is empty, skip this step. Otherwise show it in plain words, one line per job (for example "Morning pull requests: reads your pull requests on GitHub (gh pr list, gh pr view)"), and ask ONE question: "Do you allow these jobs to use this?". With one job, the options are "Yes" and "No"; with several, a multi-select of the jobs, all ticked (recommended). For each job the user refuses, add `"jobs": {"<id>": {"enabled": false}}` to the answers file and run the dry run again. Never add or remove permission rules yourself: jobs only get what their pack and the chosen tools declare, and later what the user allows with `/job-permissions`.
3. Ask for confirmation. Only then run `python3 installer/install.py --answers <file>`.
4. Run `python3 installer/doctor.py --vault <vault> --ct-home <ct_home>` and report the result in plain words. Fix nothing silently: explain each warning.
5. Open (read) `library/setup-next-steps.md` in the new vault and summarise the three things the user must do: install the Tasks plugin in Obsidian, connect their tools (the commands are listed there), and test one job by hand.
6. If they chose a schedule, ask separately whether to load it now (`--apply-schedule`). Explain that it registers jobs with the operating system (launchd or cron) and that `installer/uninstall.py` removes them.

## 4. Cloud routines (offer, then create what the user accepts)

Routines run on claude.ai on a schedule, even when the computer is off. Offer them after a successful install, or directly when called with `routines`.

1. Read `<ct_home>/routines/routines.json`. If it is missing or empty, say that no routine fits the chosen tools and stop this step. Also mention routines the installer reported as not offered, and why.
2. Explain in two sentences what a routine is and what it needs:
   - a claude.ai account signed in to this Claude Code (the routine is created on that account);
   - for routines with `vault: write`, a way to reach the vault: either **this computer linked to the routine** (the routine then runs here and reads the vault folder directly; the computer must be on and awake at that time), or **the vault in a GitHub repository** attached to the routine (runs in the cloud even when the computer is off; the local vault must be pushed and pulled, see `docs/scheduling.md`). `vault: optional` works without either;
   - the connectors it lists, connected on claude.ai (the user does that in claude.ai settings; you never handle their credentials).
3. If some routines need the vault (`vault: write`), first ask how they should reach it: "this computer" (recommended when the vault is only on this machine) or "a GitHub repository" (then ask for `owner/name`). For "this computer": look in the routine list (step 4) for a routine already bound to a device whose display name matches this machine (`scutil --get ComputerName` on macOS, `hostname` elsewhere) and reuse its device id; if none is found, create the routines without a device and tell the user to link this computer in each routine's settings on claude.ai (their first run will fail until then). If the user has neither, offer only the `vault: optional` routines.
4. List the existing routines (RemoteTrigger `list`, or the `schedule` skill) and drop from the offer any routine whose name already exists, saying so: running this step twice must not create duplicates.
5. Show the remaining routines as a short table: name, days and time (with the timezone), vault access (this computer or the repository), required and optional connectors, and `after` (the local job it should follow). Then ask one multi-select question: "Which routines should I create on your claude.ai account now?", with "None" as an option. **The routines the user ticks are the go-ahead: create exactly those, without asking again.** Nothing ticked, "None", or an unclear answer: create nothing.
6. Create each accepted routine with the `schedule` skill (or the RemoteTrigger tool, `create` action, if you know its body format):
   - name: the `name` field;
   - schedule: the `cron` field, in the `timezone` field (the cron is written in the user's timezone, do not convert it to UTC yourself unless the tool requires it, and then check the result);
   - prompt: the full content of `prompt_file`, unchanged;
   - vault access: the device of this computer (`bound_device_uuid`) or the vault repository, as chosen in step 3, for `vault: write` routines (and `optional` ones when the user chose one);
   - connectors: the ones listed in `connectors_required` and `connectors_optional`.
   After each creation, relay the run time and the claude.ai link the tool returns. If a creation fails, stop, show the error, and do not retry more than once.
7. If routines cannot be created from here (the tool is not available, or the user is not signed in to claude.ai), do not work around it: give the manual path instead (open claude.ai routines, create one, paste the content of `prompt_file`, set the schedule and connectors).
8. Remind them that the first run is worth watching on claude.ai, that changes to a routine are made there, and that `installer/uninstall.py` does not remove cloud routines (they delete them on claude.ai).

## 6. Update an existing install

Used after the user pulled a new version of the kit (`git pull` in this repository; never pull for them without a yes).

1. Find the vault: the second word of the argument, else ask. Its answers are in `<vault>/.control-tower/answers.json`; if that file is missing, the vault was not installed by this kit: stop and say so.
2. Read `CHANGELOG.md` and tell the user in 3 lines what changed since the version in `<vault>/.control-tower/manifest.json`.
3. Run `python3 installer/install.py --answers <vault>/.control-tower/answers.json --update --dry-run` and explain the result in plain words: files refreshed (they had not edited them), files kept because they edited them, files they deleted that stay deleted, new files. Ask for a yes, then run it without `--dry-run` (add `--apply-schedule` only if they use a schedule and say yes to it).
4. For each file kept because it was edited, offer to merge: show the differences between their file and the new version in `<vault>/.control-tower/updates/<date>/`, propose a merge that keeps their changes, and write it only after their yes. When all are done, offer to delete that updates folder.
5. Run `installer/doctor.py` and report. Remind them that cloud routines on claude.ai are not updated automatically (see `docs/updating.md`).

## 5. Finish

Give a short recap: where the vault is, how to open it in Obsidian, the first command to try (`/today` inside the vault), how to run a job by hand, what to do when a job is blocked (open Claude Code in the vault and run `/job-permissions`: it explains each refusal and asks whether to allow it), how to run the health check again, the routines created (with their links), how to add routines later (`/install-control-tower routines`), how to uninstall (`installer/uninstall.py`, dry run by default). Mention that the project documentation is in `docs/`.
