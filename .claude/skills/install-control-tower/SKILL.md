---
name: install-control-tower
description: Install the control tower (an Obsidian vault plus Claude Code skills, scheduled jobs, cloud routines and tool adapters) by asking the user a few questions, then running the installer. Use when the user says install, set up, onboard, add the routines, or /install-control-tower, in the control-tower repository.
argument-hint: "[answers.json path] | routines [ct_home]"
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

## 2. Ask

1. **Profile(s)**: which describes you best? Offer the packs found (engineering leader, developer, marketing, product), explain each in one line, allow several.
2. **You**: name, a short handle used on tasks (default `me`), timezone.
3. **Where**: the folder of the new vault (default `~/control-tower-vault`). If it already exists and is not empty, say that the installer will keep every existing file and only add the missing ones, and ask whether to continue.
4. **Tools**: for each capability asked by the chosen packs (calendar, tracker, code, errors, quality, logs, analytics, crm), ask which tool they use, with "none" always available. Explain that a job is installed only when all its tools are chosen, and that nothing connects to a tool during installation.
5. **Schedule**: do they want scheduled jobs (daily and weekly reports)? Default: generate the schedule files but do not load them yet. Show the job list with its default times (from each `job.json`) and let them change times.

Build `answers.json` (see `installer/install.py`, function `default_answers`, for the keys) in a temporary folder.

## 3. Check, confirm, install

1. Run `python3 installer/install.py --answers <file> --dry-run` and show the summary: vault path, number of files, jobs installed and skipped (and why), warnings.
2. Ask for confirmation. Only then run `python3 installer/install.py --answers <file>`.
3. Run `python3 installer/doctor.py --vault <vault> --ct-home <ct_home>` and report the result in plain words. Fix nothing silently: explain each warning.
4. Open (read) `library/setup-next-steps.md` in the new vault and summarise the three things the user must do: install the Tasks plugin in Obsidian, connect their tools (the commands are listed there), and test one job by hand.
5. If they chose a schedule, ask separately whether to load it now (`--apply-schedule`). Explain that it registers jobs with the operating system (launchd or cron) and that `installer/uninstall.py` removes them.

## 4. Cloud routines (offer, then create what the user accepts)

Routines run on claude.ai on a schedule, even when the computer is off. Offer them after a successful install, or directly when called with `routines`.

1. Read `<ct_home>/routines/routines.json`. If it is missing or empty, say that no routine fits the chosen tools and stop this step. Also mention routines the installer reported as not offered, and why.
2. Explain in two sentences what a routine is and what it needs:
   - a claude.ai account signed in to this Claude Code (the routine is created on that account);
   - for routines with `vault: write`, the vault in a GitHub repository that the routine can access (a cloud routine cannot see a folder on this computer); `vault: optional` works without it;
   - the connectors it lists, connected on claude.ai (the user does that in claude.ai settings; you never handle their credentials).
3. If some routines need the vault (`vault: write`), first ask whether the vault is in a GitHub repository and which one (`owner/name`). If it is not, say those routines cannot run yet, offer only the `vault: optional` ones, and point to `docs/scheduling.md`.
4. List the existing routines (RemoteTrigger `list`, or the `schedule` skill) and drop from the offer any routine whose name already exists, saying so: running this step twice must not create duplicates.
5. Show the remaining routines as a short table: name, days and time (with the timezone), repository, required and optional connectors, and `after` (the local job it should follow). Then ask one multi-select question: "Which routines should I create on your claude.ai account now?", with "None" as an option. **The routines the user ticks are the go-ahead: create exactly those, without asking again.** Nothing ticked, "None", or an unclear answer: create nothing.
6. Create each accepted routine with the `schedule` skill (or the RemoteTrigger tool, `create` action, if you know its body format):
   - name: the `name` field;
   - schedule: the `cron` field, in the `timezone` field (the cron is written in the user's timezone, do not convert it to UTC yourself unless the tool requires it, and then check the result);
   - prompt: the full content of `prompt_file`, unchanged;
   - repository: the vault repository when the routine has `vault: write` (or `optional` and the user gave one);
   - connectors: the ones listed in `connectors_required` and `connectors_optional`.
   After each creation, relay the run time and the claude.ai link the tool returns. If a creation fails, stop, show the error, and do not retry more than once.
7. If routines cannot be created from here (the tool is not available, or the user is not signed in to claude.ai), do not work around it: give the manual path instead (open claude.ai routines, create one, paste the content of `prompt_file`, set the schedule and connectors).
8. Remind them that the first run is worth watching on claude.ai, that changes to a routine are made there, and that `installer/uninstall.py` does not remove cloud routines (they delete them on claude.ai).

## 5. Finish

Give a short recap: where the vault is, how to open it in Obsidian, the first command to try (`/today` inside the vault), how to run a job by hand, how to run the health check again, the routines created (with their links), how to add routines later (`/install-control-tower routines`), how to uninstall (`installer/uninstall.py`, dry run by default). Mention that the project documentation is in `docs/`.
