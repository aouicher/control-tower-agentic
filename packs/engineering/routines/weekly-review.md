---
id: weekly-review
name: "Weekly review"
days: fri
time: "17:30"
connectors_required: []
connectors_optional: []
vault: write
after: "weekly-digest"
---

# Routine: weekly review

Writes the weekly review note after the weekly digest job.

| Setting | Value |
|---|---|
| Schedule | fri at 17:30 ({{ct.timezone}}), after the `weekly-digest` job |
| Connectors | required: none; optional: none |
| Vault | Needs the vault repository attached to the routine (it writes notes). |

The guided installer can create this routine for you (`/install-control-tower`). To create it by hand, paste everything under **Prompt** into a new claude.ai routine.

## Prompt

Scheduled routine "weekly-review" for {{ct.owner_name}}. Nobody answers questions: never ask, never wait. Read and write the vault repository attached to this routine; follow its CLAUDE.md and .claude/rules/engineering.md. Read-only on every other system. Write in English.

1. Get the ISO week and its Monday to Sunday dates in {{ct.timezone}}.
2. Follow the vault skill .claude/skills/weekly-review/SKILL.md to write journal/daily/<YYYY>/<YYYY-Www>-weekly.md from _system/templates/weekly.md: done, carried over, trends and signals.
3. In the trends section, use the delivery report of this week (journal/reports/delivery-<YYYY-Www>.md) when it exists, plus the latest triage, health and debt reports. Link them, do not copy them. If the delivery report is missing, say so in one line.
4. Signals about {{ct.people}} (load, review queue) are talking points for 1-1s, never verdicts, and are not written into notes under team/.
5. Propose the top 3 for next week from open items, blockers and active {{ct.workstreams}}. Leave the wins and lessons section with a short placeholder line for the user.
6. Duplicates: run python3 _system/tools/duplicate-tasks.py only if shell access is allowed; otherwise write "not checked" in the section. Never change a task.
7. Never create tasks except proposals tagged #to-triage, at most 3. Never write rag, owner, due or group of any note. Final answer: the summary callout.
