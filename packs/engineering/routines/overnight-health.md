---
id: overnight-health
name: "Overnight health"
days: mon-fri
time: "08:30"
connectors_required: []
connectors_optional: []
vault: write
after: "service-health"
---

# Routine: overnight health

Fallback when the local service-health job could not run: reports what is missing instead of querying production.

| Setting | Value |
|---|---|
| Schedule | mon-fri at 08:30 ({{ct.timezone}}), after the `service-health` job |
| Connectors | required: none; optional: none |
| Vault | Needs the vault repository attached to the routine (it writes notes). |

The guided installer can create this routine for you (`/install-control-tower`). To create it by hand, paste everything under **Prompt** into a new claude.ai routine.

## Prompt

Scheduled routine "overnight-health" for {{ct.owner_name}}. Nobody answers questions: never ask, never wait. Read and write the vault repository attached to this routine; follow its CLAUDE.md and .claude/rules/engineering.md. Read-only on every other system. Write in English.

1. Get today's date and time in {{ct.timezone}}.
2. Read journal/reports/health-<today>.md and triage-<today>.md. Read library/services.md and cockpit/pulse.md.
3. If health-<today>.md does not exist, the job did not run: in cockpit/pulse.md, directly under the intro text and OUTSIDE the service blocks, write "🕐 Checked on DD/MM/YYYY at HH:MM: the service-health job produced no report today. Service states below are stale." Do not touch the service blocks and do not mark anything green.
4. If it exists, check coverage: list the services of library/services.md that have no row in its coverage table, rows with 0 records scanned, and service blocks in pulse.md whose 🕐 line is older than today. Report these as coverage gaps.
5. Write the result as ONE short note journal/reports/overnight-<today>.md (type: report, report_kind: health, status: draft) with: the 🕐 Generated line, a "> [!summary] Summary" callout (icon, headline, 3 bullets max), a table of gaps "| Service | Gap | Last checked |", and, for red findings only, proposed tasks "- [ ] <action> @{{ct.owner_handle}} #to-triage" (max 3; you cannot check the vault for duplicates, so skip findings already in yesterday's report).
6. Never create other tasks. Never write rag, owner, due or group. Final answer: the headline only.
