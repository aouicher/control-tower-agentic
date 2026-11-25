# Contract: errors (error tracking)

## Purpose

Lets jobs and skills answer "what is failing in my applications, what is new, what is still active" from any error tracker (Rollbar, Sentry, ...). The job never talks to the tool directly: it follows this contract, and the adapter file explains how to obtain each field.

## Inputs the job gives

| Input | Meaning |
|---|---|
| `projects` | Project names or slugs to inspect (all accessible projects when empty) |
| `window_start`, `window_end` | Absolute dates with timezone (never "last week" alone) |
| `environments` | Environments to keep, for example `production` |
| `mode` | `new` (first_seen in the window) or `active` (last_seen in the window) |

## Outputs it expects (fields)

One record per item, plus a header stating the window and the caps reached.

| Field | Meaning |
|---|---|
| `project` | Project name or slug |
| `item_id` | Stable id of the error group (not of a single occurrence) |
| `title` | Error message or title, truncated to one line |
| `level` | `critical`, `error`, `warning`, `info`, `debug` (map tool values to these) |
| `environment` | Environment of the item, or `unknown` |
| `first_seen` | ISO 8601 timestamp |
| `last_seen` | ISO 8601 timestamp |
| `occurrences` | Cumulative count shown by the tool, labelled as cumulative |
| `status` | `active`, `resolved`, `muted` or `unknown` |
| `url` | Link to the item in the tool |

## Pagination and truncation

- Error trackers often have no server-side time filter. List the most recent items, then keep locally those whose `first_seen` (mode `new`) or `last_seen` (mode `active`) falls in the window.
- Counters shown by the tool are cumulative since the item was created, not per window. Never present them as "errors this week".
- A list is often capped (for example 20 to 50 items). When the cap is reached, report "at least N items" and say the list may be incomplete. Page further or narrow the filters when the tool allows it.
- Sort order matters: state which one was used (last seen, first seen, occurrences).

## Pitfalls

- A single noisy item can hide many new ones: report new items separately from active ones.
- Items from non-production environments must be filtered or labelled.
- Resolved items can reappear: compare `status` and `last_seen`.
- Do not paste stack traces, request bodies or user identifiers into the vault: they can contain personal data. Keep the id, title, counts and link.

## Read-only guarantees

Use read-only credentials. Never call tools that resolve, mute, assign, delete or comment on items. If a token has write scope, do not use the write tools anyway.

Some tools have no read-only mode (see `read_only` and `read_only_mitigation` in the adapter manifest). For those, the guarantee comes from the mitigation (view-only account, restricted role or token, denied write tools), not from the tool: apply it before use and never call a write tool.

## Failure handling

- Authentication or permission error: stop, report "errors: no access" and the tool name. Never fall back to guessing.
- Empty result: say how many projects and which window were queried, so an empty list is distinguishable from a misconfiguration.
- Cap reached or tool truncated the response: report it as a coverage gap in the output.
