# Changelog

## Unreleased

- Jobs get their dates from the runner: a `## Run context` block at the top of each prompt (now, today, ISO weeks, previous working day, in the installed timezone). Job prompts no longer run `date`, `weekly-digest` finds notes with Glob instead of `ls`, and the skills jobs follow say to use the Run context first. See docs/scheduling.md.
- `tests/e2e/smoke_real_claude.py --facts` checks the Claude Code behaviours the kit relies on, with the real CLI; results in docs/design/runtime-facts.md. Found with Claude Code 2.1.332: jobs do not see MCP servers added at user scope (docs/adapters.md now says so), and a claude.ai connector's tool is refused in a job even with its exact allow rule.
- Job permissions, secure by default and granted by answering questions: the installer report lists in plain words what each job may use (`permissions_summary`), the guided installer asks once and disables the jobs you refuse, and the new vault skill `/job-permissions` explains each refusal of a job's latest run (`<ct_home>/logs/<job>.denials.json`) and allows what you say yes to (`job_permissions` in the answers, written by `installer/permissions.py`, never by hand). See docs/permissions.md.
- Simpler guard and policy: the guard no longer parses shell commands (which commands a job runs is decided by its rules); one list of things never allowed, for packs and users alike. The `trusted_commands`, `trusted_env`, `trusted_mcp_tools` and `trusted_domains` answers are gone (ignored if present). Re-run the installer (`--update`).
- Optional strict mode (`"strict": true`): Claude Code's sandbox around every job command; packs declare the hosts they reach (`network`).
- Private packs (`pack_dirs` in the answers): packs kept outside the repository, which may replace or exclude core files (templates, rules, language). See docs/private-packs.md.
- Runtime-only installs (`--runtime-only`): runner, guard, jobs and schedule on an existing vault, nothing written in it but `.control-tower/`.
- `install.py --update`: refresh the kit files you never edited, keep the ones you edited (new version saved in `.control-tower/updates/`), leave deleted files deleted. See docs/updating.md.
- Job guard: jobs can read their skills, adapter notes and rules again (they wrote empty reports); glob and grep bypasses closed. Re-run the installer (`--update`) to get the fixed guard.

## 0.1.0 (unreleased)

- Core vault, four packs (engineering, developer, product, marketing), fourteen tool adapters.
- Guided installer skill, terminal wizard, answers files, doctor and uninstaller.
- Local scheduled jobs (launchd, cron) with a guard hook; cloud routine prompts.
- End-to-end tests with a fake `claude`, a clean Linux container test and CI on Ubuntu and macOS.
- Cloud routines with machine-readable metadata; the guided installer offers them and creates the ones the user ticks, never duplicates.
- Requires Python 3.9+ (job times are converted with `zoneinfo`).
