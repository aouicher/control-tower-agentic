#!/usr/bin/env python3
"""Build a fictional, lived-in demo vault for screenshots. Standard library only (Python 3.9+).

    python3 examples/build_demo_vault.py --out ~/control-tower-demo [--packs engineering,product]
        [--date YYYY-MM-DD] [--force] [--tasks-plugin-dir <installed obsidian-tasks-plugin folder>]

1. Runs the real installer (owner Sam Rivera, handle sam, scheduler "none": nothing is scheduled;
   runtime folder <out>-runtime, next to the vault: never inside it).
2. Adds fictional notes for Acme, all dated relative to --date (default: today), so every cockpit page
   and dashboard shows realistic content.
3. Seeds Obsidian: bookmarks the cockpit and, with --tasks-plugin-dir, enables a local copy of the Tasks
   plugin. Nothing is downloaded.

Everything is fictional: Acme, Sam Rivera and every teammate are made up.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'installer'))
import install  # noqa: E402
import render  # noqa: E402

SUPPORTED_PACKS = ('engineering', 'product')
TASKS_ID = 'obsidian-tasks-plugin'
# property values that are identifiers or numbers, written without quotes; every other string is double-quoted
RAW_KEYS = {'type', 'status', 'rag', 'decision_status', 'severity', 'risk_status', 'stage', 'report_kind', 'meeting_type',
            'group'}


class DemoError(Exception):
    pass


# ----------------------------------------------------------------------------- helpers
def q(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def yaml_value(key, v):
    if v is None or (v == '' and key not in ('owner', 'team', 'blocker', 'next_step', 'signal', 'problem', 'tracker')):
        return ''
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        if key == 'tags':
            return '[' + ', '.join(v) + ']'
        return '[' + ', '.join(q(x) for x in v) + ']'
    return v if key in RAW_KEYS else q(v)


def dmy(d):
    return d.strftime('%d/%m/%Y')


def iso_week(d):
    y, w, _ = d.isocalendar()
    return f'{y}-W{w:02d}'


def long_date(d):
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B %Y')}"


def answers_for(out, packs):
    """Answers like tests/test_installer.py: the first non-"none" tool per capability of each pack."""
    tools = {}
    for p in packs:
        manifest = install.jload(os.path.join(REPO, 'packs', p, 'pack.json'))
        for item in manifest.get('questions', []):
            tools.setdefault(item['capability'], next((c for c in item['choices'] if c != 'none'), 'none'))
    return {'owner_name': 'Sam Rivera', 'owner_handle': 'sam', 'timezone': 'Europe/London',
            'vault_path': out, 'ct_home': out + '-runtime', 'packs': list(packs), 'tools': tools,
            'scheduler': 'none'}


def prepare_out(out, force):
    if os.path.islink(out):
        raise DemoError(f'{out} is a symbolic link: refusing to use it')
    if os.path.exists(out) and not os.path.isdir(out):
        raise DemoError(f'{out} exists and is not a folder')
    if os.path.isdir(out) and os.listdir(out):
        if not force:
            raise DemoError(f'{out} exists and is not empty: pass --force to rebuild it')
        if not os.path.isfile(os.path.join(out, '.control-tower', 'manifest.json')):
            raise DemoError(f'{out} is not empty and is not a control tower vault (no .control-tower/manifest.json): '
                            'refusing to delete it')
        shutil.rmtree(out)
        if os.path.isfile(os.path.join(out + '-runtime', 'install.json')):  # its runtime, made by the installer
            shutil.rmtree(out + '-runtime')


# ----------------------------------------------------------------------------- the demo content
class Demo:
    def __init__(self, vault, day, packs, words):
        self.vault, self.d, self.packs, self.w = vault, day, packs, words
        self.eng, self.prod = 'engineering' in packs, 'product' in packs
        self.created = []

    def day(self, n):
        return self.d + datetime.timedelta(days=n)

    # ---- writing
    def write(self, rel, text):
        path = os.path.join(self.vault, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
        self.created.append(rel)

    def note(self, rel, props, body):
        lines = ['---']
        for k, v in props:
            val = yaml_value(k, v)
            lines.append(f'{k}: {val}' if val != '' else f'{k}:')
        lines.append('---')
        self.write(rel, '\n'.join(lines) + '\n\n' + body.strip('\n') + '\n')

    def read(self, rel):
        with open(os.path.join(self.vault, rel), encoding='utf-8') as fh:
            return fh.read()

    def replace_block(self, rel, start, end, content):
        text = self.read(rel)
        rx = re.compile(re.escape(start) + r'.*?' + re.escape(end), re.S)
        if not rx.search(text):
            raise DemoError(f'{rel}: markers {start} ... {end} not found')
        self.write(rel, rx.sub(lambda m: start + '\n' + content.strip('\n') + '\n' + end, text, count=1))

    def task(self, text, due=None, tags=()):
        s = f'- [ ] {text} @sam'
        if due is not None:
            s += f' 📅 {due.isoformat()}'
        return s + ''.join(f' #{t}' for t in tags)

    def done(self, text, when):
        return f'- [x] {text} @sam ✅ {when.isoformat()}'

    @staticmethod
    def base(title, date, type_, tags, status='active'):
        return [('title', title), ('date', date), ('type', type_), ('tags', tags), ('status', status)]

    # ---- build
    def build(self):
        self.teams_and_people()
        self.projects()
        self.workstreams()
        self.decisions_and_risks()
        self.journal()
        self.inbox()
        if self.eng:
            self.engineering()
        if self.prod:
            self.product()
        self.today_page()
        return self.created

    # ---- teams and people
    def teams_and_people(self):
        w, d = self.w, self.d
        teams = [
            ('checkout', 'Checkout', 'amber', 'casey-doe', 'CHK', ['casey-doe', 'avery-quinn'],
             'Own the path from basket to paid order: checkout web, payment API, fraud rules.',
             [('Overall', '🟠', 'Fraud rules slipping by about a week'), ('Delivery', '🟢', '21 of 26 sprint items done last week'),
              ('Morale', '🟢', 'Steady after the peak rehearsal')],
             ['[[checkout-revamp]] (project)', '[[one-click-payments]] and [[fraud-rules-v2]]'],
             [], ['[[checkout-peak-traffic]]'],
             ['Four engineers and one designer besides the people above.', 'Stand-up 09:30, retro every other Friday.']),
            ('platform', 'Platform', 'red', 'riley-park', 'PLT', ['riley-park', 'devon-hale'],
             'Run the shared infrastructure: databases, CI, deploys, observability and on-call.',
             [('Overall', '🔴', 'Database upgrade blocked, EU residency at risk'), ('Delivery', '🟠', '7 of 16 sprint items done'),
              ('Morale', '🟠', 'On-call load is high since the last incident')],
             ['[[eu-data-residency]] (project)', '[[database-upgrade]] and [[ci-speedup]]'],
             [], ['[[single-region-database]]'],
             ['Last sync: [[' + self.day(-2).isoformat() + '-team-sync]].', 'Three engineers besides the people above, one open role.']),
            ('growth', 'Growth', 'green', 'harper-lane', 'GRW', ['harper-lane'],
             'Grow activation and referrals: onboarding, partner API, referral programme.',
             [('Overall', '🟢', 'On track'), ('Delivery', '🟢', '11 of 14 sprint items done'), ('Morale', '🟢', 'Good energy after the partner pilot')],
             ['[[partner-api-launch]] (project)', '[[onboarding-checklist]] and [[referral-programme]]'],
             [self.task('Ask [[harper-lane]] for the Q1 hiring plan', self.day(3), ['waiting'])], [],
             ['Four engineers and one designer; Harper is the product lead.']),
        ]
        people = {
            'casey-doe': ('Casey Doe', 'Engineering manager', 'checkout', 'green', self.day(-1), 'Steady; wants to grow a tech lead',
                          ['Calm under pressure', 'Clear written plans'], ['Delegating incident follow-ups'],
                          [], [f'1-1 notes: [[{self.day(-1).isoformat()}-1-1-casey-doe]].']),
            'avery-quinn': ('Avery Quinn', 'Senior engineer', 'checkout', 'green', self.day(-8), 'Ready for a tech lead role',
                            ['Payments domain', 'Mentoring'], ['Writing design docs earlier'],
                            [self.task('Share the tech lead feedback summary with [[avery-quinn]]', d, ['committed'])],
                            ['Leads [[one-click-payments]].']),
            'riley-park': ('Riley Park', 'Engineering manager', 'platform', 'amber', self.day(-15), 'On-call load is high',
                           ['Incident response', 'Hiring'], ['Saying no to side requests'],
                           [self.task('Discuss the on-call rota change in the next 1-1')],
                           ['1-1 today at 11:00: start with on-call load.']),
            'devon-hale': ('Devon Hale', 'Staff engineer', 'platform', 'red', self.day(-24), 'Overloaded by the database upgrade',
                           ['Databases', 'Deep debugging'], ['Asking for help early'], [],
                           ['Last 1-1 was over three weeks ago: book one this week.', 'Owns [[database-upgrade]].']),
            'harper-lane': ('Harper Lane', 'Product manager', 'growth', 'green', self.day(-6), 'Wants a bigger discovery budget',
                            ['Customer interviews', 'Crisp PRDs'], ['Sizing engineering effort'], [],
                            ['Owns [[onboarding-checklist]] and [[referral-programme]].']),
        }
        for slug, title, rag, lead, tracker, members, mission, health, wip, tasks, risks, notes in teams:
            rows = '\n'.join(f'| [[{m}]] | {people[m][1]} | {dict(green="🟢", amber="🟠", red="🔴")[people[m][3]]} |' for m in members)
            body = [f'# {title}', '', '## 🎯 Mission', '', f'- {mission}', '', '## 🩺 Health', '',
                    '| Signal | State | Note |', '|---|---|---|'] + [f'| {a} | {b} | {c} |' for a, b, c in health] + [
                    '', f'## 👥 Members', '', f"| {w['Person']} | Role | Signal |", '|---|---|---|', rows, '',
                    '## 🚧 Work in progress', ''] + [f'- {x}' for x in wip] + ['', '## ✅ Tasks', ''] + (tasks or ['- Nothing open.']) + [
                    '', f"## 🚨 {w['Risks']}", ''] + ([f'- {r}' for r in risks] or ['- None open.']) + [
                    '', '## 📝 Notes', ''] + [f'- {n}' for n in notes]
            self.note(f'team/{slug}.md', self.base(title, self.day(-90), 'team', ['team']) + [
                ('lead', f'[[{lead}]]'), ('rag', rag), ('tracker', tracker), ('members', [f'[[{m}]]' for m in members])], '\n'.join(body))
        for slug, (name, role, team, rag, last, signal, strengths, growth, tasks, notes) in people.items():
            icon = dict(green='🟢', amber='🟠', red='🔴')[rag]
            body = [f'# {name}', '', '## 👤 Profile', '', '| Field | Value |', '|---|---|', f'| Role | {role} |',
                    f"| {w['Team']} | [[{team}]] |", f"| Strengths | {', '.join(strengths)} |", f"| Growth areas | {', '.join(growth)} |", '',
                    '## 🩺 Health', '', '| Signal | State | Note |', '|---|---|---|', f'| Overall | {icon} | {signal} |', '',
                    '## ✅ Tasks', ''] + (tasks or ['- Nothing open.']) + ['', '## 📝 Notes', ''] + [f'- {n}' for n in notes]
            self.note(f'team/{slug}.md', self.base(name, self.day(-90), 'person', ['person']) + [
                ('role', role), ('team', f'[[{team}]]'), ('signal', signal), ('rag', rag), ('last_one_to_one', last)], '\n'.join(body))

    # ---- projects
    def projects(self):
        w = self.w
        items = [
            ('checkout-revamp', 'Checkout revamp', 'active', 'casey-doe', 'checkout', 'amber',
             'Fraud rules v2 is a week late', 'Send the revised launch plan to support', self.day(20),
             'Cut checkout abandonment from 38% to 30% before the spring sale.',
             [('Overall', '🟠', 'One week of slack left'), ('Scope', '🟢', 'Frozen'), ('Schedule', '🟠', 'Fraud rules late')],
             [('one-click-payments', 'avery-quinn', '🟢'), ('fraud-rules-v2', 'casey-doe', '🟠')],
             [self.task('Send the revised launch plan to support', self.day(-1), ['committed']),
              self.done('Freeze the scope with design', self.day(-6))],
             ['Payment provider chosen: [[wallet-provider-choice]].'], ['[[checkout-peak-traffic]]']),
            ('eu-data-residency', 'EU data residency', 'active', 'riley-park', 'platform', 'red',
             'Hosting vendor has not signed the data processing agreement', 'Approve the database maintenance window', self.day(9),
             'Serve and store EU customer data from an EU region only, as promised to three enterprise prospects.',
             [('Overall', '🔴', 'Hard date at stake'), ('Scope', '🟢', 'Agreed'), ('Schedule', '🔴', 'Blocked on the vendor and the upgrade')],
             [('database-upgrade', 'devon-hale', '🔴')],
             [self.task('Chase the hosting vendor for the signed agreement', self.day(-2), ['waiting'])],
             ['Pending: [[database-upgrade-window]].'], ['[[single-region-database]]']),
            ('partner-api-launch', 'Partner API launch', 'active', 'harper-lane', 'growth', 'green',
             '', 'Open the API to the second pilot partner', self.day(35),
             'Let partners create Acme accounts for their own customers through a public API.',
             [('Overall', '🟢', 'Pilot partner live'), ('Scope', '🟢', 'Stable'), ('Schedule', '🟢', 'Two weeks ahead')],
             [('referral-programme', 'harper-lane', '🟢')],
             [self.task('Approve the partner pricing page copy', self.day(5))],
             ['Release cadence follows [[weekly-release-train]].'], []),
            ('mobile-app-refresh', 'Mobile app refresh', 'draft', 'avery-quinn', 'checkout', 'unknown',
             '', 'Write a one-page proposal', self.day(75),
             'Bring the mobile checkout to parity with the web checkout.',
             [('Overall', '⚪', 'Not started'), ('Scope', '⚪', 'To define'), ('Schedule', '⚪', 'To define')],
             [], [self.task('Ask [[avery-quinn]] for a one-page proposal', self.day(12))], [], []),
        ]
        for slug, title, status, owner, team, rag, blocker, nxt, due, goal, health, wip, tasks, decisions, risks in items:
            body = [f'# {title}', '', '## 🎯 Goal', '', f'- {goal}', '', '## 🩺 Health', '', '| Signal | State | Note |', '|---|---|---|'] + [
                f'| {a} | {b} | {c} |' for a, b, c in health] + ['', '## 🚧 Work in progress', '',
                f"| {w['Workstream']} | Owner | State |", '|---|---|---|'] + (
                [f'| [[{s}]] | [[{o}]] | {i} |' for s, o, i in wip] or ['| Nothing started yet | | ⚪ |']) + [
                '', '## ✅ Tasks', ''] + tasks + ['', '## ⚖️ Decisions', ''] + ([f'- {x}' for x in decisions] or ['- None yet.']) + [
                '', f"## 🚨 {w['Risks']}", ''] + ([f'- {r}' for r in risks] or ['- None open.']) + [
                '', '## 📝 Notes', '', f'- {w["Team"]}: [[{team}]].']
            self.note(f'work/projects/{slug}.md', self.base(title, self.day(-40), 'project', ['project'], status) + [
                ('owner', f'[[{owner}]]'), ('team', f'[[{team}]]'), ('rag', rag), ('blocker', blocker), ('next_step', nxt), ('due', due)],
                '\n'.join(body))

    # ---- workstreams (initiatives / topics)
    def workstreams(self):
        w = self.w
        prd = self.prod
        items = [
            ('checkout', 'one-click-payments', 'One-click payments', 'avery-quinn', 'green', 60, '', 'Raise the wallet button to 50% of traffic',
             self.day(18), 'CHK-412', 'Pay with a saved wallet in one click on returning visits.',
             [('Wallet button at 10% of traffic', 'avery-quinn', '🟢'), ('Saved cards for returning users', 'avery-quinn', '🟠')],
             [self.done('Ship the wallet button to 10% of traffic', self.day(-2))], ['[[checkout-revamp]]']),
            ('checkout', 'fraud-rules-v2', 'Fraud rules v2', 'casey-doe', 'amber', 35, 'False positives at 4% on the new rules',
             'Tune the rules with the risk analyst', self.day(11), 'CHK-430, CHK-431', 'Replace the static fraud rules with scored rules.',
             [('Scored rules in shadow mode', 'casey-doe', '🟠'), ('Quality gate on new code', 'casey-doe', '🔴')],
             [self.task('Review the false-positive numbers with [[casey-doe]]', self.day(1))], ['[[checkout-revamp]]']),
            ('platform', 'database-upgrade', 'Database upgrade', 'devon-hale', 'red', 20, 'No maintenance window agreed',
             'Approve the window in the decision note', self.day(7), 'PLT-88', 'Move the main database to the new major version, in the EU region.',
             [('Replica rehearsal', 'devon-hale', '🟢'), ('Maintenance window', 'riley-park', '🔴')],
             [self.task('Approve the maintenance window proposal', self.d)], ['[[eu-data-residency]]', '[[database-upgrade-window]]']),
            ('platform', 'ci-speedup', 'CI speed-up', 'riley-park', 'green', 80, '', 'Roll the remote cache out to every repository',
             self.day(14), 'PLT-102', 'Bring the median CI run under 8 minutes.',
             [('Remote build cache', 'riley-park', '🟢'), ('Flaky test quarantine', 'devon-hale', '🟢')],
             [self.done('Enable the remote build cache on the main repository', self.day(-3)),
              self.task('Get a cache cost estimate from finance', None, ['waiting'])], []),
            ('growth', 'onboarding-checklist', 'Onboarding checklist', 'harper-lane', 'amber', 45, 'Analytics events missing on step 3',
             'Sign off the PRD scope', self.day(21), 'GRW-57', 'Guide new admins through setup so more accounts reach their first invoice.',
             [('Checklist UI', 'harper-lane', '🟢'), ('Step 3 analytics events', 'harper-lane', '🟠')],
             [self.task('Sign off the onboarding checklist scope', self.day(2), ['committed'])],
             ['[[onboarding-checklist-prd]] (PRD)', '[[guided-setup-wizard]] (opportunity)'] if prd else []),
            ('growth', 'referral-programme', 'Referral programme', 'harper-lane', 'green', 10, '', 'Draft the reward rules',
             self.day(42), 'GRW-63', 'Let customers invite other businesses and earn a month free.',
             [('Reward rules', 'harper-lane', '⚪')],
             [self.task('Draft the referral reward rules', self.day(12))], ['[[partner-api-launch]]']),
        ]
        for group, slug, title, owner, rag, progress, blocker, nxt, due, tracker, goal, wip, tasks, links in items:
            icon = dict(green='🟢', amber='🟠', red='🔴')[rag]
            body = [f'# {title}', '', '## 🎯 Goal', '', f'- {goal}', '', '## 🩺 Health', '', '| Signal | State | Note |', '|---|---|---|',
                    f'| Overall | {icon} | {blocker or "On track"} |', f'| Progress | {icon} | {progress}% |', '',
                    '## 🚧 Work in progress', '', '| Item | Owner | State |', '|---|---|---|'] + [
                    f'| {a} | [[{o}]] | {s} |' for a, o, s in wip] + ['', '## ✅ Tasks', ''] + tasks + [
                    '', '## ⚖️ Decisions', '', '- None yet.', '', f"## 🚨 {w['Risks']}", '', f'- {blocker}' if blocker else '- None open.',
                    '', '## 📝 Notes', ''] + ([f'- Related: {x}' for x in links] or ['- Nothing yet.'])
            self.note(f'work/workstreams/{group}/{slug}.md', self.base(title, self.day(-30), 'workstream', ['workstream']) + [
                ('group', group), ('team', f'[[{group}]]'), ('owner', f'[[{owner}]]'), ('rag', rag), ('progress', progress),
                ('blocker', blocker), ('next_step', nxt), ('due', due), ('tracker', tracker)], '\n'.join(body))

    # ---- decisions and risks
    def decisions_and_risks(self):
        w = self.w
        self.note('work/decisions/database-upgrade-window.md', self.base('Database upgrade window', self.day(-5), 'decision', ['decision']) + [
            ('decision_status', 'to-decide'), ('owner', '[[riley-park]]'), ('team', '[[platform]]'), ('due', self.day(2))], f"""
