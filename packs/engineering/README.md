# Engineering pack

For heads of engineering, CTOs and engineering managers. It adapts the control tower to run delivery, service health, {{ct.risks}} and architecture decisions from one Obsidian vault.

Vocabulary: {{ct.team}} = squad, {{ct.workstream}} = topic, {{ct.risk}} = incident, {{ct.person}} = direct report.

## What it gives

| Piece | What it does |
|---|---|
| Skill `weekly-digest` | Weekly delivery report: PRs merged per {{ct.team}}, sprint status, blocked and in-review items, load per {{ct.person}} (signals for 1-1s, never verdicts), {{ct.workstream}} notes refreshed |
| Skill `postmortem` | Blameless write-up of an {{ct.risk}} into `work/risks/` |
| Skill `adr` | Architecture decision record in the current repository, plus an index note in `work/decisions/` |
| Skill `questionnaire-answer` | Draft answers to security or compliance questionnaires from code and docs; the draft stays outside the vault |
| Job `morning-triage` | 08:00 Mon-Fri: new errors and quality gates |
| Job `service-health` | 08:10 Mon-Fri: log and error health per service listed in `library/services.md` |
| Job `debt-review` | Friday 10:00: quality and dependency alerts into an area note |
| Job `weekly-digest` | Friday 16:00: runs the `weekly-digest` skill logic |
| Cockpit pages | `cockpit/pulse.md` (service health) and `cockpit/delivery.md` (weekly delivery) |
| Dashboard | `delivery.base`: delivery reports over time |
| Routines | `daily-note`, `weekly-review`, `morning-brief`, `overnight-health`: prompts to paste into claude.ai cloud routines |

Capabilities: `calendar` is required. `tracker`, `code`, `errors`, `quality` and `logs` are optional; a job whose capability is missing is simply not installed.

## Rules the pack adds

See `.claude/rules/engineering.md` in your vault: how delivery is counted, how a RAG is proposed, how {{ct.risks}} are handled, and what automations may write.

## First week

1. **Day 1**: install the pack, answer the tool questions. Fill `library/services.md` (one row per service: where its logs and error project live).
2. **Day 1**: create one note per {{ct.team}} in `team/` with its `tracker` property (issue key prefixes, for example `ALPHA, ALPHB`). The digest maps PRs to {{ct.teams}} through these prefixes.
3. **Day 2**: create one {{ct.workstream}} note per initiative under `work/workstreams/<{{ct.team}}-slug>/` and set `rag`, `owner` and `due` yourself. Automations never write those.
4. **Day 2**: check the connection of each adapter with its `verify` step, then run `morning-triage` and `service-health` once by hand and read the reports in `journal/reports/`.
5. **Day 3**: open `cockpit/pulse.md`. Anything red or amber with no coverage line is a gap in `library/services.md`, not a healthy service.
6. **Friday**: read the delivery report from the `weekly-digest` job, use the per-{{ct.person}} signals to prepare your 1-1s, then validate or change the proposed RAG on each {{ct.workstream}}.
7. **When something breaks**: run `/postmortem` while it is fresh. **When you decide something durable**: run `/adr`.
8. **When a questionnaire arrives**: run `/questionnaire-answer`. The draft never enters the vault; only the follow-up tasks do.
