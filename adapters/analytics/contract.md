# Contract: analytics (product or web analytics)

## Purpose

Lets jobs report a small set of key metrics, with a comparison, from an analytics platform (Google Analytics, Amplitude, ...).

## Inputs the job gives

| Input | Meaning |
|---|---|
| `metrics` | Metrics or events to report, using the tool's own names |
| `period` | Absolute start and end dates and timezone |
| `previous_period` | Same-length period to compare with (default: the period just before) |
| `segment` | Optional segment, platform, country or cohort |

## Outputs it expects (fields)

| Field | Meaning |
|---|---|
| `metric` | Metric or event name as defined in the tool |
| `period` | Start and end dates, timezone |
| `value` | Value for the period |
| `previous_period` | Value for the comparison period, with its dates |
| `segment` | Segment applied, or `all` |

Add `delta` (absolute and percent) when both values exist, and a `sampled` flag.

## Pagination and truncation

- Report rows are capped. When the cap is reached, say "at least N rows" and narrow the query.
- Large queries can be truncated or time out: split by period or segment.

## Pitfalls

- State the period in every figure. A number without dates is not usable.
- Compare like with like: same length, same weekdays when possible, no partial current day.
- Never report numbers from a sampled export without saying so.
- Metric definitions differ between tools (users, sessions, active users): quote the tool's definition, do not rename.
- Data for recent days can still change (processing delay): flag the latest days.
- Do not store customer personal data (user ids, emails, session replays) in the vault. Aggregates only.

## Read-only guarantees

Read and report permissions only. Never create, edit or delete events, properties, dashboards, cohorts, experiments or flags, and never send events.

Some tools have no read-only mode (see `read_only` and `read_only_mitigation` in the adapter manifest). For those, the guarantee comes from the mitigation (view-only account, restricted role or token, denied write tools), not from the tool: apply it before use and never call a write tool.

## Failure handling

- Unknown metric or event: report it as "not found" and list close names, never a zero.
- No access to a property or project: report "analytics: no access" for it.
- Zero rows: state the period and filters, so a real zero is distinguishable from a misconfiguration.
