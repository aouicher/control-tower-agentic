# Routine: daily note

Paste into a claude.ai cloud routine. Suggested schedule: weekdays at 07:45 in your timezone. Requires the vault repository and the `code` connector.

---

You run unattended: never ask, never wait. Read-only on every external system; write only inside the vault repository. Follow `CLAUDE.md` and `.claude/rules/developer.md`. Write in English.

1. Get today's date. If `journal/daily/<YYYY>/<YYYY-MM-DD>.md` does not exist, create it from `_system/templates/daily.md`, replacing the `{{date:...}}` placeholders with real values.
2. In `## 🎯 Focus`, propose up to 3 items from: tasks due today or overdue in `work/` and `team/` (never copy them as tasks; reference them with wikilinks), pull requests of the user with failing CI or changes requested, and `blocker` values of active notes.
3. If the calendar connector is available, fill `## 📅 Agenda` with today's events (skip declined ones); otherwise leave it untouched.
4. Do not create tasks. Never write `rag`, `owner`, `due` or `group`.
5. Commit the change with a message `docs(daily): daily note YYYY-MM-DD`.
