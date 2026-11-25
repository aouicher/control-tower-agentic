# Jira

Capability: `tracker`. Official documentation: https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/ (Atlassian Rovo MCP server) and https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/ (Jira Cloud REST API, issue search).

## Setup

The getting-started page documents, for Claude Code:

```
claude mcp add --scope user --transport http atlassian https://mcp.atlassian.com/v2/mcp
```

then run `/mcp` in a Claude Code session to authenticate. The page mentions a v1 URL that will start using v2 tools on a date it states: check the page for the current URL. If you use Claude Code's sandbox, the Atlassian documentation lists network domains to allow: check the official documentation.

## Authentication and least-privilege scopes

OAuth 2.1 is the default. API-token authentication is optional and depends on an administrator setting. The pages do **not** describe a read-only mode or configurable scopes: actions run with the signed-in user's permissions. Least privilege therefore comes from (a) using an account or service account with read-only project permissions, and (b) allowing only read tools in Claude Code permissions. After connecting, list the tools (`/mcp`) and allow the read ones by exact name; the manifest keeps `permissions_allow` empty on purpose (list the read-only tools of your MCP server after reviewing it; never use a wildcard) and `permissions_deny` empty because mutating tool names are not verified in the documentation. Check the official documentation for the administrator controls on the server.

Because no read-only mode is documented, the manifest sets `read_only` to false with a `read_only_mitigation` (view-only account).

## Commands or tools to call

The v2 server describes a `discovery` and `execute` method pattern, and a `?tools=all` option to expose a flat list: check the official documentation for the current tool names. Use a JQL search for the standard queries. Typical JQL (check the JQL documentation for exact function names in your site):

| Query | JQL idea |
|---|---|
| `current_sprint` | `project = X AND sprint in openSprints()` |
| `blocked` | `project = X AND statusCategory != Done AND (status = Blocked OR labels = blocked)` |
| `unassigned` | `project = X AND assignee is EMPTY AND statusCategory != Done` |
| `resolved_in_window` | `project = X AND resolved >= "start" AND resolved < "end"` |

For the REST API, the enhanced search endpoint is `/rest/api/3/search/jql`, paged with `nextPageToken`. Atlassian's developer community states that this endpoint does not return a total, does not allow random page access, and returns only the issue id unless `fields` is requested. Check the REST reference for the current page-size cap and end-of-results signal, and prefer "no `nextPageToken`" as the stop condition.

## Field mapping to the contract

| Contract | Jira |
|---|---|
| `key` | issue key |
| `title` | `summary` |
| `status` | `status.name` |
| `status_category` | `status.statusCategory` (To Do, In Progress, Done) |
| `assignee` | `assignee.displayName` |
| `sprint` | sprint field of the issue (a custom field on most sites) |
| `labels_or_type` | `labels`, `issuetype.name` |
| `priority` | `priority.name` |
| `updated` | `updated` |
| `url` | site base URL + `/browse/` + key |

## Pitfalls

- Search pages are capped: paginate to the end before counting; never use the page size as a total.
- Sprint status = current sprint, not "updated in the last N days".
- A status named Blocked is not always technical: read the comment or link.
- `resolved` and `updated` with a bare date mean midnight: use an exclusive upper bound.
- JQL results depend on the signed-in user's permissions: a missing issue may be a permission gap.

## Verification

Authenticate, run the `current_sprint` query for one project, paginate to the end, and compare the count with the board in the Jira UI.
