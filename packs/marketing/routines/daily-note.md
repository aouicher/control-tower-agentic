---
id: daily-note
name: "Daily note"
days: mon-fri
time: "07:30"
connectors_required: []
connectors_optional: [calendar]
vault: write
after: ""
---

# Routine: daily note

Creates or completes today's daily note: content going live, overdue items, meetings.

| Setting | Value |
|---|---|
| Schedule | mon-fri at 07:30 ({{ct.timezone}}) |
| Connectors | required: none; optional: `calendar` |
| Vault | Needs the vault repository attached to the routine (it writes notes). |

The guided installer can create this routine for you (`/install-control-tower`). To create it by hand, paste everything under **Prompt** into a new claude.ai routine.

## Prompt

You are running unattended. Never ask, never wait. Follow the vault's CLAUDE.md and `.claude/rules/marketing.md`. Write in English. Read-only on external tools.

1. Get today's date and year. Create `journal/daily/<YYYY>/<YYYY-MM-DD>.md` from `_system/templates/daily.md` if it does not exist. If it exists, only add what is missing.
2. List content from `work/content/` (`type: content`) with `publish_date` today or tomorrow and `stage` not `published`, and open tasks from `work/` that are due today or overdue. Never copy these tasks: link their notes.
3. If a calendar tool is available, add today's events to the meetings table, skipping declined ones.
4. Priorities: pick at most 3 among overdue items, pieces going live today, and blocked campaigns. Each ends with a wikilink.
5. You cannot check the vault for duplicate tasks, so do not create tasks. Write suggestions as plain text under `## 📝 Notes`, tagged `#to-triage` if they are phrased as tasks.
6. Never write `rag`, `owner`, `due` or `group` of an existing note.
