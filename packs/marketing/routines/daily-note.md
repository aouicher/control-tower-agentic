# Routine: daily note

For a claude.ai cloud routine. Suggested schedule: weekdays, 07:30. Needs access to the vault (connect the repository or folder that holds it).

## Prompt

You are running unattended. Never ask, never wait. Follow the vault's CLAUDE.md and `.claude/rules/marketing.md`. Write in English. Read-only on external tools.

1. Get today's date and year. Create `journal/daily/<YYYY>/<YYYY-MM-DD>.md` from `_system/templates/daily.md` if it does not exist. If it exists, only add what is missing.
2. List content from `work/content/` (`type: content`) with `publish_date` today or tomorrow and `stage` not `published`, and open tasks from `work/` that are due today or overdue. Never copy these tasks: link their notes.
3. If a calendar tool is available, add today's events to the meetings table, skipping declined ones.
4. Priorities: pick at most 3 among overdue items, pieces going live today, and blocked campaigns. Each ends with a wikilink.
5. You cannot check the vault for duplicate tasks, so do not create tasks. Write suggestions as plain text under `## 📝 Notes`, tagged `#to-triage` if they are phrased as tasks.
6. Never write `rag`, `owner`, `due` or `group` of an existing note.
