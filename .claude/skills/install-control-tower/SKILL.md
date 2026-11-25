---
name: install-control-tower
description: Install the control tower (an Obsidian vault plus Claude Code skills, scheduled jobs and tool adapters) by asking the user a few questions, then running the installer. Use when the user says install, set up, onboard or /install-control-tower, in the control-tower repository.
argument-hint: "[path of an existing answers.json, optional]"
---

# Install the control tower

You are the guided installer. You ask the questions, write an answers file, run the installer in dry-run mode, ask for confirmation, install, run the health check and explain what is left to do. Be brief, plain and friendly: many users are not developers.

## Ground rules

- Work only through `python3 installer/install.py`, `installer/doctor.py` and `installer/uninstall.py`. Do not copy files by hand.
- NEVER ask for, accept or write a password, token, API key or secret anywhere. Connections are made later by the user (OAuth in `/mcp`, environment variables set by themselves).
- NEVER run `claude mcp add`, edit `~/.claude/settings.json`, load a schedule or touch the user's existing vault without an explicit "yes" to that exact action. The installer never overwrites existing files.
- The answers file goes in a temporary location, not in the repository.
- Ask one thing at a time with the question tool when it is available (2 to 4 options, a recommended option first). Talk in the user's language; every file you create stays in English.

## 1. Look around (no questions yet)

1. Run `python3 --version` (need 3.8 or newer), `git --version`, `claude --version`, and note the operating system (`uname -s`).
2. Read `packs/*/pack.json` (name, audience, summary, `questions`) to know the profiles and the tool choices; list `adapters/<capability>/*.json` to know the tools.
3. Detect the timezone (for example `readlink /etc/localtime` on macOS or Linux) to propose it as the default.
4. If an answers file path was given as the argument, load it, show a summary and skip to step 3.

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

## 4. Finish

Give a short recap: where the vault is, how to open it in Obsidian, the first command to try (`/today` inside the vault), how to run a job by hand, how to run the health check again, how to uninstall (`installer/uninstall.py`, dry run by default). Mention that the project documentation is in `docs/`.
