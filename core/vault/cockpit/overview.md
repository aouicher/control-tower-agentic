---
title: "Overview"
date: 2026-01-01
tags: [moc, overview]
type: hub
status: active
---

# 🛠️ Overview

The state of all {{ct.teams}} and {{ct.workstreams}} at a glance. Back to [[cockpit]].

## 👥 {{ct.Teams}}
![[teams.base]]

## 🚧 {{ct.Workstreams}}
![[workstreams.base]]

## 🔁 Review cadence
| Rhythm | Source | What I look at |
|---|---|---|
| Daily | [[today]] | agenda, overdue tasks, `#to-triage` items |
| Weekly | latest weekly review in `journal/daily/` | progress per {{ct.workstream}}, blockers, `#waiting` items |
| Weekly | `journal/reports/` | generated reports, {{ct.risks}} |
| Monthly | `work/` and `journal/reports/` | trends, open decisions, {{ct.team}} health |

## 🩺 RAG rule (green, amber, red)
- 🟢 **Green**: delivering as planned, no open {{ct.risk}}, no blocker.
- 🟠 **Amber**: a delay, a blocking dependency or a growing problem; a plan is in progress.
- 🔴 **Red**: a critical {{ct.risk}}, a hard deadline at stake, or a blocker with no plan.
- ⚪ **Unknown**: not assessed yet.

Automations may propose a RAG in their report; I validate it and write it in the `rag` property of the {{ct.team}} or {{ct.workstream}} note.