# Database upgrade window

## ⚖️ Decision

- When do we take the 40-minute write freeze for the [[database-upgrade]]?

## 🔎 Context

- The upgrade unblocks [[eu-data-residency]], due {self.day(9).isoformat()}.
- Rehearsal on a replica took 34 minutes.

## 🧭 Options

| Option | Pros | Cons | Cost |
|---|---|---|---|
| A: Sunday 06:00 | Lowest traffic | Weekend on-call for two people | Overtime |
| B: Tuesday 22:00 | Full team awake | 3x the traffic of option A | Short checkout outage |

## ✅ Outcome

- To decide at the review today at 14:00.

## ✅ Tasks

{self.task('Review the two options with [[riley-park]] before the meeting', self.d)}

## 📎 Annexes

- Related: [[single-region-database]]
""")
        self.note('work/decisions/wallet-provider-choice.md', self.base('Wallet provider choice', self.day(-12), 'decision', ['decision']) + [
            ('decision_status', 'made'), ('owner', '[[casey-doe]]'), ('team', '[[checkout]]'), ('due', self.day(-12))], f"""
# Wallet provider choice

## ⚖️ Decision

- Which provider powers [[one-click-payments]]?

## ✅ Outcome

- Chosen: keep the current payment provider and enable its wallet option. Reason: no new contract, live in two weeks.
- Date made: {self.day(-12).isoformat()}
""")
        self.note('work/decisions/weekly-release-train.md', self.base('Weekly release train', self.day(-20), 'decision', ['decision']) + [
            ('decision_status', 'made'), ('owner', 'Sam Rivera'), ('team', ['[[checkout]]', '[[platform]]', '[[growth]]']),
            ('due', self.day(-20))], f"""
