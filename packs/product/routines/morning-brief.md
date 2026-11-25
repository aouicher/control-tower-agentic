---
id: morning-brief
name: "Morning brief"
days: mon-fri
time: "07:45"
connectors_required: []
connectors_optional: [calendar, tracker, analytics]
vault: write
after: ""
---

# Routine: morning brief

Regenerates the today page: agenda with preparation, due tasks, items to triage and product signals.

| Setting | Value |
|---|---|
| Schedule | mon-fri at 07:45 ({{ct.timezone}}) |
| Connectors | required: none; optional: `calendar`, `tracker`, `analytics` |
| Vault | Needs the vault repository attached to the routine (it writes notes). |

The guided installer can create this routine for you (`/install-control-tower`). To create it by hand, paste everything under **Prompt** into a new claude.ai routine.

## Prompt

Unattended routine: never ask, never wait. Read-only on every external system; write only inside the vault repository attached to this routine. Follow CLAUDE.md. Write in English.

Write cockpit/today.md (regenerate it fully, with "🕐 Generated on DD/MM/YYYY at HH:MM" from `date`) with:
1. Agenda: today's meetings from the calendar adapter (.claude/adapters/calendar.md), each with prep: the linked {{ct.workstream}}, the last interview or decision related to it.
2. Overdue and due-today tasks from work/ and team/ (exclude journal/daily/), top 8, as links to their notes.
3. Items tagged #to-triage waiting for me (count only after reading all matches).
4. Product watch: if the tracker or analytics adapters (.claude/adapters/) are configured, up to 3 notable changes since yesterday. Trackers return at most 100 items per page: paginate or write "at least N (truncated)". Mark sampled metrics "sampled" and compare like with like.
5. One suggestion: the most valuable discovery or prioritisation action for today.

Propose tasks only as #to-triage and only for new, important findings (you cannot check for duplicates). Never write rag, owner, due or stage of existing notes.
