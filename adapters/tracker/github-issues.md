# GitHub Issues

Capability: `tracker`. Official documentation: https://cli.github.com/manual/gh_issue_list (GitHub CLI), https://cli.github.com/manual/gh_auth_login (authentication) and https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api (REST pagination).

## Setup

Install the GitHub CLI (`gh`) following https://cli.github.com, then `gh auth login`. Check the official documentation for installation on your platform.

## Authentication and least-privilege scopes

`gh auth login` is interactive. For unattended jobs the documentation recommends environment variables, and favouring `GH_TOKEN` for a fine-grained personal access token. Create a fine-grained token limited to the repositories you read, with read-only access to issues and metadata (check the GitHub documentation for the exact permission names). The documented minimum scopes for a classic token passed with `--with-token` are `repo`, `read:org` and `gist`: this is broader than needed, prefer a fine-grained token.

The CLI has write commands, so the manifest sets `read_only` to false with a mitigation: the read-only fine-grained token is the control. Claude Code prefix permission rules need a wildcard, so the manifest pre-allows nothing (`permissions_allow` is empty, never a wildcard) and denies the documented mutating commands; review read commands as they run.

## Commands or tools to call

`gh issue list` flags documented: `--limit` / `-L` (default 30), `--state` / `-s` (open, closed, all; default open), `--search` / `-S`, `--assignee` / `-a`, `--label` / `-l`, `--milestone` / `-m`, `--json <fields>`.

| Query | Command idea |
|---|---|
| `current_sprint` | `gh issue list --milestone "NAME" --state all --limit 500 --json ...` (milestone as sprint) |
| `blocked` | `gh issue list --label blocked --limit 200 --json ...` |
| `unassigned` | `gh issue list --search "no:assignee" --limit 200 --json ...` |
| `resolved_in_window` | `gh issue list --state closed --search "closed:START..END" --limit 500 --json ...` |

GitHub Issues has no native sprint: teams use milestones, labels or a Projects iteration field. For Projects iteration fields check the official documentation.

## Field mapping to the contract

Valid `--json` field names are listed in the manual page: check it. Typical mapping: `number` to key, `title`, `state` (open or closed) to `status_category` (todo/in_progress vs done; "in progress" needs a label or a Project status), `assignees`, `milestone` to sprint, `labels`, `updatedAt`, `url`.

## Pitfalls

- `gh issue list` returns only **30** items by default: always pass `--limit`, and if the number returned equals the limit, treat it as truncated ("at least N (truncated)").
- The default state is open: use `--state all` or `closed` when counting resolved work.
- The REST API pages with a `Link` header (`rel="next"`) and a maximum `per_page` of 100 for most endpoints: stop when no `next` link remains.
- Pull requests are issues in the REST API: filter them out when counting issues.
- Issue numbers and PR numbers are the join keys with the code adapter ("Fixes #123").
- Date-only qualifiers mean midnight: use an exclusive upper bound.

## Verification

Run the command in the manifest, then a `--state all --limit` query on a repository whose count you know and compare.
