# Using it every day

Installing takes ten minutes. This page is about everything after that: what to do in the morning, during the day and on Friday, with real examples for each profile.

## The two windows you use

| Window | What you do there |
|---|---|
| **Obsidian**, on your vault | Read: `cockpit.md` is your home page; its *Pages* section lists every reading page, including your profile's (`pulse`, `roadmap`, `content-calendar`...). Tick tasks, edit notes, drop quick thoughts in `_inbox/`. |
| **Claude Code**, started in the vault folder | Ask: type a skill like `/today`, or just say what you want in plain words. |

Start Claude Code in the vault, so it reads the vault's rules (`CLAUDE.md`) and skills:

```bash
cd ~/control-tower-vault
claude
```

You never need to remember a skill name. These two lines do the same thing:

```text
/today
start my day
```

## The daily rhythm

### Morning (5 minutes)

1. **Open `cockpit.md` in Obsidian.** Overnight jobs and routines have already written their reports in `journal/reports/`, and the cockpit shows what is overdue, what is due today, and your projects with their status (🟢🟠🔴).
2. **In Claude Code, run `/today`.** It creates today's daily note (agenda and focus) and rewrites `cockpit/today.md`, a page only `/today` writes:

   ```text
   > /today

   🕐 Updated on 26/11/2026 at 08:41
   > [!summary] Priorities of the day
   > 1. Review the address form pull request [[checkout-revamp]]
   > 2. Prepare the pricing decision for Thursday [[pricing-page-test]]
   > 3. Send the brief to the agency [[spring-launch]]

   ## 📅 Agenda
   | Time  | Meeting          | Topic / preparation               |
   |-------|------------------|-----------------------------------|
   | 10:00 | 1-1 with Casey   | [[casey-doe]]: growth plan        |
   | 14:30 | Launch steering  | [[spring-launch]]: budget at risk |

   📥 4 tasks to triage
   ```

3. **Triage.** Open `cockpit/my-work.md`, section *To triage*. Automations never add real tasks: they *propose* them with the tag `#to-triage`. For each one:
   - keep it: remove `#to-triage`, check the owner and date (`- [ ] Chase the vendor @me 📅 2026-11-28`);
   - drop it: delete the line;
   - later: remove the date or mark it `#waiting` if someone else must act first.

   Triage takes a minute and keeps the vault trustworthy: nothing lands on your list without you.

### During the day

| Situation | What to type in Claude Code | What you get |
|---|---|---|
| You leave a meeting | `/meeting 1-1 casey` then paste your notes or the transcript | A meeting note in `journal/meetings/casey/`, decisions filed, each action proposed into the project it belongs to (after you confirm) |
| A thought, link or idea | Create a note in Obsidian (it lands in `_inbox/`), or tell Claude "note in the inbox: ask finance about Q1 budget" | Captured now, sorted later with `/inbox` (below) |
| You need background on a topic | `/research onboarding emails best practices` | A sourced note in `library/`, vault searched first |
| A decision was made | "record the decision: we keep the in-house flag service, because..." | A note in `work/decisions/` with context, options and outcome |
| Something is at risk | "add a risk: the agency may miss the 12/03 deadline, impact high" | A note in `work/risks/` that shows up in the cockpit |
| You start something new | "create a project note for the checkout revamp, owner me, due 15/12" | A project note from the template, ready for the dashboards |

Ticking a task in Obsidian (`- [x]`) is all it takes to close it: the Tasks plugin dates it and every query updates.

### The inbox: capture now, sort later

