---
name: today
description: Create or refresh today's daily note and the reading page cockpit/today.md (priorities, agenda, overdue tasks, triage count). Use when the user says /today, "start my day", "daily note", "what should I focus on today" or "plan my day".
argument-hint: "[YYYY-MM-DD | refresh]"
---

# Today

Target note: `journal/daily/<YYYY>/<YYYY-MM-DD>.md`. Reading page: `cockpit/today.md`, written only by this skill (other skills and routines never edit it). Tasks are never copied from one day to another: a task lives once in its own note and the cockpit aggregates them.

## Steps

1. Get the date with `date +%F` (or use the argument) and the year with `date +%Y`. Create the year folder if it is missing.
2. If the daily note exists, read it and summarise it in one line. Otherwise build it from `_system/templates/daily.md`: replace the Obsidian `{{date:...}}` placeholders with real values, the heading is the weekday and full date.
3. Collect open tasks: `grep -rn "^- \[ \]" work team` (never `journal/daily/`). Keep those due today or earlier, overdue first, as the candidates for the day. Count the tasks that carry `#to-triage`.
4. Collect priority signals from notes with `status: active`:
   - `work/` notes of type `project` or `workstream` with `rag: red|amber` or a non-empty `blocker`;
   - `work/risks/` notes with `risk_status: open` and `severity: high|critical`;
   - `work/decisions/` notes with `decision_status: to-decide` and a near `due`;
   - `team/` notes with `rag: red|amber`.
5. Pick up to 3 priorities among items that are overdue, due soon, blocked or red. Each one ends with a wikilink.
6. Agenda: read today's events with the calendar tool configured for this vault (e.g. a Google Calendar MCP server), in `{{ct.timezone}}`, skipping declined events. If no calendar tool is configured, say so in one line and leave the agenda table with a single row "No calendar configured".
   - Link each event to its note: {{ct.a_team}} ritual to the {{ct.team}} note, a one-to-one to the {{ct.person}} note in `team/`, anything matching a note in `work/` to that note.
   - Add a preparation hint only when an open task or decision links to that event.
   - Day progress: get the current time with `date "+%H:%M"` ({{ct.timezone}}) and give each event a state. `end <= now` → past; `start <= now < end` → in progress; otherwise upcoming. All-day events have no state and are never greyed. Only when the target date is today; for another date, leave every state empty.
7. Write `cockpit/today.md`: replace the whole body, keep the frontmatter and update its date. In the daily note, write the priorities under `## 🎯 Focus` and the agenda under `## 📅 Agenda`; leave the other sections as they are.
8. Refresh mode (`/today refresh`, today only): re-read only the calendar, recompute the states, and rewrite the agenda table in `cockpit/today.md` and in the daily note, plus the `🕐 Updated` line. Do not touch priorities, overdue tasks, the triage count or the other sections. If today's pages do not exist yet, run the full steps instead.
9. Show the user the priorities and the overdue tasks in 5 to 10 lines, then ask: "Anything to add?"

## Rules

- Never add a task that already lives in another note.
- A task created here is only for today, in the daily note under `## ✅ Tasks`. Anything proposed by this skill carries `#to-triage`.
- Never write `rag`: propose a change to the user instead.

## Presentation

Follow section 6 (page style) of the vault `CLAUDE.md`. Two pages, same content.

**`cockpit/today.md`** (body after the frontmatter):
- right under the title: `🕐 Updated on DD/MM/YYYY at HH:MM`, real time from `date "+%d/%m/%Y at %H:%M"`;
- `> [!summary] Priorities of the day`: 3 numbered lines, each ending with a wikilink;
- `## 📅 Agenda`: table `| | Time | Meeting | Topic / preparation |`, topics and people as wikilinks. First column by state: past `✅`, in progress `▶`, upcoming and all-day empty. A past row wraps every cell's text in `<span style="opacity:.45">…</span>` (inline style, so it also works in the `![[today]]` embed); an in-progress row puts the meeting title in bold. No next-meeting marker. The grey is only exact at the time of the last update, hence the `🕐 Updated` line;
- `## 🔴 Overdue`: table `| Task | Note | Due |`, 5 rows max;
- one line `📥 N tasks to triage`, with a link to the page that lists `#to-triage` tasks.

**Daily note** (from `_system/templates/daily.md`, no summary callout: it is a short page): `## 📅 Agenda` (same table, same states), `## 🎯 Focus` (the same priorities, numbered), `## ✅ Tasks` (today-only tasks), `## 📝 Notes`, `## ⚖️ Decisions`, `## 🚨 Blockers`, `## 🌙 End of day`. Keep these headings, with their icons.