# Weekly release train

## ⚖️ Decision

- Do we keep ad hoc releases or move to a weekly train?

## ✅ Outcome

- Chosen: a weekly train every Tuesday, with hotfixes outside it. Reason: fewer surprises for support.
- Date made: {self.day(-20).isoformat()}
""")
        self.note('work/risks/single-region-database.md', self.base('Single-region database', self.day(-18), 'risk', ['risk']) + [
            ('severity', 'high'), ('risk_status', 'open'), ('team', '[[platform]]')], f"""
# Single-region database

> [!summary] Summary
> - The main database runs in one region with no tested failover: an outage stops checkout.
> - State: high, open; nightly backups only, no warm standby.
> - To do: test a failover after the [[database-upgrade]], owner [[riley-park]].

## 🚨 Description

| Field | Value |
|---|---|
| Severity | 🔴 |
| Status | open |
| Detected on | {self.day(-18).isoformat()} |
| Impact | Checkout and sign-in down for the whole outage |
| Likelihood | Low, but the last regional incident lasted 3 hours |

## 📅 Timeline

| Date | Event |
|---|---|
| {self.day(-18).isoformat()} | Raised in the architecture review |
| {self.day(-2).isoformat()} | Discussed in [[{self.day(-2).isoformat()}-team-sync]] |

## 🔎 Cause

- The replica was dropped two years ago to save cost.

## 🛡️ Mitigation

- Warm standby comes with the [[database-upgrade]].

## ✅ Open tasks

{self.task('Confirm the failover test date with [[platform]]', self.day(4), ['deadline'])}