`_inbox/` is the default folder of the vault: every new note you create in Obsidian lands there (for a new vault, the installer sets it as Obsidian's default location for new notes; in an existing vault, set it in Settings, Files and links). Use it for anything you do not want to file right now:

- a thought during a meeting, a link someone sent, an idea in the train;
- a note typed on your phone, if your vault syncs;
- something you asked Claude to capture: "note in the inbox: ask finance about the Q1 budget".

Do not bother with properties, folders or format there. Then, once or twice a week, empty it with `/inbox`:

```text
> /inbox

| Note                 | Proposal     | Destination        | Tasks found                         |
|----------------------|--------------|--------------------|-------------------------------------|
| call vendor.md       | task only    | [[spring-launch]]  | Call the vendor about the delay     |
| pricing article.md   | library      | library/           | none                                |
| idea referral.md     | new project  | work/projects/     | none                                |
| old notes.md         | archive      | _system/archive/   | none                                |

Confirm all, or tell me what to change.

> ok except the referral idea: keep it as a draft workstream

Filed 4 notes. Inbox is empty.
```

Nothing moves until you confirm, nothing is deleted (old material goes to `_system/archive/`), and each task is written once, in the note it belongs to. An inbox that stays under ten notes is a good sign: if it grows, run `/inbox` on Friday as part of the weekly review.

### Friday (15 minutes)

1. Empty the inbox with `/inbox` if it has more than a few notes.
2. Read the weekly report your profile's job wrote (see the tables below) in `journal/reports/`.
3. Run `/weekly-review`. It writes the week's review from what you finished and what is still open: done, carried over, signals, and a proposed top 3 for next week. It also flags tasks that exist twice.
4. Optional: `/time-review` shows where your calendar time went, by category.
5. Update the status of your projects (`rag: green | amber | red`) where it changed. Claude proposes changes but never writes a status itself.

### Once a month

- Archive finished projects: set `status: archived`, then move the note to `_system/archive/` (or ask Claude "archive the finished projects"). Nothing is ever deleted.
- Run the health check: `python3 <repository>/installer/doctor.py --vault <vault> --ct-home ~/.control-tower`.

## What runs without you

| Kind | Where results land | How to tell it ran |
|---|---|---|
| Local jobs (your computer) | `journal/reports/` | `~/.control-tower/logs/<job>.log`; nothing runs while the computer sleeps |
| Cloud routines (claude.ai) | `journal/reports/` or the daily note, pushed to the vault's GitHub repository: pull it to see them (see [scheduling](scheduling.md#cloud-routines-and-your-local-vault)) | The routine's page on claude.ai |

A report always says when data was missing ("not verified", "at least N (truncated)"). Silence never means "all green".

## A week by profile

### Marketing lead

| When | Do | Example |
|---|---|---|
| Monday | `/content-calendar` | "Two posts collide on Wednesday; nothing planned for the newsletter on 4/12" written to `cockpit/content-calendar.md` |
| New campaign | `/campaign-brief launch the spring offer to existing customers, budget 20k` | A campaign note with audience, message, channels, budget, KPIs, timeline and risks |
| Every morning | Read the morning brief | Content going live in the next three days, yesterday's traffic against the same day last week |
| Mid-week | `/competitor-watch Acme Rival, last 30 days` | A sourced note in `library/` with launches, pricing and campaign moves |
| Monday (job) | `weekly-metrics` report, named after last week (`marketing-metrics-YYYY-Www`) | Traffic, conversion, draft and active campaigns, best and worst content, three observations |
| Friday | `/weekly-review` | Done, slipped content, next week's top 3 |

Templates you will use: `content-piece`, `launch-plan`, `campaign-retro` (in Obsidian: command palette, *Templates: Insert template*).

### Product manager

| When | Do | Example |
|---|---|---|
| After a customer call | `/discovery-notes` and paste the transcript | An anonymised interview note: quotes, pains, jobs to be done, linked opportunities |
| Planning | `/prioritize rice` | A ranked table in `cockpit/roadmap.md`, with why two items tie |
| New initiative | `/prd-draft bulk export for admins` | A PRD note: problem, users, goals and non-goals, requirements, metrics, open questions |
| Monday (job) | `feedback-digest` report, named after last week | Feedback themes, metric changes, emerging issues |
| Friday (job) | `product-weekly` report | Shipped, in progress, blocked, metric movements, decisions needed |
| Friday | `/weekly-review`, or the `weekly-review` routine | The routine adds the product loop: interviews this week, opportunities by stage |

### Developer

| When | Do | Example |
|---|---|---|
| Before standup | `/standup` | Yesterday from your commits and closed tickets, today's plan, blockers, in the `🧍 Standup` section of today's daily note |
| Between tasks | `/review-queue` | Pull requests waiting for you, yours with their review and CI state, stale ones; it offers a note per open pull request for the `my-pull-requests` dashboard |
| While working | `/worklog decided to cache the price list for 5 min, see PR 412` | A dated line in today's note |
| After a hard bug | `/debug-journal checkout timeout on large carts` | Symptom, hypotheses tried, root cause, fix, how to detect it next time |
| Every morning (job) | `morning-prs` report | Reviews to do and your open pull requests |
| Friday (job) | `weekly-wrap` report (`dev-weekly-wrap-YYYY-Www`) | Merged, closed, carried over |

### Engineering leader

| When | Do | Example |
|---|---|---|
| Every morning (jobs) | `morning-triage` and `service-health` reports | New or spiking errors, failing quality gates, service health, each with a verdict |
| Every morning | Read `cockpit/pulse.md` | Health of every service at a glance |
| After an incident | `/postmortem checkout outage 25/11` | A blameless postmortem with a sourced timeline, root cause, impact and follow-ups |
| A technical choice | `/adr move image processing to a queue` | An ADR in the code repository and an index note in `work/decisions/` |
| A security questionnaire | `/questionnaire-answer <path or pasted questions>` | Draft answers with evidence and explicit gaps, stored outside the vault |
| Friday (job) | `weekly-digest` report, `cockpit/delivery.md` | Pull requests merged per team, sprint status, load per person as signals for 1-1s |

## Talking to Claude: good habits

- **Say where it belongs.** "Add to the spring launch: ask legal to review the terms by Friday" puts one task in the right note instead of the inbox.
- **Ask for a proposal before a change.** "What would you change in the checkout revamp status?" Claude proposes; you decide.
- **Paste, don't summarise.** For meetings and interviews, paste the raw notes or transcript: the skill does the structuring.
- **Check numbers at the source** when a decision depends on them. Reports link their sources.
- **Never paste secrets** (passwords, tokens, customer personal data) into notes or chat.

## When something feels off

| Feels like | Usually |
|---|---|
| The cockpit is empty | No project notes yet, the Tasks plugin is not enabled, or Obsidian is older than 1.9 (no Bases). Create one project and reload. |
| A report is missing this morning | The computer was asleep at the job's time. For a cloud routine, the vault was not pushed or pulled. Run it by hand: `python3 ~/.control-tower/bin/run_job.py --job <id> --ct-home ~/.control-tower`. |
| The same task shows twice | It was copied into two notes. Keep one; `/weekly-review` lists duplicates. |
| A report says "not verified" | A tool was not reachable. Check the connection (see [adapters](adapters.md)). |

More in [troubleshooting](troubleshooting.md).
