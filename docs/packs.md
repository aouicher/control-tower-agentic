# Packs

A pack is a profile: it overlays the core vault with extra skills, templates, dashboards, cockpit pages, scheduled jobs and cloud routines. Install one or several; they never collide (this is tested).

| Pack | For | Skills | Jobs | Needs |
|---|---|---|---|---|
| `engineering` | Engineering leaders | weekly-digest, postmortem, adr, questionnaire-answer | morning-triage, service-health, debt-review, weekly-digest | calendar; optional tracker, code, errors, quality, logs |
| `developer` | Developers | standup, review-queue, worklog, debug-journal | morning-prs, weekly-wrap | code; optional tracker, errors, calendar |
| `product` | Product managers | discovery-notes, prioritize, prd-draft, product-weekly | product-weekly, feedback-digest | calendar; optional tracker, analytics, crm |
| `marketing` | Marketing leads | campaign-brief, content-calendar, weekly-metrics, competitor-watch | weekly-metrics, content-reminders | none required; optional analytics, crm, tracker, calendar |

Every pack also ships cloud routines (`daily-note`, `weekly-review`, `morning-brief`; engineering adds `overnight-health`) in `packs/<id>/routines/`, and a README in its folder. A routine is offered only when its required connectors have a tool; `/install-control-tower routines` creates the ones you choose on claude.ai (see [scheduling](scheduling.md#cloud-routines)).

## Vocabulary

Each pack renames a few words so the vault speaks your language. Marketing, for example, shows *campaigns* instead of *workstreams* and *teammates* instead of *people*. Folder names and property values stay stable, so packs can be mixed.

## Jobs need their tools

A job is installed only if every capability it needs has a tool. Choose `none` for a capability and the jobs that depend on it are skipped; the installer lists them. Skills always install, and work with whatever you paste or connect.

## Changing schedules

Defaults are in each `job.json`. Override at install time with the answers file:

```json
"jobs": {"morning-prs": {"time": "07:15", "days": "mon,wed"}}
```

## Writing your own pack

See [docs/design/pack-spec.md](design/pack-spec.md) and [CONTRIBUTING.md](../CONTRIBUTING.md). A pack is a folder with `pack.json`, `vocabulary.json`, `vault/`, `jobs/` and `routines/`; the test suite checks it automatically.
