---
name: time-review
description: Weekly breakdown of the calendar by category with a short reading, saved as a report. Use when the user says /time-review, "where did my time go", "time breakdown" or "how did I spend my week".
argument-hint: "[YYYY-Www]"
---

# Time review

## Steps

If the prompt has a `## Run context`, take dates and times from it and do not run `date`; otherwise get them as below.

1. Get the ISO week with `date +%G-W%V` (or use the argument) and the Monday to Sunday dates. Default: the current week up to today; on a Monday, the week that just ended.
2. Read the calendar with the calendar tool configured for this vault (e.g. a Google Calendar MCP server), primary calendar, timezone `{{ct.timezone}}`, accepted or no-response events only; skip all-day and declined events. If no calendar tool is configured, say so, stop, and suggest configuring one. Write nothing.
3. Classify each event into ONE category from its title and attendees.
   - If `library/calendar-categories.md` exists, it defines the categories and overrides the defaults.
   - Defaults: **Deep work** (focus blocks), **{{ct.Team}}** (rituals and {{ct.team}} meetings), **Stakeholders** (leadership, cross-functional, steering), **External** (customers, vendors, partners, regulators), **1-1s** (one-to-ones, interviews), **Other** (unclassified: list the titles).
   - If the file does not exist, show the defaults once and offer to save the user's corrected version as `library/calendar-categories.md` from `_system/templates/resource.md`.
4. Write `journal/reports/time-<YYYY-Www>.md` from `_system/templates/report.md` (`date: <today, YYYY-MM-DD>`, `type: report`, `report_kind: time`), named after the week it reports on.
5. Propose at most 2 adjustments as `- [ ] ... @{{ct.owner_handle}} #to-triage` (for example "block 2 h of focus on Thursday"). Never create or edit calendar events.
6. Reply in 5 lines: total hours, the split, the main observation.

## Presentation

Follow section 6 (page style) of the vault `CLAUDE.md`. Layout:
- `# ⏱️ Time <YYYY-Www>`, then `🕐 Generated on DD/MM/YYYY at HH:MM` (real time from `date "+%d/%m/%Y at %H:%M"`);
- `> [!summary] Summary` with a status icon 🟢 🟠 🔴: total meeting hours, share of the week, the main observation (3 bullets max);
- `## 📊 Breakdown`: table `| Category | Hours | % | Change |`, change versus the previous `journal/reports/time-*` when present (▲ ▼ ▬);
- `## 📅 By day`: table day by category, flag days with more than 6 h of meetings with 🔴;
- `## 🩺 Observations`: 3 bullets;
- `## ✅ Proposed actions`;
- `## 📎 Annexes`: folded callout `> [!note]- Event details` listing events by category, every line prefixed with `> `.

Event titles and ids stay in the annex, never in the main body.
