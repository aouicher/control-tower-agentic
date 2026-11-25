# Routine: daily note

Paste into a claude.ai cloud routine, scheduled on weekdays at 07:30 ({{ct.timezone}}).

```
Unattended routine: never ask, never wait. Read-only on external systems; write only inside the vault at {{ct.vault_path}}. Follow CLAUDE.md. Write in English.

1. Get today's date and real time with `date`.
2. If journal/daily/<YYYY>/<YYYY-MM-DD>.md does not exist, create it from _system/templates/daily.md. If it exists, only append, never overwrite.
3. Use the calendar adapter in .claude/adapters/calendar.md to list today's meetings. Under "Agenda" add one line per meeting: time, title, and a wikilink to the related {{ct.workstream}} if the title clearly names one.
4. List open tasks due today or overdue from work/ and team/ (exclude journal/daily/). Do not copy them into the daily note: link their notes. Daily notes only hold tasks for today.
5. Add a "Product focus" line: the interview, PRD or ranking review that has been waiting longest, as a suggestion.
6. Any task you propose carries #to-triage. You cannot check for duplicates, so propose only new, important items. Never write rag, owner, due or stage of existing notes.
```
