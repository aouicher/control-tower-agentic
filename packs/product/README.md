# Product pack

For product managers, product leads and heads of product. It adapts the neutral core to the product loop: talk to customers, record opportunities, rank them, write the requirements, track delivery, report.

## What you get

| Piece | What it does |
|---|---|
| Note type `opportunity` | A problem worth solving, with RICE inputs and a `stage`. Lives in `work/opportunities/`. |
| Note type `interview` | One customer conversation, anonymised. Lives in `library/interviews/`. |
| Initiatives | Core `workstream` notes, shown as "initiatives". |
| Skills | `discovery-notes`, `prioritize`, `prd-draft`, `product-weekly`. |
| Templates | `opportunity`, `interview`, `prd`, `release-notes`. |
| Dashboard and page | `opportunities.base` (ranked by score, grouped by stage) and `cockpit/roadmap.md` (now, next, later). |
| Jobs | `product-weekly` (Friday 15:00) and `feedback-digest` (Monday 08:30). |
| Routines | `daily-note`, `weekly-review`, `morning-brief` prompts for claude.ai cloud routines. |

## Capabilities

Required: `calendar`. Optional: `tracker`, `analytics`, `crm`. Jobs degrade gracefully and say what they could not read.

## First week

1. **Day 1**: install, answer the capability questions, open `cockpit/roadmap.md`.
2. **Day 1**: create one initiative per thing your team is building now (core `workstream` template) and set `owner`, `team`, `due` yourself.
3. **Day 2**: paste your last interview notes into Claude and run `/discovery-notes`. Check that no personal data was kept.
4. **Day 3**: let `/discovery-notes` link or create opportunities, then fill `reach`, `impact`, `confidence`, `effort` on the top five.
5. **Day 4**: run `/prioritize`, read the ranking and the tie explanations, then change `stage` yourself.
6. **Day 5**: run `/prd-draft` for the top initiative; the Friday `product-weekly` job writes your first digest.
7. **Monday**: read the `feedback-digest` report and accept or drop its `#to-triage` tasks.