## ⚖️ Decisions

- Depends on [[database-upgrade-window]].

## 📎 Annexes

> [!note]- Evidence, logs and sources
> - Architecture review notes, section "data stores".
""")
        self.note('work/risks/checkout-peak-traffic.md', self.base('Checkout peak traffic', self.day(-35), 'risk', ['risk']) + [
            ('severity', 'medium'), ('risk_status', 'mitigated'), ('team', '[[checkout]]')], f"""
# Checkout peak traffic

## 🚨 Description

| Field | Value |
|---|---|
| Severity | 🟠 |
| Status | mitigated |
| Detected on | {self.day(-35).isoformat()} |
| Impact | Slow checkout at 5x normal traffic |

## 🛡️ Mitigation

- Load test passed at 6x on {self.day(-10).isoformat()}; autoscaling limits raised.

## ✅ Open tasks

{self.done('Run the peak load test', self.day(-10))}
""")

    # ---- journal
    def journal(self):
        w, d = self.w, self.d
        y = d.strftime('%Y')
        eng_note = f'- Morning triage: refund timeouts on payment-api, see [[{d.isoformat()}-triage]].' if self.eng else '- Quiet morning.'
        self.note(f'journal/daily/{y}/{d.isoformat()}.md', self.base(d.isoformat(), d, 'daily', ['daily']), f"""
# {long_date(d)}

## 📅 Agenda

| Time | Meeting | Topic / preparation |
|---|---|---|
| 09:30 | Checkout stand-up | [[checkout]] |
| 11:00 | 1-1 with [[riley-park]] | On-call load, see the open task in [[riley-park]] |
| 14:00 | Database upgrade window review | [[database-upgrade-window]]: choose A or B |
| 16:00 | Product review | [[onboarding-checklist]] scope |

## 🎯 Focus

1. Decide the database upgrade window: [[database-upgrade-window]]
2. Unblock EU data residency, the signed agreement is late: [[eu-data-residency]]
3. Send the revised checkout launch plan (overdue): [[checkout-revamp]]

## ✅ Tasks

Only tasks that are for today and nowhere else. Everything else belongs in its project, area, {w['team']} or {w['workstream']} note.

{self.task("Book a room for Friday's demo", d)}

## 📝 Notes

{eng_note}

## ⚖️ Decisions

-

## 🚨 Blockers

- No maintenance window yet for the [[database-upgrade]].

## 🌙 End of day

| Done | Carried over | Learned |
|---|---|---|
|  |  |  |
""")
        yd = self.day(-1)
        one = f'{yd.isoformat()}-1-1-casey-doe'
        self.note(f"journal/daily/{yd.strftime('%Y')}/{yd.isoformat()}.md", self.base(yd.isoformat(), yd, 'daily', ['daily']), f"""
# {long_date(yd)}

## 📅 Agenda

| Time | Meeting | Topic / preparation |
|---|---|---|
| 10:00 | 1-1 with [[casey-doe]] | [[{one}]] |
| 13:30 | Partner pilot check-in | [[partner-api-launch]] |
| 15:00 | Hiring debrief | Platform open role, [[platform]] |

## 🎯 Focus

1. Prepare the 1-1 with Casey: [[casey-doe]]
2. Review the fraud rules numbers: [[fraud-rules-v2]]
3. Read the platform sync notes: [[{self.day(-2).isoformat()}-team-sync]]

## ✅ Tasks

Only tasks that are for today and nowhere else. Everything else belongs in its project, area, {w['team']} or {w['workstream']} note.

{self.done('Prepare the 1-1 with Casey', yd)}
{self.done('Answer the partner pilot questions', yd)}

## 📝 Notes

- The partner pilot is happy with the sandbox; second partner ready next month.

## ⚖️ Decisions

- Fraud rules v2 stays in shadow mode one more week.

## 🚨 Blockers

- The hosting vendor still has not signed the agreement for [[eu-data-residency]].

## 🌙 End of day

| Done | Carried over | Learned |
|---|---|---|
| 1-1 with Casey, partner pilot answers | Revised launch plan for support | Shadow mode numbers need a week of data |
""")
        self.note(f'journal/meetings/1-1/casey-doe/{one}.md', self.base(f'1-1 Casey Doe {yd.isoformat()}', yd, 'meeting', ['meeting', '1-1']) + [
            ('meeting_type', '1-1')], f"""
# 1-1 Casey Doe {yd.isoformat()}

> [!summary] Summary
> - Fraud rules v2 is a week late; Casey owns the new plan.
> - Agreed to sponsor [[avery-quinn]] as tech lead of [[one-click-payments]].
> - Next: the revised launch plan goes to support.

| | |
|---|---|
| Participants | [[casey-doe]], Sam Rivera |
| Context | Fortnightly 1-1 |

## 📝 Notes

- False positives at 4% on the scored rules; target is under 1%.
- Casey wants Avery to lead design reviews from next sprint.

## ⚖️ Decisions

| Decision | Decider | Link |
|---|---|---|
| Keep fraud rules v2 in shadow mode one more week | [[casey-doe]] | [[fraud-rules-v2]] |

## ✅ Actions

Each action lives in the note it belongs to: this table only points to it.

| Action | Owner | Due | Where it lives |
|---|---|---|---|
| Send the revised launch plan to support | Sam Rivera | {self.day(-1).isoformat()} | [[checkout-revamp]] |
| Review the false-positive numbers | Sam Rivera | {self.day(1).isoformat()} | [[fraud-rules-v2]] |
| Share the tech lead feedback summary | Sam Rivera | {d.isoformat()} | [[avery-quinn]] |

## 🚨 {w['Risks']} raised

- None.
""")
        sd = self.day(-2)
        self.note(f'journal/meetings/team-sync/{sd.isoformat()}-team-sync.md',
                  self.base(f'Meeting team-sync {sd.isoformat()}', sd, 'meeting', ['meeting', 'team-sync']) + [('meeting_type', 'team-sync')], f"""
# Meeting team-sync {sd.isoformat()}

> [!summary] Summary
> - Platform sync: the [[database-upgrade]] needs a maintenance window this week.
> - Two options written up in [[database-upgrade-window]].
> - On-call load raised again: to discuss with [[riley-park]].

| | |
|---|---|
| Participants | [[riley-park]], [[devon-hale]], Sam Rivera |
| Context | Weekly [[platform]] sync |

## 📝 Notes

- Replica rehearsal took 34 minutes, under the 40-minute budget.
- Three pages last week, two after midnight.

## ⚖️ Decisions

| Decision | Decider | Link |
|---|---|---|
| Write up two window options before Wednesday | [[riley-park]] | [[database-upgrade-window]] |

## ✅ Actions

Each action lives in the note it belongs to: this table only points to it.

| Action | Owner | Due | Where it lives |
|---|---|---|---|
| Approve the maintenance window proposal | Sam Rivera | {d.isoformat()} | [[database-upgrade]] |
| Confirm the failover test date | Sam Rivera | {self.day(4).isoformat()} | [[single-region-database]] |

## 🚨 {w['Risks']} raised

- [[single-region-database]] stays high until the failover test.
""")
        wk = iso_week(d)
        self.note(f'journal/daily/{d.strftime("%Y")}/{wk}-weekly.md', self.base(f'Week {wk}', d, 'weekly', ['weekly', 'review']), f"""
# Week {wk}

> [!summary] Summary
> - Done: 4 tasks, the main one the wallet button at 10% of traffic.
> - Carried over: 2 tasks, both waiting on someone else.
> - Signal: Platform is overloaded; the database upgrade window must be decided.

## ✅ Done

- Wallet button live for 10% of traffic: [[one-click-payments]]
- Remote build cache on the main repository: [[ci-speedup]]
- Scope frozen with design: [[checkout-revamp]]
- Partner pilot questions answered: [[partner-api-launch]]

## 🚧 Not done (carried over)

