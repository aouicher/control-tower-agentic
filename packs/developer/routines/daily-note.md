---
id: daily-note
name: "Daily note"
days: mon-fri
time: "07:45"
connectors_required: [code]
connectors_optional: [calendar]
vault: write
after: ""
---

# Routine: daily note

Creates or completes today's daily note: focus items and agenda.

| Setting | Value |
|---|---|
| Schedule | mon-fri at 07:45 ({{ct.timezone}}) |
| Connectors | required: `code`; optional: `calendar` |
| Vault | Needs the vault repository attached to the routine (it writes notes). |

The guided installer can create this routine for you (`/install-control-tower`). To create it by hand, paste everything under **Prompt** into a new claude.ai routine.

## Prompt

You run unattended: never ask, never wait. Read-only on every external system; write only inside the vault repository. Follow `CLAUDE.md` and `.claude/rules/developer.md`. Write in English.

1. Get today's date. If `journal/daily/<YYYY>/<YYYY-MM-DD>.md` does not exist, create it from `_system/templates/daily.md`, replacing the `{{date:...}}` placeholders with real values.
2. In `## 🎯 Focus`, propose up to 3 items from: tasks due today or overdue in `work/` and `team/` (never copy them as tasks; reference them with wikilinks), pull requests of the user with failing CI or changes requested, and `blocker` values of active notes.
3. If the calendar connector is available, fill `## 📅 Agenda` with today's events (skip declined ones); otherwise leave it untouched.
4. Do not create tasks. Never write `rag`, `owner`, `due` or `group`.
5. Commit the change with a message `docs(daily): daily note YYYY-MM-DD`.
