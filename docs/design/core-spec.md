# Core specification

This document is the contract for everything under `core/` and for the packs. Files in `core/vault/` are templates: the installer copies them into the user's vault and replaces the `{{ct.*}}` tokens.

## 1. Principles

1. **One task lives once.** A task is written in exactly one note (its project, area, team, workstream or risk). Dashboards aggregate; nothing is copied from day to day. Daily notes only hold tasks that are for today.
2. **Automations propose, the human decides.** Anything created by a job or an agent carries the tag `#to-triage`. The user accepts it (removes the tag), delegates it or drops it.
3. **Properties, not folders.** Facts (`status`, `rag`, `owner`, `due`, `blocker`, `next_step`) live in the note's frontmatter. Dashboards (Obsidian Bases) read them.
4. **Nothing is deleted.** Retired notes move to `_system/archive/`.
5. **Pages are readable.** See the page style below.

## 2. Folder layout (identical for every pack)

```
<vault>/
  CLAUDE.md                 rules for Claude (rendered from CLAUDE.md.tmpl)
  cockpit.md                the home page: live queries and embedded dashboards
  _inbox/                   quick capture, triaged on request
  cockpit/                  reading pages: today.md, my-work.md, commitments.md, overview.md
  work/
    projects/               things with an end date
    areas/                  ongoing responsibilities
    workstreams/<group>/    streams of work, one subfolder per team or channel
    decisions/              decisions to take or taken
    risks/                  incidents, risks, open problems
  team/                     team notes and people notes
  journal/
    daily/<YYYY>/           daily notes, weekly reviews
    meetings/<type>/        meeting notes (1-1s: one folder per person)
    reports/                generated reports
  library/                  references and research notes
  _system/
    templates/ dashboards/ tools/ archive/ attachments/
  .claude/skills/           the vault skills
```

Folder names never change with the vocabulary: only the words shown to the user do.

## 3. Note types and properties

Every note starts with YAML frontmatter. Free-text values are always wrapped in double quotes (a colon or ` #` inside an unquoted value breaks the properties panel). Several links in one property are a YAML list of quoted links.

Common: `title`, `date` (creation date), `tags`, `type`, `status` (`draft | active | archived`).

| `type` | Folder | Specific properties |
|---|---|---|
| `project` | `work/projects/` | `owner`, `team`, `rag`, `blocker`, `next_step`, `due` |
| `area` | `work/areas/` | `owner`, `team` |
| `workstream` | `work/workstreams/<group>/` | `group` (team slug), `team`, `owner`, `rag`, `progress`, `blocker`, `next_step`, `due`, `tracker` (issue keys or links) |
| `decision` | `work/decisions/` | `decision_status` (`to-decide | proposed | made`), `owner`, `team`, `due` |
| `risk` | `work/risks/` | `severity` (`low | medium | high | critical`), `risk_status` (`open | mitigated | closed`), `team` |
| `team` | `team/` | `lead`, `rag`, `tracker`, `members` |
| `person` | `team/` | `role`, `team`, `signal`, `rag`, `last_one_to_one` |
| `daily` | `journal/daily/<YYYY>/` | none |
| `weekly` | `journal/daily/<YYYY>/` | none |
| `report` | `journal/reports/` | `report_kind` |
| `meeting` | `journal/meetings/<type>/` | `meeting_type` |
| `resource` | `library/` | none |
| `hub` | `cockpit/`, root | none |

`rag` is one of `red | amber | green | unknown`. It is a health signal proposed by automations and validated by the human: jobs never write `rag`.

## 4. Task conventions

- Syntax: `- [ ] Task text @owner 📅 YYYY-MM-DD` (Obsidian Tasks plugin).
- Tags: `#waiting` (waiting on someone else), `#committed` (the user promised it), `#deadline` (hard or external date), `#to-triage` (proposed by an automation).
- Overdue and due-today tasks are shown by the cockpit with a Tasks query that excludes `journal/daily/`.

## 5. Vocabulary tokens

The installer replaces these tokens in every file under `core/` and `packs/`. Obsidian's own `{{title}}` and `{{date:...}}` placeholders are NOT tokens and must stay untouched.

| Token | Core default | Notes |
|---|---|---|
| `{{ct.team}}` / `{{ct.teams}}` | team / teams | e.g. squad, pod, crew |
| `{{ct.Team}}` / `{{ct.Teams}}` | Team / Teams | capitalised |
| `{{ct.workstream}}` / `{{ct.workstreams}}` | workstream / workstreams | e.g. topic, campaign, initiative, epic |
| `{{ct.Workstream}}` / `{{ct.Workstreams}}` | Workstream / Workstreams | capitalised |
| `{{ct.risk}}` / `{{ct.risks}}` | risk / risks | e.g. incident |
| `{{ct.Risk}}` / `{{ct.Risks}}` | Risk / Risks | capitalised |
| `{{ct.person}}` / `{{ct.people}}` | person / people | e.g. direct report, teammate |
| `{{ct.Person}}` / `{{ct.People}}` | Person / People | capitalised |
| `{{ct.owner_name}}` | (from answers) | the user's name |
| `{{ct.owner_handle}}` | (from answers) | handle used in tasks, default `me` |
| `{{ct.timezone}}` | (from answers) | IANA name, e.g. `Europe/Paris` |
| `{{ct.vault_path}}` | (from answers) | absolute vault path |

Rule: never hardcode a vocabulary word that has a token. Property values, folder names, tags used by dashboards and task tags are stable and are NOT tokenised.

## 6. Page style (every page)

- Only long pages (more than about 40 lines of content) and generated reports open with ONE callout `> [!summary] Summary` (3 bullets max: what it is, the state, what to do). Short pages get none.
- Tables for comparisons and attributes, bullets for ideas, no paragraph longer than 3 lines.
- Icons on `##` headings and states, always the same: 📅 agenda · ✅ actions · ⚖️ decisions · 🚧 work in progress · 🩺 health · 📊 figures · 👥 teams · 🚨 risks · 📎 annexes; status 🟢 🟠 🔴 ⚪.
- Detail (ids, raw numbers, sources, logs) goes at the bottom in FOLDED callouts `> [!note]- Title`, every line prefixed with `> `.
- Generated pages show `🕐 Generated on DD/MM/YYYY at HH:MM` (or `Updated on`) right under the title, with the real time.
- People, teams, workstreams and projects are wikilinks.
- Never rename a heading that a skill looks for (`## Notes`, `## Tasks`, `## Decisions`, `## Actions`): only an icon may be added in front.

## 7. Safety rules (shipped in `CLAUDE.md`)

- Never delete a note: move it to `_system/archive/`.
- Never rename or move a file without asking.
- Never write to `_system/attachments/`, never modify `_system/templates/` or `.obsidian/` unless asked.
- Never store secrets, credentials, personal data of customers or confidential documents.
- Jobs are read-only on external systems and write only inside the vault.

## 8. Language

Everything shipped is in English: docs, templates, skills, prompts, example vault.