| Task | Note | Due | Since |
|---|---|---|---|
| Chase the hosting vendor for the signed agreement | [[eu-data-residency]] | {self.day(-2).isoformat()} | {self.day(-2).isoformat()} |
| Send the revised launch plan to support | [[checkout-revamp]] | {self.day(-1).isoformat()} | {self.day(-1).isoformat()} |

## 🩺 Trends and signals

- [[platform]] is red two weeks in a row; [[devon-hale]] has had no 1-1 for over three weeks.
- [[growth]] is ahead of plan on the [[partner-api-launch]].

## 🏆 Wins and lessons

- The peak load test passed at 6x: [[checkout-peak-traffic]] is mitigated.

## 🎯 Next week: top 3

1. Run the database upgrade: [[database-upgrade]]
2. Fraud rules v2 under 1% false positives: [[fraud-rules-v2]]
3. Sign off the onboarding checklist scope: [[onboarding-checklist]]

## 🔁 Duplicates to tidy

| Task | Notes | Proposal |
|---|---|---|
| None found | | |

## 📎 Annexes

> [!note]- Sources
> - [[{d.isoformat()}]], [[{yd.isoformat()}]], [[{one}]], [[{sd.isoformat()}-team-sync]]
""")

    def inbox(self):
        d = self.d
        self.note('_inbox/idea-status-page-for-partners.md', self.base('Idea: status page for partners', d, 'resource', ['idea'], 'draft'), """
# Idea: status page for partners

- Partners on the API ask us by email when something is slow.
- A public status page per API region would save support time.
- Check with [[harper-lane]] if it fits the [[partner-api-launch]].
""")
        self.note('_inbox/conference-talk-idea.md', self.base('Conference talk idea', self.day(-1), 'resource', ['idea'], 'draft'), """
# Conference talk idea

- "What a weekly release train changed for support": story of [[weekly-release-train]].
- Call for papers closes next month.
""")
        self.note('_inbox/on-call-rota-thought.md', self.base('On-call rota thought', self.day(-3), 'resource', ['capture'], 'draft'), """
# On-call rota thought

- Split night pages between Platform and Checkout for services they own.
- Raise it in the 1-1 with [[riley-park]].
""")

    # ---- engineering pack
    def engineering(self):
        w, d = self.w, self.d
        fri = self.day(-d.weekday() - 3)  # Friday of the previous ISO week
        prev_wk, prev2_wk = iso_week(fri), iso_week(fri - datetime.timedelta(days=7))
        services = [
            ('payment-api', 'checkout', 'critical', '/acme/prod/payment-api', 'payment-api / production', 'level = error', 'GET /health'),
            ('checkout-web', 'checkout', 'critical', '/acme/prod/checkout-web', 'checkout-web / production', 'level = error', 'client aborts'),
            ('auth-service', 'platform', 'critical', '/acme/prod/auth-service', 'auth-service / production', 'level = error', 'none'),
            ('search-indexer', 'growth', 'standard', '/acme/prod/search-indexer', 'search-indexer / production', 'level = error', 'startup banner'),
        ]
        text = self.read('library/services.md')
        head = text.split('## 🩺 Services to monitor')[0]
        rows = '\n'.join(f'| `{s}` | [[{t}]] | `{c}` | `{lg}` | `{ep}` | `{f}` | `{n}` |' for s, t, c, lg, ep, f, n in services)
        self.write('library/services.md', head + f"""## 🩺 Services to monitor

| Service | {w['Team']} | Criticality | Logs (full identifier) | Error project and environment | Error level filter | Known noise to ignore |
|---|---|---|---|---|---|---|
{rows}

## 🧭 Classification hints

Criticality `critical` means a silent service or a new error signature is red. Critical flows:

- Payment capture and refunds (`payment-api`).
- Sign-in and password reset (`auth-service`).

## 📎 Annexes

> [!note]- Out of scope
> - `legacy-reports`: decommissioned, never query it.
""")
        # morning triage
        t = d.isoformat()
        self.note(f'journal/reports/{t}-triage.md', self.base(f'Triage {t}', d, 'report', ['report', 'triage'], 'draft') + [
            ('report_kind', 'triage')], f"""
# 🩺 Triage {t}

🕐 Generated on {dmy(d)} at 08:03

> [!summary] Summary
> - 🟠 2 findings to watch, nothing critical: refund timeouts on payment-api, a new error on the address form.
> - One failing quality gate: fraud-rules, coverage on new code.
> - 1 action proposed.

## 🔴🟠 Findings

| Severity | Project | Finding | Volume and first seen | Likely impact | Next step |
|---|---|---|---|---|---|
| 🟠 | payment-api | Refund calls to the provider time out | 214 events, first seen 02:40 | Refunds delayed, retried later | Check the retry queue with [[checkout]] |
| 🟠 | checkout-web | New TypeError on the address form | 38 events, first seen {dmy(self.day(-1))} 17:12 | Some users re-type their address | Raise at the [[checkout]] stand-up |

## 🩺 Quality gates

| Project | Gate | Reason |
|---|---|---|
| fraud-rules | 🔴 failed | Coverage on new code 61%, required 80% ([[fraud-rules-v2]]) |

## ⚪ Dropped

- 12 known signatures (health checks, client aborts), 1,940 events in total.

## ✅ Actions

{self.task('Check the refund timeout spike on payment-api with [[casey-doe]]', None, ['to-triage'])}

> [!note]- Coverage
> | Source | Items returned | Pages | Truncated | Error |
> |---|---|---|---|---|
> | payment-api / production | 37 | 1 | no | |
> | checkout-web / production | 22 | 1 | no | |
> | auth-service / production | 4 | 1 | no | |
> | search-indexer / production | 9 | 1 | no | |
> | quality: 6 projects | 6 | 1 | no | |

> [!note]- Technical detail
> - payment-api: signature `ProviderTimeout refunds.create`, item 4812, first seen {t} 02:40, filtered on first_seen.
> - checkout-web: signature `TypeError address.postcode`, item 4807, first seen {self.day(-1).isoformat()} 17:12.
""")
        # service health
        self.note(f'journal/reports/{t}-health.md', self.base(f'Service health {t}', d, 'report', ['report', 'health'], 'draft') + [
            ('report_kind', 'health')], f"""
# 🩺 Service health {t}

🕐 Generated on {dmy(d)} at 08:14 · window: last 24 hours

> [!summary] Summary
> - 🟠 1 service to watch: payment-api refund timeouts since 02:40.
> - checkout-web and auth-service healthy.
> - search-indexer not verified: 0 records scanned.

## 🔴🟠 Findings

| Severity | Service | Finding | Volume and start | Likely impact | Next step |
|---|---|---|---|---|---|
| 🟠 | payment-api | Provider timeouts on refunds | 214 errors from 02:40 | Refunds delayed | Already in [[{t}-triage]] |
| ⚪ | search-indexer | No log records overnight | 0 records | Unknown: coverage gap | Check the log group name |

## ⚪ Dropped

- 3 known noise patterns, 6,120 records.

## ✅ Actions

{self.task('Confirm why search-indexer logged nothing overnight', None, ['to-triage'])}

> [!note]- Coverage (4 sources of 4)
> | Service | Log source | Records scanned | Errors | Error project | Status |
> |---|---|---|---|---|---|
> | payment-api | /acme/prod/payment-api | 182,400 | 231 | payment-api | 🟠 |
> | checkout-web | /acme/prod/checkout-web | 96,050 | 12 | checkout-web | 🟢 |
> | auth-service | /acme/prod/auth-service | 41,700 | 3 | auth-service | 🟢 |
> | search-indexer | /acme/prod/search-indexer | 0 | 0 | search-indexer | ⚪ not verified |

