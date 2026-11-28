# Concepts

## The vault

```
cockpit.md         your entry page: what needs attention now
cockpit/           today, my work, commitments, overview
_inbox/            default folder for new notes: capture now, sort with /inbox
work/projects/     time-boxed outcomes
work/areas/        ongoing responsibilities
work/workstreams/  streams of work inside projects (campaigns in the marketing pack)
work/decisions/    decision records
work/risks/        risk register
team/              teams and people
journal/daily/     daily notes
journal/meetings/  meeting notes, one folder per person or group
journal/reports/   reports written by skills and jobs
library/           reference material and research
_system/           templates, dashboards, tools, archive, attachments
.claude/skills/    the vault's Claude Code skills
CLAUDE.md          rules Claude follows in this vault
```

Packs can add folders and note types but never edit `CLAUDE.md`; their rules live in `.claude/rules/<pack>.md`.

## Typed notes

Every note has YAML properties. Dashboards (`_system/dashboards/*.base`, Obsidian Bases) query them: status, owner, team, risk level, dates. Free text values with `: ` or ` #` must be double-quoted or Obsidian shows "Invalid properties"; `doctor.py` warns about it.

## Tasks

- One task lives in exactly one note, as `- [ ] task @owner 📅 YYYY-MM-DD`.
- Queries (Tasks plugin) show them everywhere without copying them.
- Jobs and skills only *propose* tasks, tagged `#to-triage`. Triage in the cockpit, then remove the tag.

## Vocabulary

The core uses neutral words. Each pack can rename the shown words (for example workstream becomes campaign, person becomes teammate) in `vocabulary.json`. Folder names, property values and tags stay stable.

## The vault's language

Notes and reports are written in the answers' `language`. The vault's templates, dashboards and pages are translated into it once, by Claude, at install (`install.py --strings` lists their texts; `translation_file` in the answers brings the translation). The translation changes words only: links, tokens, tags, handles, code, queries, properties and folder names stay as they are, and `installer/translate.py` refuses one that changes them or adds a table cell, a heading, a quote, a list, code, a link, HTML or a comment. It is kept in `.control-tower/translation.json` and put back every time the installer writes those files, so an update keeps it and finds nothing edited; the texts a new version adds are translated from `/control-tower` (`configure.py translate --missing`, then `--file`). Skills and `CLAUDE.md` stay in English, and so does every heading a skill, a rule or a report names (`## ✅ Tasks`), so they still find it; a translation is kept only for texts the vault has.

## Page style

Short pages stay plain. Long pages open with a summary callout, use tables and icons, fold annexes in `> [!note]-` blocks and end with a `🕐 Generated on` line when machine-written.

## Counting rules for reports

Reports state exact numbers or say "at least N (truncated)". Queries always pass an explicit limit, and zero records scanned is reported as a coverage gap, not as "nothing found".

## Skills, jobs and routines

| Kind | Runs | Where | Use for |
|---|---|---|---|
| Skill | when you type `/name` | your Claude Code session in the vault | interactive work |
| Job | on a schedule on your machine | `claude -p` with a locked-down settings file | recurring reports |
| Routine | on a schedule in the cloud | claude.ai routines, prompt pasted by you | when your machine is off |
