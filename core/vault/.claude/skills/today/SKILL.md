---
name: today
description: Create or refresh today's daily note and the reading page cockpit/today.md (priorities, agenda, overdue tasks, triage count). Use when the user says /today, "start my day", "daily note", "what should I focus on today" or "plan my day".
argument-hint: "[YYYY-MM-DD]"
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
7. Write `cockpit/today.md`: replace the whole body, keep the frontmatter and update its date. In the daily note, write the priorities under `## 🎯 Focus` and the agenda under `## 📅 Agenda`; leave the other sections as they are.
8. Show the user the priorities and the overdue tasks in 5 to 10 lines, then ask: "Anything to add?"

## Rules

- Never add a task that already lives in another note.
- A task created here is only for today, in the daily note under `## ✅ Tasks`. Anything proposed by this skill carries `#to-triage`.
- Never write `rag`: propose a change to the user instead.

## Presentation

Follow section 6 (page style) of the vault `CLAUDE.md`. Two pages, same content.

**`cockpit/today.md`** (body after the frontmatter):
- right under the title: `🕐 Updated on DD/MM/YYYY at HH:MM`, real time from `date "+%d/%m/%Y at %H:%M"`;
- `> [!summary] Priorities of the day`: 3 numbered lines, each ending with a wikilink;
- `## 📅 Agenda`: table `| Time | Meeting | Topic / preparation |`, topics and people as wikilinks;
- `## 🔴 Overdue`: table `| Task | Note | Due |`, 5 rows max;
- one line `📥 N tasks to triage`, with a link to the page that lists `#to-triage` tasks.

**Daily note** (from `_system/templates/daily.md`, no summary callout: it is a short page): `## 📅 Agenda` (same table), `## 🎯 Focus` (the same priorities, numbered), `## ✅ Tasks` (today-only tasks), `## 📝 Notes`, `## ⚖️ Decisions`, `## 🚨 Blockers`, `## 🌙 End of day`. Keep these headings, with their icons.