> [!note]- Technical detail
> - payment-api: `ProviderTimeout refunds.create`, peak 41 per minute at 03:10.
""")
        blocks = [
            ('payment-api', '🟠 **payment-api**: refund calls to the provider time out since 02:40', ['214 errors overnight, refunds retried later']),
            ('checkout-web', '🟢 **checkout-web**: healthy, 12 known errors', []),
            ('auth-service', '🟢 **auth-service**: healthy, 3 errors, no new signature', []),
            ('search-indexer', '⚪ **search-indexer**: not verified (0 records scanned)', ['A silent service is a coverage gap, not a healthy one']),
        ]
        pulse = self.read('cockpit/pulse.md')
        rx = re.compile(r'<!-- service:example-service -->.*?<!-- /service:example-service -->', re.S)
        if not rx.search(pulse):
            raise DemoError('cockpit/pulse.md: example-service block not found')
        out = []
        for slug, line, bullets in blocks:
            out.append('\n'.join([f'<!-- service:{slug} -->', f'🕐 Updated on {dmy(d)} at 08:14', line] + [f'- {b}' for b in bullets]
                                 + [f'[[{t}-health]]', f'<!-- /service:{slug} -->']))
        self.write('cockpit/pulse.md', rx.sub(lambda m: '\n\n'.join(out), pulse, count=1))
        # delivery digests
        for wk, when, merged, rows, signal, stale in (
            (prev_wk, fri, 41, [('checkout', 18, '21/26', 3, 2, 1), ('platform', 9, '7/16', 3, 2, 4), ('growth', 12, '11/14', 2, 1, 0)],
             '🟠 41 merged PRs; [[platform]] has 4 of 16 sprint items blocked by the database upgrade.', True),
            (prev2_wk, fri - datetime.timedelta(days=7), 37, [('checkout', 15, '19/24', 3, 1, 1), ('platform', 11, '10/15', 3, 1, 1), ('growth', 10, '9/13', 3, 1, 0)],
             f"🟢 37 merged PRs; every {w['team']} delivered most of its sprint.", False)):
            figures = '\n'.join(f'| [[{s}]] | {m} | {sd} | {ip} | {ir} | {b} |' for s, m, sd, ip, ir, b in rows)
            actions = '- None this week.'
            if stale:
                actions = '- None new: the platform blockers are already tracked in [[database-upgrade]].'
            self.note(f'journal/reports/{(when - datetime.timedelta(days=when.weekday())).isoformat()}-delivery.md', self.base(f'Delivery digest {wk}', when, 'report', ['report', 'delivery']) + [
                ('report_kind', 'delivery')], f"""
# 🚧 Delivery digest {wk}

🕐 Generated on {dmy(when)} at 16:04

> [!summary] Summary
> - {signal}
> - Unattributed: 2 merged PRs without an issue key.
> - Stale open PRs: {3 if stale else 1} older than 7 days.

## 📊 Figures

| {w['Team']} | Merged PRs | Sprint done | In progress | In review | Blocked |
|---|---|---|---|---|---|
{figures}
| unattributed | 2 | | | | |
| **Total** | **{merged}** | | | | |

## 🚧 Blocked and in review

| Item | {w['Team']} | State | Age |
|---|---|---|---|
| PLT-88 database upgrade | [[platform]] | Blocked: no window | 9 days |
| CHK-431 scored fraud rules | [[checkout]] | In review | 4 days |

## 👥 Load per {w['person']} (signals, not verdicts)

| {w['Person']} | PRs authored | Reviews | Open items | Talking point |
|---|---|---|---|---|
| [[avery-quinn]] | 6 | 11 | 3 | Review load building up? |
| [[devon-hale]] | 2 | 4 | 7 | Too many open items at once? |

PR counts do not measure value.

## 🚧 {w['Workstreams']}

| {w['Workstream']} | Progress | Blocker | Next step | Proposed RAG | Refresh |
|---|---|---|---|---|---|
| [[one-click-payments]] | 60 | | Raise to 50% of traffic | 🟢 | updated |
| [[fraud-rules-v2]] | 35 | False positives 4% | Tune the rules | 🟠 | updated |
| [[database-upgrade]] | 20 | No window | Approve the window | 🔴 | updated |
| [[ci-speedup]] | 80 | | Roll out the cache | 🟢 | updated |
| [[onboarding-checklist]] | 45 | Step 3 events | Sign off scope | 🟠 | unchanged |
| [[referral-programme]] | 10 | | Reward rules | ⚪ | not verified |

6 {w['workstreams']}: 4 updated, 1 unchanged, 1 not verified

## ✅ Actions

{actions}

> [!note]- Sources and coverage
> - code: merged PRs, limit 100, {merged} returned, not truncated.
> - tracker: 3 boards, 1 page each, not truncated.
""")
        self.replace_block('cockpit/delivery.md', '<!-- delivery -->', '<!-- /delivery -->', f"""
🕐 Updated on {dmy(fri)} at 16:04
🟠 **Week {prev_wk}**: 41 merged PRs, Platform half blocked by the database upgrade.
- [[checkout]]: 18 merged, sprint 21/26 done, 1 blocked
- [[platform]]: 9 merged, sprint 7/16 done, 4 blocked
- [[growth]]: 12 merged, sprint 11/14 done, 0 blocked
- Report: [[{(fri - datetime.timedelta(days=fri.weekday())).isoformat()}-delivery]]
""")
        # debt review and its area note
        dt = fri.isoformat()
        self.note(f'journal/reports/{dt}-debt.md', self.base(f'Debt review {dt}', fri, 'report', ['report', 'debt'], 'draft') + [
            ('report_kind', 'debt')], f"""
# 🧱 Debt review {dt}

🕐 Generated on {dmy(fri)} at 10:06

> [!summary] Summary
> - 🟠 2 critical dependency alerts older than 30 days, both on payment-api.
> - Trend: blocker and critical issues down from 14 to 11.
> - One failing gate: fraud-rules.

## 📊 Figures

| Project or repository | Gate | Blocker/critical issues | Critical/high alerts | Oldest alert | Change |
|---|---|---|---|---|---|
| payment-api | 🟢 passed | 4 | 2 | 41 days | -2 |
| checkout-web | 🟢 passed | 3 | 1 | 12 days | -1 |
| fraud-rules | 🔴 failed | 2 | 0 | | +1 |
| auth-service | 🟢 passed | 2 | 0 | | -1 |

## 🔴🟠 Top 5 to act on

| Item | Where | Severity | Why now |
|---|---|---|---|
| Outdated HTTP client with a known flaw | payment-api | critical | Critical flow, alert 41 days old |
| Outdated XML parser | payment-api | high | Same service, easy upgrade |
| Coverage on new code 61% | fraud-rules | gate | Blocks the [[fraud-rules-v2]] release |
| Duplicated validation code | checkout-web | major | Touched by [[checkout-revamp]] |
| Deprecated token library | auth-service | major | End of support next quarter |

## ✅ Actions

- None new: the payment-api alerts were already raised last week.

> [!note]- Coverage
> | Source | Items returned | Pages | Truncated | Error |
> |---|---|---|---|---|
> | quality: 4 projects | 4 | 1 | no | |
> | code alerts: 4 repositories | 9 | 1 | no | |
""")
        self.note('work/areas/technical-debt.md', self.base('Technical debt', self.day(-60), 'area', ['area']) + [
            ('owner', ''), ('team', '')], f"""
# Technical debt

## 🎯 Responsibility

- Keep critical services free of critical alerts older than 30 days, and every quality gate green.

## 🩺 Health

| Signal | State | Note |
|---|---|---|
| Overall | 🟠 | Two old alerts on payment-api |

## 📝 Notes

- Refreshed every Friday by the debt review.

<!-- debt-review -->
🕐 Updated on {dmy(fri)} at 10:06
🟠 2 critical dependency alerts older than 30 days, both on payment-api.
- Outdated HTTP client (payment-api)
- Outdated XML parser (payment-api)
- Coverage on new code (fraud-rules)
- Duplicated validation code (checkout-web)
- Deprecated token library (auth-service)

[[{dt}-debt]]
<!-- /debt-review -->
""")

    # ---- product pack
    def product(self):
        w, d = self.w, self.d
        i1, i2 = f'{self.day(-9).isoformat()}-small-business-1', f'{self.day(-4).isoformat()}-agency-2'
        self.note(f'library/interviews/{i1}.md', self.base(f'Interview {self.day(-9).isoformat()}, small business, participant 1', self.day(-9),
                                                           'interview', ['interview']) + [
            ('customer_segment', 'small business, monthly plan'), ('interview_date', self.day(-9)), ('source', 'call')], f"""
