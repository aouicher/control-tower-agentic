# Developer pack

For individual software developers. It turns the neutral control tower into a daily cockpit for code work: what to review, what you shipped, what is blocking you, and what you learned while debugging.

## What it gives

| Piece | What it does |
|---|---|
| `standup` skill | Prepares the daily standup from git history and closed tickets: done, plan, {{ct.risks}} |
| `review-queue` skill | Pull requests waiting for your review, your open pull requests with review and CI state, stale ones |
| `worklog` skill | Appends a dated entry (decision, finding, link) to today's daily note |
| `debug-journal` skill | Turns a debugging session into a note in `library/` |
| Templates | `debug-journal`, `pull-request-notes`, `spike` |
| Dashboard | `my-pull-requests` (reads note properties) |
| Cockpit page | `cockpit/dev-today.md` |
| Jobs | `morning-prs` (08:30 Mon-Fri), `weekly-wrap` (Friday 16:30) |
| Routines | `daily-note`, `weekly-review`, `morning-brief` for claude.ai cloud routines |

Vocabulary: team, epic, blocker, teammate.

## Capabilities

- Required: `code` (pull requests).
- Optional: `tracker` (tickets), `errors` (error tracking), `calendar`.

Jobs are read-only on every external system and write only inside the vault.

## First week

1. **Day 1.** Install, connect `code`, open `cockpit/dev-today.md`. Run `/worklog` once to see the daily note fill up.
2. **Day 2.** Run `/standup` before your standup. Correct it, then keep what is useful.
3. **Day 3.** Run `/review-queue`. Accept or drop the `#to-triage` tasks it proposes.
4. **Day 4.** After your next bug hunt, run `/debug-journal` and read the note it creates.
5. **Day 5.** Enable the `morning-prs` and `weekly-wrap` jobs and read the Friday wrap.

Rules for notes: no secrets, tokens or customer data, ever. See `.claude/rules/developer.md` in the vault.
