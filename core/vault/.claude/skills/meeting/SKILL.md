---
name: meeting
description: Turn pasted notes, a transcript or calendar notes into a structured meeting note, route each action once into the note it belongs to after confirmation, and file decisions. Use when the user says /meeting, "meeting notes", "write up my meeting", "file this meeting" or pastes meeting notes.
argument-hint: "<type> [date], e.g. 1-1 alex, weekly-sync, steering"
---

# Meeting

Output: ONE note from `_system/templates/meeting.md`: `journal/meetings/<type>/<YYYY-MM-DD>-<type>.md`, or for a one-to-one `journal/meetings/1-1/<person-slug>/<YYYY-MM-DD>-1-1-<person-slug>.md` (one folder per {{ct.person}}). Tasks never stay in the meeting note: they go to the note they belong to.

## 1. Identify the meeting

If the prompt has a `## Run context`, take dates and times from it and do not run `date`; otherwise get them as below.

- Type: a recurring-meeting slug. The existing subfolders of `journal/meetings/` are the reference; create a new one only when none fits.
- One-to-one: `<person-slug>` is the file name of the {{ct.person}}'s note in `team/`; link it as a wikilink. Create the folder if missing. The file name keeps the person and the date so wikilinks stay unique.
- Date: given, else today (`date +%F`). Attendees and title: read the event with the calendar tool configured for this vault (e.g. a Google Calendar MCP server, timezone `{{ct.timezone}}`). If no calendar is configured, ask only for what is missing.

## 2. Get the content

In this order: what the user pasted or said; notes or a transcript attached to the calendar event, if a tool gives access to them; a page the user points to. Read it fully. If nothing is available, ask for the raw notes (one question).

## 3. Write the note

Frontmatter, every free-text value in double quotes: `title: "Meeting <type> <date>"`, `date`, `tags: [meeting, <type>]`, `type: meeting`, `meeting_type: <type>`, `status: active`.

Body, following the template:
- **Participants**: wikilinks to notes in `team/` when they exist, plain names otherwise.
- **Context**: one or two lines plus wikilinks to the daily note and to the {{ct.team}}, {{ct.workstream}}, project, area or {{ct.risk}} notes discussed. When the meeting changes the state of {{ct.a_workstream}}, update its `blocker`, `next_step` (double-quoted) and its `## 🩺 Health` table. Never write `rag`: propose it to the user.
- **Notes**: by topic, short bullets, exact numbers and dates, no transcript dump.
- **Decisions**: one line each, with the decider when known.
- **Actions**: only a link to where each action now lives.

If the file already exists, append a dated section instead of replacing it.

## 4. Route the actions (ask first)

List the proposed actions in a table (action, owner, due date, destination note, tag) and ask the user to confirm or correct, in ONE question. Only then write each action ONCE, as `- [ ] <action> @<owner> 📅 <date>`, under `## Tasks` of its destination:
- a project, area or {{ct.risk}} goes to its note in `work/projects/`, `work/areas/` or `work/risks/`; {{ct.a_workstream}} subject goes to its note in `work/workstreams/<group>/`; a general {{ct.team}} point goes to the {{ct.team}} note; a point to raise with {{ct.a_person}} goes to their note in `team/`;
- waiting on someone else: add `#waiting`; promised by the user: add `#committed`; hard or external date: add `#deadline`;
- the user's own actions use `@{{ct.owner_handle}}`;
- no obvious home: ask which note. Never create a project note for a single task.

Actions inferred by the skill rather than stated in the meeting carry `#to-triage`.

## 5. Decisions, one-to-ones and links

- A pending or important decision: create `work/decisions/<slug>.md` from `_system/templates/decision.md` (`decision_status: to-decide | proposed | made`) and link it from the meeting note.
- One-to-one: set `last_one_to_one: <date>` in the {{ct.person}}'s note, update `signal` (double-quoted), and add at most 3 factual lines (workload, blockers, mood as stated by them). Never a performance judgement.
- Add a line `Meeting: [[<meeting note>]]` under `## 📝 Notes` of the daily note and of the notes really discussed.

## 6. Confidentiality

Never write secrets, credentials, customers' personal data, or the content of regulatory submissions, NDA or M&A material. Use neutral wording ("ongoing compliance topic") and say what was left out. Keep sensitive one-to-one content factual and minimal.

## 7. Reply

5 to 8 lines: the note path, the decisions, the actions routed with their destination, anything that could not be placed.

## Presentation

Follow section 6 (page style) of the vault `CLAUDE.md`, using `_system/templates/meeting.md`:
- `> [!summary] Summary`: purpose, decisions, actions, one line each;
- the template's two-row table for Participants and Context;
- `## 📝 Notes` with one `###` per topic (3 to 6 short bullets);
- `## ⚖️ Decisions`: table `| Decision | Decider | Link |`;
- `## ✅ Actions`: table `| Action | Owner | Due | Where it lives |`, the last column a wikilink;
- raw material only in a folded callout `> [!note]- Raw notes`, every line prefixed with `> `.
