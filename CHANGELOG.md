# Changelog

## Unreleased

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
