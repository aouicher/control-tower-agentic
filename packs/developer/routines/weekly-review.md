---
id: weekly-review
name: "Weekly review"
days: fri
time: "17:00"
connectors_required: []
connectors_optional: []
vault: write
after: "weekly-wrap"
---

# Routine: weekly review

Writes the weekly review note from the week's daily notes and the weekly wrap report.

| Setting | Value |
|---|---|
| Schedule | fri at 17:00 ({{ct.timezone}}), after the `weekly-wrap` job |
| Connectors | required: none; optional: none |
| Vault | Needs the vault repository attached to the routine (it writes notes). |

The guided installer can create this routine for you (`/install-control-tower`). To create it by hand, paste everything under **Prompt** into a new claude.ai routine.

## Prompt

You run unattended: never ask, never wait. Read-only on every external system; write only inside the vault repository. Follow `CLAUDE.md` and `.claude/rules/developer.md`. Write in English.

1. Read this week's daily notes in `journal/daily/<YYYY>/` and the latest `journal/reports/dev-weekly-wrap-*.md`.
2. Create `journal/daily/<YYYY>/<YYYY-MM-DD>-weekly-review.md` (date of the Friday) from `_system/templates/weekly.md`, type `weekly`.
3. Fill: what shipped (links to pull requests from the wrap report), decisions made, what was learned (link debug journals), what blocked you, and three candidate priorities for next week.
4. Propose at most 3 follow-ups as `- [ ] text @me #to-triage` inside the weekly review note. You cannot check the vault for duplicates, so propose only new important items.
5. Never write `rag`, `owner`, `due` or `group`. Never include secrets or customer data.
6. Commit the change with a message `docs(weekly): weekly review YYYY-MM-DD`.
