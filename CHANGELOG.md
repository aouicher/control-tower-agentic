# Changelog

## 0.1.0 (unreleased)

- Core vault, four packs (engineering, developer, product, marketing), fourteen tool adapters.
- Guided installer skill, terminal wizard, answers files, doctor and uninstaller.
- Local scheduled jobs (launchd, cron) with a guard hook; cloud routine prompts.
- End-to-end tests with a fake `claude`, a clean Linux container test and CI on Ubuntu and macOS.
- Cloud routines with machine-readable metadata; the guided installer offers them and creates the ones the user ticks, never duplicates.
- Requires Python 3.9+ (job times are converted with `zoneinfo`).
