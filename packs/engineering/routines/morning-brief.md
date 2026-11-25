# Routine: morning brief

Paste the prompt below into a claude.ai cloud routine. Suggested schedule: weekdays at 08:20 ({{ct.timezone}}), after the `morning-triage` and `service-health` jobs. Prerequisites: the vault device is linked, and the `calendar` connector is enabled.

## Prompt

```text
Scheduled routine "morning-brief" for {{ct.owner_name}}. Nobody answers questions: never ask, never wait. Read and write the vault at {{ct.vault_path}} through the linked device; follow its CLAUDE.md and .claude/rules/engineering.md. Read-only on every other system. Write in English.

1. Get the date and time in {{ct.timezone}}.
2. Read the vault only; do NOT re-query trackers, error tools or log tools: read today's journal/reports/triage-<date>.md and health-<date>.md (if missing, take the latest and say its date), cockpit/pulse.md, cockpit/delivery.md, and open #to-triage tasks.
3. Fetch today's calendar events with the calendar connector.
4. Write ONE brief as journal/reports/brief-<date>.md (type: report, report_kind: brief, status: draft; replace if it exists; never edit cockpit/today.md, it belongs to the today skill). Content: the line "🕐 Generated on DD/MM/YYYY at HH:MM" under the title, the headline with 🟢🟠🔴 (worst state among the reports), then at most 5 bullets: red or amber service findings, quality gates failing, today's meetings that need preparation, the oldest overdue or #waiting item, and any #to-triage items count. Link the source reports with wikilinks.
5. A source that is missing or stale is "not verified": never present absence of data as green.
6. Never create tasks, never edit other notes. Final answer: the headline only.
```
