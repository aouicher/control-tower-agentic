---
id: morning-brief
name: "Morning brief"
days: mon-fri
time: "07:45"
connectors_required: []
connectors_optional: [calendar, analytics]
vault: write
after: ""
---

# Routine: morning brief

Content due in the next three days, today's meetings and yesterday's traffic against last week.

| Setting | Value |
|---|---|
| Schedule | mon-fri at 07:45 ({{ct.timezone}}) |
| Connectors | required: none; optional: `calendar`, `analytics` |
| Vault | Needs the vault repository attached to the routine (it writes notes). |

The guided installer can create this routine for you (`/install-control-tower`). To create it by hand, paste everything under **Prompt** into a new claude.ai routine.

## Prompt

You are running unattended. Never ask, never wait. Follow the vault's CLAUDE.md and `.claude/rules/marketing.md`. Write in English. Read-only on every external tool; write only inside the vault.

1. Read the page `cockpit/content-calendar.md` and the notes in `work/content/` to find what goes live in the next 3 days and what is overdue.
2. If a calendar tool is available, list today's events and link each to the campaign or content note it relates to.
3. If an analytics tool is available, read yesterday's traffic and compare it with the same weekday last week (same period length). If the data is sampled, limited or truncated, write "at least N" or "estimated" and say why. If nothing is available, skip this part without comment.
4. Write `journal/reports/morning-brief-YYYY-MM-DD.md`, `type: report`, `report_kind: "morning-brief"`, double-quoted free text, with `🕐 Generated on DD/MM/YYYY at HH:MM` under the title and `> [!summary] Summary` of 3 bullets: what goes live today, what is at risk, what needs a decision.
5. Sections: `## 📅 Today` (events and launches), `## ⏰ Due soon and overdue` (table `| Piece | Channel | Date | Stage |`), `## 📊 Figures` (only if available), `## ✅ Actions`.
6. You cannot check the vault for duplicate tasks: write tasks only for important new findings, tagged `#to-triage`, at most 3.
7. Never write `rag`, `owner`, `due` or `group` of an existing note.
