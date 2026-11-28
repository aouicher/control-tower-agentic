# Adapter: Datadog Logs (logs)

Official documentation: https://docs.datadoghq.com/bits_ai/mcp_server/, setup https://docs.datadoghq.com/mcp_server/setup.md, tools https://docs.datadoghq.com/mcp_server/tools.md

## Setup

Datadog hosts a remote MCP server. The endpoint depends on your site: `https://mcp.<site>/v1/mcp`, for example `https://mcp.datadoghq.com/v1/mcp` (US1) or `https://mcp.datadoghq.eu/v1/mcp` (EU1). Other sites are listed on the setup page; the US1-FED and US2-FED sites are not supported.

```
claude mcp add --scope project --transport http datadog-mcp https://mcp.datadoghq.com/v1/mcp
```

The documentation also recommends the official plugin: `/plugin install datadog@claude-plugins-official`. The `toolsets` query parameter selects toolsets (default `core`, which contains the logs tools); `omit_tools` removes tools.

## Authentication and least-privilege scopes

- OAuth 2.0 is recommended: the client completes the flow at setup.
- For automation, a Personal Access Token or a Service Access Token can be sent as `Authorization: Bearer <token>`: select only the scopes needed, set an expiry, and put the token in the client configuration yourself, never in a prompt.
- Legacy API and application keys are accepted but not recommended.
- Access follows the user or service account permissions. The logs tools need `Logs Read Data` and `Logs Read Index Data` (and `Timeseries` for `analyze_datadog_logs`). Use an account with read permissions only: write tools check write permissions on each call.

## Commands or tools to call

- `analyze_datadog_logs`: SQL queries for counts and aggregations (use this first).
- `search_datadog_logs`: returns individual log details, filtered by time, query, service, host and storage tier. Parameter names: check the official documentation.
- Both are documented as read-only. Burst limit: 50 tool calls per 10 seconds. Responses are truncated by estimated length; most tools accept `max_tokens`.

## Field mapping to the contract

| Contract field | Datadog |
|---|---|
| `resource` | service, index or log source used in the query, written in full |
| `window` | time range passed to the query |
| `error_count`, `top_signatures`, `first_seen` | SQL aggregates from `analyze_datadog_logs` (count by status, by error message or class, min timestamp) |
| `records_scanned` | check the official documentation; if absent, report the count of matching records and say the scan size is unknown |

## Pitfalls

- Level lives in the log status or in a custom attribute depending on the pipeline: inspect one record first.
- Logs can sit in several indexes or storage tiers: name the one queried.
- Response truncation can hide rows: say "at least N".
- Zero matching logs for a service can mean a wrong service tag, not health.

## Verification

Ask Claude Code: "With analyze_datadog_logs, count the logs of service <name> over the last hour." Run `/mcp` to confirm the connection.
