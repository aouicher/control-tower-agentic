# Linear

Capability: `tracker`. Official documentation: https://linear.app/docs/mcp (MCP server) and https://linear.app/developers/pagination (API pagination).

## Setup

The documented Claude Code command for the standard server is:

```
claude mcp add --scope project --transport http linear-server https://mcp.linear.app/mcp
```

then run `/mcp` to complete authentication. For this adapter use the read-only endpoint the same page documents, `https://mcp.linear.app/mcp/readonly`, which exposes only read tools (the manifest uses it).

## Authentication and least-privilege scopes

Interactive OAuth 2.1 (default), or a bearer token / Linear API key in the `Authorization: Bearer` header. The documentation gives three read-only routes: the `/mcp/readonly` endpoint, the standard endpoint with only the `read` OAuth scope, or an API key created with only the Read permission. Prefer one of them; never grant write. The documentation excerpt read does not list tool names, so the manifest keeps `permissions_allow` empty: after connecting, list the read-only tools of the server (`/mcp`) and allow them by exact name, never with a wildcard.

## Commands or tools to call

The server exposes tools for issues, teams, cycles and projects: run the tool list after connecting and check the official documentation for current names. Needed reads: list issues filtered by team, cycle, state, assignee, and completion date.

The Linear API paginates with Relay-style cursors: `first` and `after`, then `pageInfo.endCursor` while `pageInfo.hasNextPage` is true. The default page is 50 items; the documentation excerpt does not state a maximum, so check the official documentation.

## Field mapping to the contract

| Contract | Linear (check the API schema for exact field names) |
|---|---|
| `key` | issue identifier (team key plus number) |
| `title` | title |
| `status` | workflow state name |
| `status_category` | workflow state type (for example backlog, unstarted, started, completed, canceled): map to todo / in_progress / done |
| `assignee` | assignee name |
| `sprint` | cycle name or number |
| `labels_or_type` | labels |
| `priority` | priority |
| `updated` | updated at |
| `url` | issue URL |

## Pitfalls

- Default page is 50: keep following `endCursor` until `hasNextPage` is false before counting.
- Linear calls sprints "cycles": filter by the active cycle for sprint status.
- A "Blocked" state or label is not always technical; relations ("blocked by") are a better signal.
- Dates are timestamps: use an exclusive upper bound.
- PR links and branch names carry the issue identifier: use it as the join key with the code adapter.

## Verification

Authenticate, list the issues of the active cycle for one team, paginate to the end and compare with the cycle view in Linear.
