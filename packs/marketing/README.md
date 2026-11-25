# Marketing pack

For marketing leads, marketers and content teams. It turns the vault into a place where campaigns, content and weekly results live together.

## What you get

| Piece | What it does |
|---|---|
| Vocabulary | Workstreams become **campaigns**, people become **teammates** |
| Content notes | One note per piece (`type: content`) in `work/content/`, with channel, publish date and stage |
| Skills | `/campaign-brief`, `/content-calendar`, `/weekly-metrics`, `/competitor-watch` |
| Templates | Content piece, launch plan, campaign retrospective |
| Dashboard | Content pipeline, grouped by stage (idea, draft, review, scheduled, published) |
| Cockpit page | `cockpit/content-calendar.md`, the next two weeks at a glance |
| Jobs | Monday metrics report, weekday content reminders |
| Routines | Prompts for daily note, weekly review and morning brief |

## Tools it can use (all optional)

Analytics, CRM, task tracker and calendar. Without them the pack still works from your notes: the weekly report simply asks you for figures instead.

## Your first week

1. **Day 1.** Write down your active campaigns with `/campaign-brief "<goal>"`. One note each.
2. **Day 1.** Add the content you already have planned: copy `_system/templates/content-piece.md` into `work/content/`, one note per piece, with channel, publish date and stage.
3. **Day 2.** Run `/content-calendar` and fix the gaps and clashes it finds.
4. **Day 3.** Connect analytics and CRM if you have them, then run `/weekly-metrics` once by hand to check the numbers match what you see in your tools.
5. **Day 4.** Run `/competitor-watch "<competitor name>"` for two competitors.
6. **Day 5.** Turn on the two jobs. On Monday morning your first report is waiting in `journal/reports/`.
7. **When a campaign ends.** Fill in `_system/templates/campaign-retro.md` while it is fresh.

## Good habits

- Move a content note's `stage` as soon as it changes: the calendar and reminders trust it.
- Anything the automations suggest is tagged `#to-triage`. Accept it or drop it.
- Health (`rag`) and owners stay yours: automations never write them.
