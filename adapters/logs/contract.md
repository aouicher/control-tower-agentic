# Contract: logs (log search and metrics)

## Purpose

Lets jobs and skills measure error volume and recurring failures in application logs from a log platform (CloudWatch Logs, Datadog Logs, ...), without reading raw lines.

## Inputs the job gives

| Input | Meaning |
|---|---|
| `resources` | Full resource identifiers (log group name or ARN, index, service) |
| `window_start`, `window_end` | Absolute timestamps with timezone |
| `noise_filters` | Known-noise patterns to exclude |
| `level_field` | Field holding the level for this log format (see Pitfalls) |

## Outputs it expects (fields)

One record per resource.

| Field | Meaning |
|---|---|
| `resource` | The full identifier that was queried |
| `window` | Start and end actually queried |
| `records_scanned` | Number of records scanned by the query (as reported by the tool) |
| `error_count` | Count of records at error level or above, after noise exclusion |
| `top_signatures` | Up to 10 `{signature, count}` pairs, normalised message or error class |
| `first_seen` | Timestamp of the earliest matching record in the window |

## Pagination and truncation

- Always pass the full resource identifier. A bare name can resolve to the wrong environment or account.
- Query one log group (or resource) per call. Do not merge unrelated resources in one query.
- Prefer one aggregate query per resource (count by level, count by signature) over reading raw lines. Raw lines are read only to confirm a signature, with a small limit.
- Query results are capped (often thousands of rows or a maximum per page). When the cap is reached, say "at least N" and narrow the window instead of paging blindly.
- Exclude known noise (health checks, bots, expected retries) before counting, and say what was excluded.

## Pitfalls

- A query that scanned zero records is a coverage gap (wrong resource, wrong window, ingestion delay, no access), never "healthy". Report it as `records_scanned: 0, coverage gap`.
- Use the right level field per log format: structured JSON logs, plain-text logs and platform-generated logs do not share the same field or values. Check one sample record first.
- Counts depend on the window: compare windows of equal length.
- Do not copy log lines into the vault: they can contain personal data and secrets. Keep signatures, counts and timestamps.

## Read-only guarantees

Read and query permissions only. Never create, modify or delete log groups, indexes, monitors, pipelines or retention settings.

Some tools have no read-only mode (see `read_only` and `read_only_mitigation` in the adapter manifest). For those, the guarantee comes from the mitigation (view-only account, restricted role or token, denied write tools), not from the tool: apply it before use and never call a write tool.

## Failure handling

- Access denied or unknown resource: report the resource as "not queried" with the reason.
- Query timeout or cancellation: retry once with a narrower window, then report a coverage gap.
- Query cost: queries can be billed by volume scanned. Keep windows tight and avoid unbounded scans.