# Interview {self.day(-9).isoformat()}, small business, participant 1

> Anonymised: use a segment and a pseudonym, never a name or contact detail.

## 💬 Quotes

- "I gave up on setup twice before I found the invoice settings." (Participant 1, first week)
- "At the end of the month I download every report by hand." (Participant 1, month-end)

## 😣 Pains

- Setup has no clear order; invoice settings are hard to find.
- Month-end exports take about an hour.

## 🎯 Jobs to be done

- When I sign up, I want to know the next step, so I can send my first invoice the same day.

## 😮 Surprises

- Never opened the help centre: expected the product to guide them.

## 🔗 Opportunities

- [[guided-setup-wizard]]
- [[bulk-export-for-admins]]
""")
        self.note(f'library/interviews/{i2}.md', self.base(f'Interview {self.day(-4).isoformat()}, agency, participant 2', self.day(-4),
                                                           'interview', ['interview']) + [
            ('customer_segment', 'agency, annual plan'), ('interview_date', self.day(-4)), ('source', 'call')], f"""
# Interview {self.day(-4).isoformat()}, agency, participant 2

> Anonymised: use a segment and a pseudonym, never a name or contact detail.

## 💬 Quotes

- "Adding a new colleague means three emails and a call." (Participant 2, onboarding staff)
- "We pay with the same card every time, why ask again?" (Participant 2, renewal)

## 😣 Pains

- Inviting colleagues is slow; no shareable link.
- Card details re-typed at each renewal.

## 🎯 Jobs to be done

- When a new colleague joins, I want to share one link, so they are set up in minutes.

## 🔗 Opportunities

- [[team-invitations-by-link]]
- [[saved-payment-methods]]
- [[guided-setup-wizard]]
""")
        opps = [
            ('guided-setup-wizard', 'Guided setup wizard', 'validated', 'I gave up on setup twice before I found the invoice settings.',
             [i1, i2], 1200, 2, 0.8, 4, 'new accounts per quarter', 'onboarding-checklist'),
            ('team-invitations-by-link', 'Team invitations by link', 'candidate', 'Adding a new colleague means three emails and a call.',
             [i2], 600, 0.5, 0.8, 2, 'accounts adding a user per quarter', ''),
            ('saved-payment-methods', 'Saved payment methods', 'validated', 'We pay with the same card every time, why ask again?',
             [i2], 900, 1, 0.8, 6, 'renewals per quarter', 'one-click-payments'),
            ('bulk-export-for-admins', 'Bulk export for admins', 'candidate', 'At the end of the month I download every report by hand.',
             [i1], 400, 1, 0.5, 3, 'admins exporting monthly', ''),
        ]
        ranked = []
        for slug, title, stage, problem, ev, reach, impact, conf, effort, basis, link in opps:
            score = round(reach * impact * conf / effort, 2)
            score = int(score) if score == int(score) else score
            ranked.append((score, slug, reach, impact, conf, effort, stage, len(ev)))
            self.note(f'work/opportunities/{slug}.md', self.base(title, self.day(-8), 'opportunity', ['opportunity']) + [
                ('problem', problem), ('evidence', [f'[[{e}]]' for e in ev]), ('reach', reach), ('impact', impact),
                ('confidence', conf), ('effort', effort), ('score', score), ('stage', stage)], f"""
# {title}

## 🎯 Problem

- "{problem}"

## 📊 Scoring inputs

| Input | Value | Basis |
|---|---|---|
| Reach | {reach} | {basis} |
| Impact | {impact} | 0.25, 0.5, 1, 2 or 3 |
| Confidence | {conf} | {len(ev)} interview(s) |
| Effort | {effort} | person-weeks, rough estimate |

## 💬 Evidence

""" + '\n'.join(f'- [[{e}]]' for e in ev) + """

## ⚖️ Decisions

- None yet.

## 🔗 Links

- """ + (f"{w['Workstream']}: [[{link}]]" if link else f"{w['Workstream']}: none yet"))
        ranked.sort(key=lambda r: (-r[0], r[1] != 'saved-payment-methods'))  # tie: the order proposed in the tie note
        rows = '\n'.join(f'| {i} | [[{s}]] | {sc} | {r} | {im} | {c} | {e} | {st} | {n} interview(s) |'
                         for i, (sc, s, r, im, c, e, st, n) in enumerate(ranked, 1))
        self.replace_block('cockpit/roadmap.md', '<!-- ranking:start -->', '<!-- ranking:end -->', f"""
🕐 Updated on {dmy(self.day(-1))} at 17:20

Method: **RICE** = reach x impact x confidence / effort.

| # | Opportunity | Score | Reach | Impact | Confidence | Effort | Stage | Evidence |
|---|---|---|---|---|---|---|---|---|
{rows}

## Tie notes

- [[saved-payment-methods]] and [[team-invitations-by-link]] tie at 120. Invitations cost a third of the effort; saved payments has the stronger evidence and fits [[one-click-payments]]. Proposed order: saved payments first.

> [!note]- Inputs and gaps
> - Every candidate and validated opportunity has complete inputs.
> - [[bulk-export-for-admins]] rests on a single interview: confidence kept at 0.5.
""")
        roadmap = self.read('cockpit/roadmap.md')
        cut = roadmap.find('## ⏩ Now')
        if cut < 0:
            raise DemoError('cockpit/roadmap.md: "## ⏩ Now" section not found')
        self.write('cockpit/roadmap.md', roadmap[:cut] + """## ⏩ Now

- [[onboarding-checklist]]: guided setup, first slice of [[guided-setup-wizard]]
- [[one-click-payments]]: wallet button rollout

## 🔜 Next

- [[saved-payment-methods]]
- [[team-invitations-by-link]]

## 🔭 Later

- [[bulk-export-for-admins]]
- [[referral-programme]] rewards
""")
        self.created.remove('cockpit/roadmap.md')  # counted once
        # PRD next to its initiative
        self.note('work/workstreams/growth/onboarding-checklist-prd.md', self.base('Onboarding checklist PRD', self.day(-14), 'resource', ['prd']), f"""
# Onboarding checklist PRD

🕐 Updated on {dmy(self.day(-3))} at 15:40

> [!summary] Summary
> - Problem: new admins do not know the next setup step; 41% never send a first invoice.
> - Goal: first invoice within 7 days for 55% of new accounts (from 41%).
> - Open question: do we gate the checklist behind the plan choice?

## 🎯 Problem

- New admins stall between sign-up and their first invoice: [[{i1}]], [[{i2}]].

## 👥 Users

- Segment: admins of new small business and agency accounts.

## 🎯 Goals and non-goals

| Goals | Non-goals |
|---|---|
| First invoice sent in the first week | Redesigning the invoice editor |
| Admins invite their team during setup | Mobile setup |

## ✅ Requirements

| # | Requirement | Priority | Acceptance criterion |
|---|---|---|---|
| R1 | A five-step checklist on the home page | must | Visible to every new admin until done |
| R2 | Each step deep-links to the right setting | must | One click from the checklist |
| R3 | Progress events for each step | must | Events visible in analytics the same day |
| R4 | Dismiss and restore the checklist | should | Restored from the help menu |

## 📊 Metrics

| Metric | Baseline | Target | Source |
|---|---|---|---|
| Primary: first invoice within 7 days | 41% | 55% | analytics, weekly cohort |
| Guardrail: support tickets about setup | 120 per week | no increase | support tool |

## ❓ Open questions

- Gate the checklist behind the plan choice, or show it first?

## 🚨 {w['Risks']}

- Step 3 events are missing: the primary metric cannot be read yet.

## 🔗 Links

