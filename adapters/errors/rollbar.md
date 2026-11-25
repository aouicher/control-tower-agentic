# Adapter: Rollbar (errors)

Official documentation: https://docs.rollbar.com/docs/mcp-server-setup

## Setup

Rollbar publishes an MCP server as the npm package `@rollbar/mcp-server`, run with `npx`. The documentation shows it as an `.mcp.json` entry (server name `rollbar`, type `stdio`, command `npx -y @rollbar/mcp-server@latest`, environment variable `ROLLBAR_ACCOUNT_ACCESS_TOKEN`). Add the same server at user scope, so it is visible from the vault and from scheduled jobs, with the token taken from your environment:

```bash
claude mcp add --scope user rollbar --env ROLLBAR_ACCOUNT_ACCESS_TOKEN=$ROLLBAR_ACCOUNT_ACCESS_TOKEN -- npx -y @rollbar/mcp-server@latest
```

Single project instead: use `ROLLBAR_ACCESS_TOKEN` with a project token. Several projects: `ROLLBAR_CONFIG_FILE` pointing to a config file. `ROLLBAR_API_BASE` overrides the API base URL (default `https://api.rollbar.com/api/1`).

## Authentication and least-privilege scopes

- Use a token with **read scope only**. The documentation recommends read scope unless `update-item` is needed.
- An account token with read scope gives all read-only tools across projects; a project token covers one project.
- Never use a read and write token: it enables `update-item`. Do not allow that tool.
- Keep the token out of the vault and out of the repository; load it from the environment.

## Commands or tools to call

Documented tools: `list-projects`, `get-item-details`, `get-deployments`, `get-version`, `get-top-items` (last 24 hours), `list-items` (`status` defaults to `active`), `list-occurrences` (`limit` default 3, maximum 100; pages with `page` or `last_id`), `get-replay`, `update-item` (write, never call).

For the exact filters of `list-items` (environment, query, ordering), check the official documentation.

## Field mapping to the contract

| Contract field | Rollbar |
|---|---|
| `project` | project name from `list-projects` |
| `item_id` | item id (and counter) returned by `list-items` or `get-item-details` |
| `title`, `level`, `environment`, `status` | same-named properties of the item |
| `first_seen`, `last_seen` | item first and last occurrence timestamps |
| `occurrences` | total occurrences of the item (cumulative) |
| `url` | check the official documentation, otherwise build it from the project and item counter |

## Pitfalls

- Time filtering: the documented parameters do not include a time window for `list-items`. List recent items and filter locally on `first_seen` or `last_seen`.
- `get-top-items` only covers the last 24 hours.
- Occurrence counts are cumulative since the item was created.
- `list-occurrences` returns 3 items by default: it is a sample, not a count.
- `get-item-details` and `list-occurrences` truncate by `max_tokens` (default 20000): the response may be cut.

## Verification

Ask Claude Code: "List my Rollbar projects." A list of project names confirms the token and the server.
