# Routine: weekly review

Paste into a claude.ai cloud routine. Suggested schedule: Friday at 17:00 in your timezone. Run after the `weekly-wrap` job.

---

You run unattended: never ask, never wait. Read-only on every external system; write only inside the vault repository. Follow `CLAUDE.md` and `.claude/rules/developer.md`. Write in English.

1. Read this week's daily notes in `journal/daily/<YYYY>/` and the latest `journal/reports/dev-weekly-wrap-*.md`.
2. Create `journal/daily/<YYYY>/<YYYY-MM-DD>-weekly-review.md` (date of the Friday) from `_system/templates/weekly.md`, type `weekly`.
3. Fill: what shipped (links to pull requests from the wrap report), decisions made, what was learned (link debug journals), what blocked you, and three candidate priorities for next week.
4. Propose at most 3 follow-ups as `- [ ] text @me #to-triage` inside the weekly review note. You cannot check the vault for duplicates, so propose only new important items.
5. Never write `rag`, `owner`, `due` or `group`. Never include secrets or customer data.
6. Commit the change with a message `docs(weekly): weekly review YYYY-MM-DD`.
