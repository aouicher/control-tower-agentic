# Asana

Capability: `tracker`. Official documentation: https://developers.asana.com/docs/using-asanas-mcp-server, https://developers.asana.com/docs/connecting-mcp-clients-to-asanas-v2-server (Claude Code setup) and https://developers.asana.com/docs/pagination (API pagination).

## Setup

Official server: `https://mcp.asana.com/v2/mcp`. The client setup page documents for Claude Code:

```
claude mcp add --scope project --transport http --client-id YOUR_CLIENT_ID --client-secret --callback-port 8080 asana https://mcp.asana.com/v2/mcp
```

Leave the secret value empty: Claude Code prompts for it and stores it in the system keychain, per the page. The app's redirect URL must be exactly `http://localhost:8080/callback`. A client id and secret come from an app you create (see the developer integration guide linked from the page).

## Authentication and least-privilege scopes

OAuth with your Asana account. The documentation does **not** describe a read-only mode or scopes for the MCP server. Least privilege therefore comes from (a) a user with read-only access to the needed projects, and (b) Claude Code permissions that allow only read tools: run `tools/list` after connecting (the documentation says to do this) and allow the read tools by exact name. The manifest keeps `permissions_allow` empty on purpose (list the read-only tools of your MCP server after reviewing it; never use a wildcard) and `permissions_deny` empty because mutating tool names are not verified in the documentation.

Because no read-only mode is documented, the manifest sets `read_only` to false with a `read_only_mitigation` (view-only account).

## Commands or tools to call

The documentation does not list tool names; use `tools/list`. Needed reads: tasks of a project, by assignee, completion state and completion date, with custom fields.

The API paginates with `limit` (1 to 100) and an `offset` token returned in `next_page`; when `next_page` is null there are no more pages. Offset tokens expire. Unpaginated requests can be truncated at about 1,000 objects: always set `limit`. The audit-log endpoint can still return `next_page` when nothing remains: check for empty `data`.

## Field mapping to the contract

| Contract | Asana (check the API reference for exact names) |
|---|---|
| `key` | task gid |
| `title` | name |
| `status` | section name or a status custom field |
| `status_category` | `completed` true means done; otherwise todo or in_progress from the section or custom field |
| `assignee` | assignee name |
| `sprint` | no native sprint: a section, a custom field or a dedicated project (check how the team models it) |
| `labels_or_type` | tags, custom field |
| `priority` | custom field |
| `updated` | modified at |
| `url` | task permalink |

## Pitfalls

- Set `limit` on every list call and follow `next_page` until it is null before counting.
- Asana has no built-in sprint: ask how the team models it before answering sprint questions, never use "updated in the last N days" as a substitute.
- "Blocked" is usually a custom field or section: not always a technical blocker.
- Tasks can belong to several projects: de-duplicate by task id.
- Date-only values (due dates) mean midnight: use an exclusive upper bound.

## Verification

Connect, list the tasks of one project with `limit=100`, follow `next_page` to the end, compare the count with the project view.
