# Routine: weekly review

For a claude.ai cloud routine. Suggested schedule: Friday, 16:00. Needs access to the vault.

## Prompt

You are running unattended. Never ask, never wait. Follow the vault's CLAUDE.md and `.claude/rules/marketing.md`. Write in English. Read-only on external tools.

1. Compute the current ISO week (Monday to Sunday) and compare it with the previous 7 days when you compare anything: same length, same definitions.
2. Read `work/` and `team/` (not old daily notes). Collect tasks done this week (with their `✅` date), open tasks past their due date, campaigns with `rag: red|amber` or a blocker, content pieces published this week, content that slipped (publish date passed, stage not `published`).
3. If this week's `journal/reports/marketing-metrics-YYYY-Www.md` or last Monday's report exists, quote its headline and link it. Never restate a number you cannot trace to a note; say "see the report" instead. If a figure comes from a truncated or sampled export, say so.
4. Write `journal/daily/<YYYY>/<YYYY-Www>-weekly.md` from `_system/templates/weekly.md`: done, carried over, signals, and a proposed top 3 for next week.
5. You cannot check the vault for duplicate tasks. Proposed next steps are plain bullets, or tasks tagged `#to-triage` for important new findings only. Do not edit any existing task.
6. Never write `rag`, `owner`, `due` or `group` of an existing note. Do not move or delete anything.
