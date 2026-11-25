# Routine: daily note

Paste the prompt below into a claude.ai cloud routine. Suggested schedule: weekdays at 07:30 ({{ct.timezone}}). Prerequisites: the vault device is linked to the routine, and the `calendar` connector is enabled.

## Prompt

```text
Scheduled routine "daily-note" for {{ct.owner_name}}. Nobody answers questions: never ask, never wait. Read and write the vault at {{ct.vault_path}} through the linked device; follow its CLAUDE.md and .claude/rules/engineering.md. Read-only on every other system. Write in English.

1. Get today's date and time in {{ct.timezone}}.
2. If journal/daily/<YYYY>/<YYYY-MM-DD>.md already exists, do nothing and stop. Otherwise create it from _system/templates/daily.md.
3. Fill the agenda from the calendar connector: today's events with time, title and attendees as wikilinks when a note exists in team/. Flag events overlapping each other and days with more than 5 hours of meetings.
4. Read the latest reports in journal/reports/ (triage, health, delivery) and add under the title ONE line per report that has a red or amber finding, as a wikilink with its headline. Do not copy their content.
5. Add today's tasks ONLY if they are due today and live in a daily-only context. Never copy tasks from other notes: a task lives once, in its project, area, {{ct.team}}, {{ct.workstream}} or {{ct.risk}} note. The cockpit shows the rest.
6. Never create tasks, except proposals tagged #to-triage in the Actions section, at most 2, and only when the calendar shows a meeting with no preparation note.
7. Do not modify any other note. Final answer: one line with the note path.
```
