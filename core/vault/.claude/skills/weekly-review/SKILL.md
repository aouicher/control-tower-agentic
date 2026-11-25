---
name: weekly-review
description: Write the weekly review from the tasks done and open in work/ and team/, with trends, signals, top 3 for next week and a duplicate-task check. Use when the user says /weekly-review, "weekly review", "how was my week" or "review my week".
argument-hint: "[YYYY-Www]"
---

# Weekly review

The review depends on `work/` and `team/`, not on daily notes: daily notes are optional extra context.

## Steps

1. Get the ISO week with `date +%G-W%V` (or use the argument) and the Monday to Sunday dates.
2. Read this week's daily notes in `journal/daily/<YYYY>/` when they exist, for context only. If none exist, continue and say so in one line. Never read tasks from older daily notes: they are stale.
3. Extract from `work/` and `team/`:
   - **Done**: `- [x]` tasks whose `✅ YYYY-MM-DD` date (added by the Tasks plugin) falls inside Monday to Sunday, grouped by note.
   - **Not done (carried over)**: open `- [ ]` tasks with a due date before the end of the week, overdue first, grouped by note.
   - **Trends and signals**: {{ct.workstreams}} and projects that are red or blocked, {{ct.teams}} with `rag: amber|red`, open {{ct.risks}} with high severity, recurring blockers, tasks carried over several weeks, notes that absorbed most of the work, active projects with no activity. Use the latest report in `journal/reports/` when one exists.
4. **Duplicates to tidy**: run `python3 _system/tools/duplicate-tasks.py` (read-only). For each group, decide whether it is a real duplicate (same action in two notes) or a false positive (same wording, different subject).
   - For real duplicates, PROPOSE which note keeps the task (the project, area, {{ct.team}} or {{ct.risk}} note, never a report or a meeting note) and which copies become `- [-]` with a pointer.
   - Do NOT change any task without the user's confirmation. If the script is missing, say so and skip.
5. Write `journal/daily/<YYYY>/<YYYY-Www>-weekly.md` from `_system/templates/weekly.md`, with wikilinks to the daily notes used.
6. Propose **Next week: top 3** from open items, blockers and active projects. Ask the user for wins and lessons and add the answer under `## 🏆 Wins and lessons`.
7. Anything proposed as a new task carries `#to-triage`; assign to `@{{ct.owner_handle}}` only if the user confirms.

## Presentation

Follow section 6 (page style) of the vault `CLAUDE.md`. Use `_system/templates/weekly.md`:
- under the title: `🕐 Generated on DD/MM/YYYY at HH:MM` (real time from `date "+%d/%m/%Y at %H:%M"`);
- `> [!summary] Summary`: done count, carried-over count, the main signal (3 bullets max);
- `## ✅ Done`: grouped by note, one line each, in a folded callout `> [!note]- Details` when more than 8 lines;
- `## 🚧 Not done (carried over)`: table `| Task | Note | Due | Since |`, overdue first;
- `## 🩺 Trends and signals`: 5 bullets max, red or blocked first, with status icons 🟢 🟠 🔴 ⚪;
- `## 🏆 Wins and lessons`;
- `## 🎯 Next week: top 3`;
- `## 🔁 Duplicates to tidy`: table `| Task | Notes | Proposal |`, or one line "No duplicates".
