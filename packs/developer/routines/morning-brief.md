# Routine: morning brief

Paste into a claude.ai cloud routine. Suggested schedule: weekdays at 08:45 in your timezone. Requires the `code` connector; `tracker` and `calendar` are optional.

---

You run unattended: never ask, never wait. Read-only on every external system. Write in English. Reply with a brief to read in under a minute; write nothing unless the vault repository is attached.

1. Pull requests waiting for my review and my open pull requests with review and CI state. List commands return a default page (30 for the GitHub CLI `gh pr list`): always pass an explicit limit of 100, and write "at least N (truncated)" if it is reached.
2. If a tracker connector exists: tickets assigned to me, open, by priority. Trackers return at most 100 items per page: paginate or write "at least N (truncated)".
3. If a calendar connector exists: today's events, skipping declined ones.
4. Output, max 15 lines: first the 3 things to do first, then a table of pull requests to review, then my blocked items, then today's meetings.
5. If the vault repository is attached, also save it as `journal/reports/dev-morning-YYYY-MM-DD.md` with the page style of `CLAUDE.md`. Any task proposed carries `#to-triage`; you cannot check the vault for duplicates, so propose at most 3.
6. Never include secrets or customer data.
