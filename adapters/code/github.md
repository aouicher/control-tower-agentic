# GitHub

Capability: `code`. Official documentation: https://cli.github.com/manual/gh_pr_list (GitHub CLI), https://cli.github.com/manual/gh_release_list, https://cli.github.com/manual/gh_auth_login and, for the optional MCP server, https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp/set-up-the-github-mcp-server.

## Setup

Install the GitHub CLI (`gh`) from https://cli.github.com (check the official documentation for your platform), then `gh auth login`.

## Authentication and least-privilege scopes

Interactive login for a person; for unattended jobs the CLI documentation recommends environment variables and favouring `GH_TOKEN` for a fine-grained personal access token. Create a fine-grained token restricted to the needed repositories with read-only access to pull requests, contents metadata and releases (check the GitHub documentation for exact permission names). The documented minimum scopes for a classic token given with `--with-token` are `repo`, `read:org` and `gist`: broader than needed, so prefer a fine-grained token.

Optional MCP route: GitHub documents a remote server at `https://api.githubcopilot.com/mcp/` with OAuth or a token header, and toolsets such as `pull_requests`, `issues` and `repos`. The project documentation describes a read-only URL (`/readonly`) and an `X-MCP-Readonly: true` header for the remote server. Tool names were not verified here: if you use it, list the read-only tools after reviewing the server and allow them by exact name. The CLI is the default of this adapter.

The CLI has write commands, so the manifest sets `read_only` to false with a mitigation: the read-only fine-grained token is the control. Claude Code prefix permission rules need a wildcard, so the manifest pre-allows nothing (`permissions_allow` is empty, never a wildcard) and denies the documented mutating commands; review read commands as they run.

## Commands or tools to call

`gh pr list` documented flags: `--limit` / `-L` (default 30), `--state` / `-s` (open, closed, merged, all; default open), `--search` / `-S`, `--json <fields>`, `--author` / `-A`, `--base` / `-B`, `--label` / `-l`, `--draft` / `-d`, `--head` / `-H`. `gh release list`: `--limit` (default 30), `--order`, `--exclude-drafts`, `--exclude-pre-releases`, `--json` with fields `createdAt`, `isDraft`, `isLatest`, `isPrerelease`, `name`, `publishedAt`, `tagName`.

| Query | Command idea |
|---|---|
| `merged_in_window` | `gh pr list --state merged --search "merged:START..END" --limit 500 --json number,title,author,mergedAt,...` |
| `open_older_than` | `gh pr list --state open --limit 500 --json number,title,author,createdAt,isDraft,reviewDecision,...` then filter by age |
| `review_state` | same, using the review fields listed in the manual |
| `authors` | group the `merged_in_window` result by author |
| `releases_in_window` | `gh release list --exclude-drafts --limit 100 --json tagName,name,publishedAt,isPrerelease` then filter |

Valid `--json` field names are listed on each manual page: check them before use. Run one command per repository (`--repo OWNER/REPO`).

## Field mapping to the contract

| Contract | `gh pr list --json` (check the manual for exact names) |
|---|---|
| `number`, `title`, `url` | `number`, `title`, `url` |
| `author` | `author` |
| `state` | `state` |
| `created`, `updated`, `merged` | `createdAt`, `updatedAt`, `mergedAt` |
| `labels` | `labels` |
| `review_state` | review decision and reviews fields |
| release `tag`, `published` | `tagName`, `publishedAt` |

## Pitfalls

- `gh pr list` and `gh release list` return **30** items by default: always pass `--limit`; if the result length equals the limit, it is truncated.
- Search qualifiers with dates mean midnight: use an exclusive upper bound.
- The default state is open: use `--state merged` for shipped work.
- Bot authors inflate counts; report them separately.
- Join PRs to tracker issues by number or key found in titles and branch names.

## Verification

Run the manifest command, then a merged query on a repository where you know the weekly count and compare it.
