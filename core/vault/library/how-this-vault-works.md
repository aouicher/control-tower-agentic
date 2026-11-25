---
title: "How this vault works"
date: 2026-01-01
tags: [resource, guide]
type: resource
status: active
---

# 📖 How this vault works

A control tower: one place to see what matters, with Claude keeping it tidy. Start from [[cockpit]].

## 🧭 The 3 principles
1. **One task lives once.** Write it in the note of its project, area, {{ct.team}}, {{ct.workstream}} or {{ct.risk}}. Dashboards aggregate; never copy a task.
2. **Automations propose, you decide.** Anything created by a job or an agent carries `#to-triage`. Accept it (remove the tag), delegate it or drop it.
3. **Properties, not folders.** Facts (`status`, `rag`, `owner`, `due`, `blocker`, `next_step`) live in the frontmatter. The dashboards read them.

Also: nothing is deleted, retired notes go to `_system/archive/`.

## 📎 Where to put what
| I have... | It goes in |
|---|---|
| A quick thought or link | `_inbox/` |
| Something with an end date | `work/projects/` |
| An ongoing responsibility | `work/areas/` |
| A stream of work for a {{ct.team}} | `work/workstreams/<group>/` |
| A decision to take or taken | `work/decisions/` |
| A {{ct.risk}} or open problem | `work/risks/` |
| A {{ct.team}} or a {{ct.person}} | `team/` |
| A meeting | `journal/meetings/<type>/` |
| A reference or research | `library/` |

## 🏷️ Task tags
| Tag | Meaning |
|---|---|
| `#waiting` | waiting on someone else |
| `#committed` | I promised it |
| `#deadline` | hard or external date |
| `#to-triage` | proposed by an automation |

Syntax: `- [ ] Task text @{{ct.owner_handle}} 📅 YYYY-MM-DD`.

## 📅 Rhythm
- **Daily**: read [[today]] in the cockpit, clear overdue tasks, triage `#to-triage` items, empty `_inbox/` when asked.
- **Weekly**: run the weekly review, update `rag`, `blocker` and `next_step` on active notes, check [[commitments]] and [[overview]].
- **Monthly**: review open decisions, {{ct.risks}} and trends in `journal/reports/`.

## 🚦 Rules of the road
- Free text in frontmatter always goes in double quotes.
- Claude never deletes, renames or moves notes without asking, and never stores secrets or customers' personal data.
