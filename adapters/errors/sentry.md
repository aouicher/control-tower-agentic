# Adapter: Sentry (errors)

Official documentation: https://mcp.sentry.dev/ (the page https://docs.sentry.io/product/sentry-mcp/ redirects to it).

## Setup

Sentry hosts a remote MCP server at `https://mcp.sentry.dev/mcp`. The URL can be scoped to an organization (`/{organizationSlug}`) or a project (`/{organizationSlug}/{projectSlug}`):

```
claude mcp add --scope project --transport http sentry https://mcp.sentry.dev/mcp/{organizationSlug}/{projectSlug}
```

Project scoping is recommended by the documentation when possible. A local alternative uses the Sentry CLI login (`sentry auth login`). For self-hosted Sentry, check the official documentation (it mentions `SENTRY_HOST`).

## Authentication and least-privilege scopes

- OAuth: the first connection opens an authentication flow. No token is stored in the configuration.
- The documentation page does not list the OAuth scopes and does not describe a read-only mode. Check the official documentation, and grant the account the minimum role needed to read issues. Do not call tools that update issues or manage projects. The manifest says `read_only: false` because no read-only mode is documented.

## Commands or tools to call
Run `/mcp`, review the tool list, and allow only the read-only tools (`permissions_allow` is empty on purpose: never a wildcard, never guessed names).


The page describes capabilities (searching errors, triaging issues, reading documentation, managing projects) but does not list tool names. Run `/mcp` in Claude Code to see the tools exposed, and use only the search and read ones.

## Field mapping to the contract

| Contract field | Sentry |
|---|---|
| `project` | project slug |
| `item_id` | issue short id or id |
| `title`, `level`, `status` | issue title, level, status |
| `environment` | environment tag of the issue |
| `first_seen`, `last_seen` | issue first seen and last seen |
| `occurrences` | issue event count (cumulative) |
| `url` | issue permalink |

Exact field names depend on the tool output: check the official documentation.

## Pitfalls

- Whether a time window can be passed to the search is not stated in the page: if not, list recent issues and filter on `first_seen` or `last_seen`.
- Event counts are cumulative since issue creation.
- Scoped connections hide some discovery tools.
- Results may be capped: say "at least N" when the list is full.

## Verification

Ask Claude Code: "List the five most recent unresolved Sentry issues." Run `/mcp` to confirm the server is connected.