- {w['Workstream']}: [[onboarding-checklist]]
- Opportunity: [[guided-setup-wizard]]
""")
        # product weekly: written on Monday for the previous ISO week
        mon = self.day(-d.weekday())
        pw = iso_week(mon - datetime.timedelta(days=1))
        self.note(f'journal/reports/{(mon - datetime.timedelta(days=7)).isoformat()}-product-weekly.md', self.base(f'Product weekly {pw}', mon, 'report', ['report']) + [
            ('report_kind', 'product-weekly')], f"""
# 📦 Product weekly {pw}

🕐 Generated on {dmy(mon)} at 09:05

> [!summary] Summary
> - Shipped: wallet button to 10% of traffic, checklist UI behind a flag.
> - Main risk: step 3 analytics events missing on [[onboarding-checklist]].
> - Decision needed: [[database-upgrade-window]] (blocks EU data residency).

## ✅ Shipped

| {w['Workstream']} | Item | Tracker |
|---|---|---|
| [[one-click-payments]] | Wallet button for 10% of traffic | CHK-412 |
| [[onboarding-checklist]] | Checklist UI behind a flag | GRW-57 |

## 🚧 In progress

| {w['Workstream']} | Item | Tracker |
|---|---|---|
| [[fraud-rules-v2]] | Scored rules in shadow mode | CHK-430 |
| [[referral-programme]] | Reward rules | GRW-63 |

## 🚨 Blocked

| {w['Workstream']} | Item | Tracker |
|---|---|---|
| [[onboarding-checklist]] | Step 3 analytics events | GRW-59 |

## 📊 Metric movements

| Metric | This week | Previous | Change | Note |
|---|---|---|---|---|
| First invoice within 7 days | 42% | 41% | +1 pt | Coincides with the checklist flag at 5% |
| Checkout conversion | 63.1% | 62.4% | +0.7 pt | Coincides with the wallet button |
| Setup support tickets | 114 | 120 | -6 | |

## ⚖️ Decisions needed

- [[database-upgrade-window]]: to decide by {self.day(2).isoformat()}.

## 🩺 Proposed health

| {w['Workstream']} | Proposed | Reason |
|---|---|---|
| [[one-click-payments]] | 🟢 | Rollout on plan |
| [[onboarding-checklist]] | 🟠 | Primary metric not readable yet |
| [[referral-programme]] | ⚪ | No tracker activity this week |

## ✅ Actions

{self.task('Ask [[harper-lane]] whether the step 3 events can ship this sprint', None, ['to-triage'])}

## 📎 Annexes

> [!note]- Sources and raw data
> - tracker: 6 {w['workstreams']}, 1 page each, not truncated.
> - analytics: weekly cohorts, not sampled.
""")

    # ---- cockpit/today.md, as the today skill writes it
    def today_page(self):
        d = self.d
        triage = (2 if self.eng else 0) + (1 if self.prod else 0)
        text = self.read('cockpit/today.md')
        fm = re.match(r'---\n.*?\n---\n', text, re.S).group(0)
        fm = re.sub(r'^date: .*$', f'date: {d.isoformat()}', fm, flags=re.M)
        self.write('cockpit/today.md', fm + f"""
# 📅 Today

🕐 Updated on {dmy(d)} at 08:42

> [!summary] Priorities of the day
> 1. Decide the database upgrade window before the 14:00 review: [[database-upgrade-window]]
> 2. Unblock EU data residency, the signed agreement is 2 days late: [[eu-data-residency]]
> 3. Send the revised launch plan to support (overdue): [[checkout-revamp]]

## 📅 Agenda

| Time | Meeting | Topic / preparation |
|---|---|---|
| 09:30 | Checkout stand-up | [[checkout]] |
| 11:00 | 1-1 with [[riley-park]] | On-call load: start there |
| 14:00 | Database upgrade window review | [[database-upgrade-window]]: choose A or B |
| 16:00 | Product review | [[onboarding-checklist]] scope |

## 🔴 Overdue

| Task | Note | Due |
|---|---|---|
| Chase the hosting vendor for the signed agreement | [[eu-data-residency]] | {self.day(-2).isoformat()} |
| Send the revised launch plan to support | [[checkout-revamp]] | {self.day(-1).isoformat()} |

📥 {triage} tasks to triage: see [[my-work]].
""")


# ----------------------------------------------------------------------------- Obsidian
def seed_obsidian(vault, tasks_dir):
    obs = os.path.join(vault, '.obsidian')
    os.makedirs(obs, exist_ok=True)
    install.jdump(os.path.join(obs, 'bookmarks.json'), {'items': [{'type': 'file', 'ctime': 0, 'path': 'cockpit.md', 'title': 'Cockpit'}]})
    if not tasks_dir:
        return False
    src = os.path.abspath(os.path.expanduser(tasks_dir))
    for f in ('main.js', 'manifest.json'):
        if not os.path.isfile(os.path.join(src, f)):
            raise DemoError(f'--tasks-plugin-dir: {f} not found in {src}')
    with open(os.path.join(src, 'manifest.json'), encoding='utf-8') as fh:
        if json.load(fh).get('id') != TASKS_ID:
            raise DemoError(f'--tasks-plugin-dir: {src} is not the Tasks plugin (manifest id is not {TASKS_ID})')
    dst = os.path.join(obs, 'plugins', TASKS_ID)
    os.makedirs(dst, exist_ok=True)
    for f in ('main.js', 'manifest.json', 'styles.css'):
        if os.path.isfile(os.path.join(src, f)):
            shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))  # read-only on the source folder
    cp = os.path.join(obs, 'community-plugins.json')
    plugins = install.jload(cp) if os.path.isfile(cp) else []
    if TASKS_ID not in plugins:
        plugins.append(TASKS_ID)
    install.jdump(cp, plugins)
    return True


# ----------------------------------------------------------------------------- main
def build(out, packs=SUPPORTED_PACKS, day=None, force=False, tasks_dir=None):
    out = os.path.abspath(os.path.expanduser(out))
    packs = list(packs)
    unknown = [p for p in packs if p not in SUPPORTED_PACKS]
    if not packs or unknown:
        raise DemoError(f'--packs: choose among {", ".join(SUPPORTED_PACKS)} (got {", ".join(packs) or "nothing"})')
    day = day or datetime.date.today()
    prepare_out(out, force)
    answers = answers_for(out, packs)
    report = install.install(answers, log=lambda *a: None)
    words = render.build_table(install.vocab_files(REPO, packs, install.resolve_packs(REPO)), answers)
    created = Demo(out, day, packs, words).build()
    tasks = seed_obsidian(out, tasks_dir)
    return {'vault': out, 'installed': report['created'], 'notes': sorted(set(created)), 'tasks_plugin': tasks}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True, help='folder of the demo vault (created; must be empty unless --force)')
    ap.add_argument('--packs', default=','.join(SUPPORTED_PACKS), help='comma separated, among engineering,product')
    ap.add_argument('--date', help='the "today" of the demo, YYYY-MM-DD (default: today)')
    ap.add_argument('--force', action='store_true', help='delete --out first, only if it is a control tower vault')
    ap.add_argument('--tasks-plugin-dir', help='an installed obsidian-tasks-plugin folder to copy (never downloaded)')
    args = ap.parse_args()
    try:
        day = datetime.date.fromisoformat(args.date) if args.date else None
    except ValueError:
        ap.error('--date must be YYYY-MM-DD')
    try:
        res = build(args.out, [p.strip() for p in args.packs.split(',') if p.strip()], day, args.force, args.tasks_plugin_dir)
    except (DemoError, install.InstallError, render.RenderError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(2)
    print(f"Demo vault: {res['vault']}")
    print(f"Installer: {res['installed']} files; demo notes written: {len(res['notes'])}")
    if res['tasks_plugin']:
        print('Tasks plugin: copied and enabled (Obsidian asks once to trust the vault and turn on community plugins).')
    else:
        print('Tasks plugin: not installed. In Obsidian: Settings > Community plugins > Browse > "Tasks" > Install > Enable,'
              ' or re-run with --tasks-plugin-dir <an installed obsidian-tasks-plugin folder>.')
    print('Next: open this folder as a vault in Obsidian (Open folder as vault), then open cockpit.md.')


if __name__ == '__main__':
    main()
