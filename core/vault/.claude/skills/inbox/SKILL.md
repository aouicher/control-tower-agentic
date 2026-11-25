---
name: inbox
description: Empty the _inbox folder - for each captured note, propose where it belongs (project, workstream, person, decision, risk, library, archive), the properties to set and the tasks it contains, then file it after the user agrees. Use when the user says /inbox, "triage my inbox", "sort my inbox", "clean the inbox" or "what is in my inbox".
argument-hint: "[note name, optional]"
---

# Inbox

`_inbox/` is the default folder for every new note: quick captures, pasted links, ideas, notes made on the phone. This skill empties it. Nothing is filed without the user's agreement.

## Steps

1. List the notes in `_inbox/` (oldest first, ignore `.gitkeep`). If it is empty, say "Inbox is empty" and stop. With an argument, handle only that note.
2. Read each note. For each, decide the most likely outcome:
   - **merge** into an existing note (a project, {{ct.workstream}}, {{ct.person}} or decision it clearly belongs to: search the vault for its keywords first);
   - **file** as a new typed note (project, {{ct.workstream}}, decision, {{ct.risk}}, resource) in its folder, from its template in `_system/templates/`;
   - **library** for reference material (links, articles, research): `library/`, type `resource`;
   - **task only**: the note is just an action. It becomes one task in the note it belongs to;
   - **archive** if it is no longer useful: move it to `_system/archive/` (never delete).
3. Show one table for the whole inbox, before changing anything:

   | Note | Proposal | Destination | Tasks found |
   |---|---|---|---|
   | `call vendor.md` | task only | `work/projects/spring-launch.md` | Call the vendor about the delay |

4. Ask the user to confirm or correct, all at once ("ok", "ok except 2: library"). Do only what was agreed.
5. Apply:
   - merging: append the content under a dated heading of the target note (`### From the inbox, YYYY-MM-DD`), then move the inbox note to `_system/archive/`;
   - filing: create the note from the template with a quoted `title`, today's `date`, its `type`, `status: active` (or `draft` when it is only an idea), and the properties the user gave; keep the captured text under `## 📝 Notes`; then remove the inbox note;
   - tasks: write each task once, in the note it belongs to, as `- [ ] text @{{ct.owner_handle}}` with a `📅 YYYY-MM-DD` only if a date was stated. Tasks the user confirmed here are real tasks: no `#to-triage`;
   - links: wikilinks only to notes that exist.
6. Reply with what moved where (one line per note) and the number of notes left in `_inbox/`.

## Rules

- Never delete a note: archive it.
- Never invent a date, an owner or a status the note does not state; ask or leave it empty.
- A task lives in exactly one note. If the same action already exists somewhere, link it instead of copying it.
- Quote free-text frontmatter values (`title: "Call: vendor #2"`).
