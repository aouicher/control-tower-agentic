# Adapter: Amplitude (analytics)

Official documentation: https://amplitude.com/docs/amplitude-ai/amplitude-mcp and https://amplitude.com/docs/amplitude-ai/amplitude-mcp/claude-code

## Setup

Amplitude hosts a remote MCP server. US endpoint `https://mcp.amplitude.com/mcp`, EU endpoint `https://mcp.eu.amplitude.com/mcp`.

```
claude mcp add --transport http --scope user Amplitude https://mcp.amplitude.com/mcp
```

`--scope user` makes it available in every session; the default `local` scope keeps it to the current project. To switch region, remove the entry, add it again with the other URL, run `/mcp` and authenticate again. Availability depends on the plan (documented: Enterprise included, Plus as an add-on, Free and Growth not included).

## Authentication and least-privilege scopes

- OAuth, no API key to manage. The server acts with the permissions of the signed-in user.
- Reads need the RBAC action Use MCP (read); writes need Use MCP (write). The Viewer role has read only, the Member, Manager and Admin roles have read and write. Use a Viewer account for this adapter.
- The Amplitude MCP server is read and write by design and has no read-only switch in the documentation: restrict by role and never call the write tools.

## Commands or tools to call

Documented tools: `get_amplitude_context`, `query_amplitude_data`, `get_amp_taxonomy` (with `action: workspace`), `list_tool_categories`, `get_category_tools`, `describe_tool`. Write-capable tools to avoid: `manage_amp_events`, `run_amp` (creates guides and surveys). Chart, dashboard and cohort tools: check the official documentation before use.

## Field mapping to the contract

| Contract field | Amplitude |
|---|---|
| `metric` | event or metric name from the taxonomy |
| `period`, `previous_period` | two date ranges in the query |
| `value` | value returned by `query_amplitude_data` |
| `segment` | segment or user property filter of the query |

## Pitfalls

- Use the project named in the job: the account may see several projects.
- The documentation mentions that large charts may be truncated, token limit errors can occur and complex queries can time out: split by period or segment and say so.
- The documentation states no row or rate limits: do not assume any.
- The server is not an ingestion path: never send events through it.
- Do not store user ids or session replay content in the vault.

## Verification

Ask Claude Code: "Which Amplitude projects can I access?" A list of projects confirms the connection.
