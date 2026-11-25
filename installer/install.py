#!/usr/bin/env python3
"""Control tower installer. Standard library only (Python 3.9+).

Installs the core vault, the chosen packs, the tool adapter notes, the scheduled jobs and (optionally)
the schedule, from an answers file or an interactive terminal wizard.

    python3 installer/install.py --answers answers.json --dry-run     # show what would happen
    python3 installer/install.py --answers answers.json               # install
    python3 installer/install.py --interactive                        # answer questions in the terminal

Safety:
  * it never overwrites an existing file; re-running is safe (existing files are kept);
  * it never edits your Claude Code or MCP configuration: the commands to run are written to
    <vault>/library/setup-next-steps.md;
  * it never loads a schedule unless --apply-schedule is given;
  * it seeds .obsidian/ only when the folder does not exist yet.
"""
import argparse
import datetime
import hashlib
import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys

if sys.version_info < (3, 9):
    sys.exit('control tower needs Python 3.9 or newer (found %s)' % sys.version.split()[0])
import zoneinfo  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render  # noqa: E402

REPO = os.path.dirname(HERE)
VERSION = '0.1.0'
CAPABILITIES = ['calendar', 'tracker', 'code', 'errors', 'quality', 'logs', 'analytics', 'crm']
DAYS = {'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6, 'sun': 0}
BASE_ALLOW = ['Read', 'Grep', 'Glob', 'Bash(date)', 'Bash(date:*)', 'Bash(ls:*)']
BASE_DENY = ['Agent']
PROTECTED_DIRS = ('.claude', '.control-tower', '.obsidian', '_system/templates', '_system/dashboards', '.git', '.github', '.vscode')
PROTECTED_FILES = ('CLAUDE.md', 'CLAUDE.local.md', '.mcp.json')
DAY_ALIASES = {'weekdays': 'mon-fri', 'weekends': 'sat-sun', 'daily': 'mon-sun', 'every day': 'mon-sun', '*': 'mon-sun'}
GUARD_MATCHER = 'Bash|Read|Edit|Write|MultiEdit|NotebookEdit|Grep|Glob'


class InstallError(Exception):
    pass


# ----------------------------------------------------------------------------- helpers
def jload(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def jdump(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write('\n')


def expand(path):
    return os.path.abspath(os.path.expanduser(path))


def list_packs(repo=REPO):
    base = os.path.join(repo, 'packs')
    return sorted(d for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, 'pack.json'))) if os.path.isdir(base) else []


def list_tools(capability, repo=REPO):
    d = os.path.join(repo, 'adapters', capability)
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith('.json')) if os.path.isdir(d) else []


# ----------------------------------------------------------------------------- answers
def default_answers(repo=REPO):
    return {
        'owner_name': 'Your Name', 'owner_handle': 'me', 'timezone': 'UTC',
        'vault_path': '~/control-tower-vault', 'ct_home': '~/.control-tower',
        'packs': [], 'tools': {}, 'jobs': {}, 'scheduler': 'auto', 'claude_bin': 'claude',
    }


def validate(answers, repo=REPO):
    errors = []
    for key in ('owner_name', 'owner_handle', 'timezone', 'vault_path', 'packs'):
        if not answers.get(key):
            errors.append(f'answers: "{key}" is required')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', str(answers.get('owner_handle', 'x'))):
        errors.append('answers: "owner_handle" may only contain letters, digits, ".", "_" and "-"')
    tz = str(answers.get('timezone', ''))
    try:
        zoneinfo.ZoneInfo(tz)
    except Exception:
        errors.append(f'answers: unknown timezone "{tz}" (use an IANA name such as Europe/Paris)')
    available = list_packs(repo)
    for p in answers.get('packs', []):
        if p not in available:
            errors.append(f'answers: unknown pack "{p}" (available: {", ".join(available)})')
    for cap, tool in (answers.get('tools') or {}).items():
        if cap not in CAPABILITIES:
            errors.append(f'answers: unknown capability "{cap}"')
        elif tool != 'none' and tool not in list_tools(cap, repo):
            errors.append(f'answers: no adapter "{tool}" for capability "{cap}" (available: {", ".join(list_tools(cap, repo))}, none)')
    if answers.get('scheduler', 'auto') not in ('auto', 'launchd', 'cron', 'none'):
        errors.append('answers: "scheduler" must be auto, launchd, cron or none')
    if not isinstance(answers.get('packs', []), list):
        errors.append('answers: "packs" must be a list, for example ["marketing"]')
    if not isinstance(answers.get('tools') or {}, dict):
        errors.append('answers: "tools" must be an object, for example {"calendar": "google-calendar"}')
    jobs = answers.get('jobs') or {}
    if not isinstance(jobs, dict):
        errors.append('answers: "jobs" must be an object, for example {"morning-prs": {"time": "07:15"}}')
        jobs = {}
    for jid, cfg in jobs.items():
        if not isinstance(cfg, dict):
            errors.append(f'answers: job "{jid}" must be an object such as {{"time": "07:15", "days": "mon-fri"}}')
            continue
        t = cfg.get('time')
        if t is not None and not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', str(t)):
            errors.append(f'answers: job "{jid}" time must be HH:MM')
        if cfg.get('days') is not None:
            try:
                parse_days(str(cfg['days']))
            except ValueError as exc:
                errors.append(f'answers: job "{jid}": {exc}')
    if errors:
        raise InstallError('\n'.join(errors))


def wizard(repo=REPO, ask=input, out=print):
    """Terminal wizard returning an answers dict. `ask` and `out` are injectable for tests."""
    a = default_answers(repo)
    out('Control tower installer: answer a few questions (Enter keeps the default).\n')
    def q(prompt, default):
        v = ask(f'{prompt} [{default}]: ').strip()
        return v or default
    a['owner_name'] = q('Your name', a['owner_name'])
    a['owner_handle'] = q('Handle used on your tasks', a['owner_handle'])
    a['timezone'] = q('Timezone (IANA name)', a['timezone'])
    a['vault_path'] = q('Vault folder (created if needed)', a['vault_path'])
    packs = list_packs(repo)
    out('\nProfiles: ' + ', '.join(packs))
    a['packs'] = [p.strip() for p in q('Profiles to install (comma separated)', packs[0] if packs else '').split(',') if p.strip()]
    asked = set()
    for pid in a['packs']:
        manifest = jload(os.path.join(repo, 'packs', pid, 'pack.json'))
        for item in manifest.get('questions', []):
            if item['capability'] in asked:
                continue
            asked.add(item['capability'])
            choices = item['choices']
            a['tools'][item['capability']] = q(f"{item['ask']} ({', '.join(choices)})", 'none' if 'none' in choices else choices[0])
    a['scheduler'] = q('Scheduler (auto, launchd, cron, none)', 'auto')
    return a


# ----------------------------------------------------------------------------- plan
def vocab_files(repo, packs):
    files = [os.path.join(repo, 'core', 'vocabulary.json')]
    for p in packs:
        manifest = jload(os.path.join(repo, 'packs', p, 'pack.json'))
        files.append(os.path.join(repo, 'packs', p, manifest['vocabulary']))
    return files


def static_collisions(repo, packs):
    """Files that two sources would write to the same place (a pack colliding with the core or another pack)."""
    seen, clash = {}, []
    def walk(src, label):
        for root, _, files in os.walk(src):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), src)
                rel = rel[:-5] if rel.endswith('.tmpl') else rel
                if rel.endswith('.gitkeep'):
                    continue
                if rel in seen:
                    clash.append(f'{rel} ({seen[rel]} and {label})')
                seen[rel] = label
    walk(os.path.join(repo, 'core', 'vault'), 'core')
    for p in packs:
        v = os.path.join(repo, 'packs', p, 'vault')
        if os.path.isdir(v):
            walk(v, 'pack ' + p)
    return clash


def job_capabilities(meta):
    """(required, optional) capabilities of a job. A plain list means every capability is required."""
    caps = meta.get('capabilities', [])
    if isinstance(caps, dict):
        return list(caps.get('required', [])), list(caps.get('optional', []))
    return list(caps), []


def eligible_jobs(repo, packs, tools):
    """Jobs whose capabilities all have a chosen tool."""
    jobs = []
    for p in packs:
        manifest = jload(os.path.join(repo, 'packs', p, 'pack.json'))
        for j in manifest.get('jobs', []):
            meta = jload(os.path.join(repo, 'packs', p, 'jobs', j, 'job.json'))
            req, opt = job_capabilities(meta)
            missing = [c for c in req if tools.get(c, 'none') == 'none']
            if not missing and not req and opt and not meta.get('vault_only') and all(tools.get(c, 'none') == 'none' for c in opt):
                missing = ['one of ' + ' / '.join(opt)]
            jobs.append({'pack': p, 'id': j, 'meta': meta, 'missing': missing})
    return jobs


def read_routine(path):
    """Split a routine file into its frontmatter (dict) and the prompt (text under '## Prompt')."""
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    m = re.match(r'---\n(.*?)\n---\n', text, re.S)
    if not m or '\n## Prompt\n' not in text:
        raise InstallError(f'{path}: a routine needs a frontmatter and a "## Prompt" section')
    meta = {}
    for line in m.group(1).split('\n'):
        k, _, v = line.partition(':')
        v = v.strip()
        if v.startswith('[') and v.endswith(']'):
            v = [x.strip() for x in v[1:-1].split(',') if x.strip()]
        elif len(v) >= 2 and v[0] == v[-1] == '"':
            v = v[1:-1]
        meta[k.strip()] = v
    return meta, text.split('\n## Prompt\n', 1)[1].strip() + '\n'


def eligible_routines(repo, packs, tools):
    """Cloud routines of the chosen packs; a routine is offered only if its required connectors have a tool."""
    out = []
    for p in packs:
        for rid in jload(os.path.join(repo, 'packs', p, 'pack.json')).get('routines', []):
            meta, prompt = read_routine(os.path.join(repo, 'packs', p, 'routines', rid + '.md'))
            missing = [c for c in meta.get('connectors_required', []) if tools.get(c, 'none') == 'none']
            out.append({'pack': p, 'id': rid, 'meta': meta, 'prompt': prompt, 'missing': missing})
    return out


def routine_cron(days, hhmm):
    """Cron expression in the user's own timezone (the routine is created with that timezone)."""
    h, m = map(int, hhmm.split(':'))
    return f"{m} {h} * * {','.join(str(d) for d in parse_days(days))}"


def adapter_doc(repo, capability, tool):
    with open(os.path.join(repo, 'adapters', capability, 'contract.md'), encoding='utf-8') as fh:
        contract = fh.read()
    with open(os.path.join(repo, 'adapters', capability, tool + '.md'), encoding='utf-8') as fh:
        doc = fh.read()
    return (f'<!-- Installed by control-tower {VERSION}: capability {capability}, tool {tool}. '
            f'Jobs and skills read this file to know how to query the tool. -->\n\n'
            f'# {capability.capitalize()} adapter: {tool}\n\n## Contract\n\n{contract}\n\n---\n\n{doc}\n')


def next_steps(repo, answers, jobs_on, jobs_off, routines=()):
    lines = ['---', 'title: "Setup next steps"', f'date: {datetime.date.today().isoformat()}', 'tags: [setup]',
             'type: resource', 'status: active', '---', '', '# Setup next steps', '',
             'The installer created your vault, jobs and notes. A few things must be done by you, because they change your own '
             'Claude Code or Obsidian configuration, which the installer never touches.', '',
             '## 1. Obsidian', '',
             '- Open this folder as a vault in Obsidian.',
             '- Settings > Community plugins > turn on community plugins, then install **Tasks** (required by the dashboards).',
             '- Settings > Core plugins: make sure **Bases**, **Templates** and **Daily notes** are enabled.',
             '- Optional: install **Iconize** for folder icons.', '',
             '## 2. Connect your tools', '']
    any_tool = False
    for cap, tool in sorted((answers.get('tools') or {}).items()):
        if tool == 'none':
            continue
        any_tool = True
        man = jload(os.path.join(repo, 'adapters', cap, tool + '.json'))
        lines += [f'### {cap}: {tool}', '', f"Official documentation: {man['setup_url']}", '']
        if man.get('install'):
            lines += ['Run once in a terminal:', '', '```bash'] + man['install'] + ['```', '']
        if man.get('env'):
            lines += ['Environment variables to set: ' + ', '.join(f'`{e}`' for e in man['env']), '']
        if not man.get('read_only', True):
            lines += [f"> Read-only caution: {man.get('read_only_mitigation', '')}", '']
        if man.get('access') == 'mcp' and not man.get('permissions_allow'):
            lines += ['> Unattended jobs refuse every tool that is not allowed. After connecting, run `/mcp`, review the tool list, then add the '
                      f'READ-ONLY tool names to your answers file under `"permissions": {{"{cap}": ["mcp__<server>__<tool>"]}}` and re-run the installer.', '']
        lines += [f"Check the connection: {man['verify']}", '']
    if not any_tool:
        lines += ['No external tool was selected: the vault works on its own.', '']
    lines += ['## 3. Scheduled jobs', '']
    if jobs_on:
        lines += ['Installed jobs: ' + ', '.join(f"`{j['id']}`" for j in jobs_on) + '. Test one by hand with:', '',
                  '```bash', f"python3 {answers['ct_home']}/bin/run_job.py --job {jobs_on[0]['id']} --ct-home {answers['ct_home']}", '```', '']
    for j in jobs_off:
        lines.append(f"- `{j['id']}` was not installed: no tool chosen for {', '.join(j['missing'])}.")
    lines += ['', '## 4. Cloud routines (optional)', '']
    if routines:
        lines += ['Cloud routines run on claude.ai, even when your computer is off. Most of them write notes, so they need this vault '
                  'in a GitHub repository attached to the routine. Available for your answers:', '',
                  '| Routine | When |', '|---|---|'] + [f"| {r['name']} | {r['days']} at {r['time']} |" for r in routines] + [
                  '', 'To create them, start Claude Code in the control tower repository and run `/install-control-tower routines`: '
                  'it proposes each routine and creates only the ones you accept. Or paste a prompt by hand from '
                  f"`{answers['ct_home']}/routines/<name>.prompt.md` into a new routine on claude.ai.", '']
    else:
        lines += ['No cloud routine is available for the tools you chose.', '']
    lines += [
              '## 5. Health check', '', '```bash', f"python3 {shlex.quote(os.path.join(repo, 'installer', 'doctor.py'))} --vault {shlex.quote(answers['vault_path'])} --ct-home {shlex.quote(answers['ct_home'])}", '```', '']
    return '\n'.join(lines)


def obsidian_seed(vault):
    cfg = os.path.join(vault, '.obsidian')
    if os.path.exists(cfg):
        return []
    files = {
        'app.json': {'attachmentFolderPath': '_system/attachments', 'newFileLocation': 'folder', 'newFileFolderPath': '_inbox',
                     'alwaysUpdateLinks': True, 'userIgnoreFilters': ['_system/attachments/', '_system/archive/', '.claude/']},
        'daily-notes.json': {'folder': 'journal/daily', 'format': 'YYYY/YYYY-MM-DD', 'template': '_system/templates/daily'},
        'templates.json': {'folder': '_system/templates'},
        'core-plugins.json': {'file-explorer': True, 'global-search': True, 'switcher': True, 'graph': True, 'backlink': True,
                              'outgoing-link': True, 'tag-pane': True, 'properties': True, 'page-preview': True,
                              'daily-notes': True, 'templates': True, 'command-palette': True, 'bases': True, 'outline': True},
    }
    for name, data in files.items():
        jdump(os.path.join(cfg, name), data)
    return ['.obsidian/' + n for n in files]


# ----------------------------------------------------------------------------- jobs and schedule
def abs_rule(tool, path):
    """Permission rule for an absolute path: Claude Code reads `//abs/path` as absolute, `/path` as relative to the settings file."""
    return f'{tool}(/{path})' if path.startswith('/') else f'{tool}({path})'


def fix_rule(rule):
    """Upgrade `Edit(/abs/...)` written by a pack to the absolute form `Edit(//abs/...)`."""
    m = re.fullmatch(r'(Edit|Write|Read|MultiEdit)\((/[^/].*)\)', rule)
    return f'{m.group(1)}(/{m.group(2)})' if m else rule


def job_settings(repo, answers, job):
    vault = expand(answers['vault_path'])
    req, opt = job_capabilities(job['meta'])
    allow = list(BASE_ALLOW) + [abs_rule('Edit', f'{vault}/**')]  # every job writes its report in the vault
    allow += [fix_rule(render.render_text(p, {'vault_path': vault}, job['id'], [])) for p in job['meta']['permissions'].get('allow', [])]
    deny = list(BASE_DENY) + [fix_rule(p) for p in job['meta']['permissions'].get('deny', [])]
    deny += ['Read(**/.env*)', 'Read(**/.ssh/**)', 'Read(**/.aws/**)', 'Read(**/.gnupg/**)', 'Read(**/*credentials*)', 'Read(**/id_rsa*)', 'Read(**/id_ed25519*)']
    # defence in depth (the guard hook enforces the same): jobs never edit their own settings, the vault rules, git internals or the installer state
    deny += [abs_rule('Edit', f'{vault}/{p}/**') for p in PROTECTED_DIRS] + [abs_rule('Edit', f'{vault}/{f}') for f in PROTECTED_FILES]
    for cap in req + opt:
        tool = answers['tools'].get(cap, 'none')
        if tool != 'none':
            man = jload(os.path.join(repo, 'adapters', cap, tool + '.json'))
            allow += man.get('permissions_allow', [])
            allow += list((answers.get('permissions') or {}).get(cap, []))
            deny += man.get('permissions_deny', [])
    guard = ' '.join(shlex.quote(x) for x in (python_bin(answers), os.path.join(expand(answers['ct_home']), 'bin', 'guard.py'), '--vault', vault))
    return {'permissions': {'allow': sorted(set(allow)), 'deny': sorted(set(deny))},
            'hooks': {'PreToolUse': [{'matcher': GUARD_MATCHER, 'hooks': [{'type': 'command', 'command': guard, 'timeout': 10}]}]}}


def python_bin(answers):
    """Absolute interpreter for hooks and schedules: launchd and cron have a minimal PATH."""
    return answers.get('python_bin') or sys.executable or 'python3'


def parse_days(spec):
    """'mon-fri', 'mon,wed', 'weekdays', 'daily' -> cron weekday numbers (0 = Sunday). Raises ValueError with a readable message."""
    spec = DAY_ALIASES.get(spec.lower().strip(), spec.lower().strip())
    out = []
    def day(x):
        x = x.strip()[:3]
        if x not in DAYS:
            raise ValueError(f'unknown day "{x}" in "{spec}" (use mon, tue, wed, thu, fri, sat, sun, ranges like mon-fri, or weekdays)')
        return DAYS[x]
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            i, j = day(a), day(b)
            order = [1, 2, 3, 4, 5, 6, 0]
            ia, ib = order.index(i), order.index(j)
            out += order[ia:ib + 1] if ia <= ib else order[ia:] + order[:ib + 1]
        else:
            out.append(day(part))
    return sorted(set(out), key=lambda d: (d + 6) % 7)


def local_time(hhmm, timezone, machine_tz=None):
    """Convert a time in the user's timezone to machine time.

    Returns (HH:MM, day_shift, warning or None). day_shift is -1, 0 or +1 when the conversion crosses midnight:
    the weekdays of the schedule must move by the same amount.
    """
    tz = zoneinfo.ZoneInfo(timezone)  # validated before; never fall back silently to machine time
    h, m = map(int, hhmm.split(':'))
    now = datetime.datetime.now(tz)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    local = target.astimezone(machine_tz)
    shift = (local.date() - target.date()).days
    if local.strftime('%H:%M') == hhmm and shift == 0:
        return hhmm, 0, None
    return local.strftime('%H:%M'), shift, (f'{hhmm} {timezone} runs at {local.strftime("%H:%M")} machine time'
                                            + (f' ({"next" if shift > 0 else "previous"} day)' if shift else '')
                                            + ' (today\'s offsets; re-run the installer after a daylight-saving change)')


def shift_days(days, shift):
    return sorted({(d + shift) % 7 for d in days}, key=lambda d: (d + 6) % 7)


def launchd_plist(label, args, days, hhmm, log):
    h, m = map(int, hhmm.split(':'))
    data = {'Label': label, 'ProgramArguments': list(args),
            'StartCalendarInterval': [{'Weekday': d, 'Hour': h, 'Minute': m} for d in days],
            'StandardOutPath': log, 'StandardErrorPath': log, 'ProcessType': 'Background'}
    return plistlib.dumps(data, sort_keys=False).decode('utf-8')  # escapes &, < and quotes in paths


def cron_line(args, days, hhmm):
    h, m = map(int, hhmm.split(':'))
    dow = ','.join(str(d) for d in days)
    return f'{m} {h} * * {dow} ' + ' '.join(shlex.quote(a).replace('%', '\\%') for a in args)  # cron reads % as a newline


def pick_scheduler(choice):
    if choice != 'auto':
        return choice
    return {'darwin': 'launchd', 'linux': 'cron'}.get(sys.platform, 'none')


# ----------------------------------------------------------------------------- install
def install(answers, repo=REPO, dry_run=False, apply_schedule=False, launch_agents_dir=None, no_launchctl=False, log=print):
    validate(answers, repo)
    a = dict(default_answers(repo)); a.update(answers)
    a['tools'] = {c: (a.get('tools') or {}).get(c, 'none') for c in CAPABILITIES}
    vault, ct_home = expand(a['vault_path']), expand(a['ct_home'])
    a['vault_path'], a['ct_home'] = vault, ct_home
    clash = static_collisions(repo, a['packs'])
    if clash:
        raise InstallError('these files would be written by two packs or by a pack and the core: ' + '; '.join(clash))
    table = render.build_table(vocab_files(repo, a['packs']), a)
    report = {'vault': vault, 'ct_home': ct_home, 'created': 0, 'kept': 0, 'jobs': [], 'jobs_skipped': [], 'warnings': [], 'schedule': None}
    manifest_path = os.path.join(vault, '.control-tower', 'manifest.json')
    files = {}
    def record(res):
        report['created'] += len(res['created']) + len(res['replaced'])
        report['kept'] += len(res['kept'])
        for rel in res['created'] + res['replaced']:
            files[rel] = None
    # 1. vault: core then packs
    record(render.render_tree(os.path.join(repo, 'core', 'vault'), vault, table, dry_run=dry_run))
    for p in a['packs']:
        pv = os.path.join(repo, 'packs', p, 'vault')
        if os.path.isdir(pv):
            record(render.render_tree(pv, vault, table, dry_run=dry_run))
    # 2. adapter notes and next steps
    for cap, tool in a['tools'].items():
        if tool == 'none':
            continue
        rel = f'.claude/adapters/{cap}.md'
        target = os.path.join(vault, rel)
        if not os.path.exists(target):
            report['created'] += 1
            files[rel] = None
            if not dry_run:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, 'w', encoding='utf-8') as fh:
                    errs = []
                    fh.write(render.render_text(adapter_doc(repo, cap, tool), table, rel, errs))
                    if errs:
                        raise InstallError('; '.join(errs))
        else:
            report['kept'] += 1
    # 3. jobs
    jobs = eligible_jobs(repo, a['packs'], a['tools'])
    on, off = [], []
    for j in jobs:
        cfg = (a.get('jobs') or {}).get(j['id'], {})
        if j['missing'] or cfg.get('enabled') is False:
            off.append(j)
        else:
            on.append(j)
    for j in off:
        report['jobs_skipped'].append({'id': j['id'], 'missing': j['missing']})
    if not dry_run:
        os.makedirs(os.path.join(ct_home, 'bin'), exist_ok=True)
        for name in ('run_job.py', 'guard.py'):
            shutil.copy2(os.path.join(repo, 'scheduler', name), os.path.join(ct_home, 'bin', name))
        jdump(os.path.join(ct_home, 'install.json'), {'vault': vault, 'claude_bin': a.get('claude_bin', 'claude'),
                                                       'timezone': a['timezone'], 'version': VERSION})
    sched_dir = os.path.join(ct_home, 'schedule')
    if not dry_run:
        # the schedule and the job folders always mirror the current answers: a job that was disabled or lost its tool disappears
        shutil.rmtree(sched_dir, ignore_errors=True)
        jobs_root = os.path.join(ct_home, 'jobs')
        keep = {j['id'] for j in on}
        for old in (os.listdir(jobs_root) if os.path.isdir(jobs_root) else []):
            if old not in keep:
                shutil.rmtree(os.path.join(jobs_root, old), ignore_errors=True)
    kind = pick_scheduler(a.get('scheduler', 'auto'))
    plist_paths, cron_lines = [], []
    for j in on:
        cfg = (a.get('jobs') or {}).get(j['id'], {})
        meta = dict(j['meta'])
        sched = dict(meta['schedule'])
        sched.update({k: v for k, v in cfg.items() if k in ('time', 'days')})
        meta['schedule'] = sched
        report['jobs'].append({'id': j['id'], 'pack': j['pack'], 'days': sched['days'], 'time': sched['time']})
        jdir = os.path.join(ct_home, 'jobs', j['id'])
        if not dry_run:
            res = render.render_tree(os.path.join(repo, 'packs', j['pack'], 'jobs', j['id']), jdir, table, force=True,
                                     rename=lambda r: {'prompt.md': 'prompt.md'}.get(r, r))
            jdump(os.path.join(jdir, 'job.json'), json.loads(render.render_text(json.dumps(meta), {**table}, j['id'], [])))
            jdump(os.path.join(jdir, 'settings.json'), job_settings(repo, a, {'id': j['id'], 'meta': json.loads(render.render_text(json.dumps(meta), table, j['id'], []))}))
        args = [python_bin(a), os.path.join(ct_home, 'bin', 'run_job.py'), '--job', j['id'], '--ct-home', ct_home]
        lt, shift, warn = local_time(sched['time'], a['timezone'])
        days = shift_days(parse_days(sched['days']), shift)
        if warn:
            report['warnings'].append(f"{j['id']}: {warn}")
        if kind == 'launchd':
            label = f"com.control-tower.{j['id']}"
            path = os.path.join(sched_dir, 'launchd', label + '.plist')
            plist_paths.append((label, path))
            if not dry_run:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as fh:
                    fh.write(launchd_plist(label, args, days, lt, os.path.join(ct_home, 'logs', j['id'] + '.launchd.log')))
        elif kind == 'cron':
            cron_lines.append(f'# {j["id"]}\n' + cron_line(args, days, lt))
    if kind == 'cron' and not dry_run:  # an empty block is written too, so applying it removes jobs that are gone
        os.makedirs(sched_dir, exist_ok=True)
        with open(os.path.join(sched_dir, 'crontab.txt'), 'w', encoding='utf-8') as fh:
            fh.write('# BEGIN control-tower\n' + '\n'.join(cron_lines) + '\n# END control-tower\n')
    report['schedule'] = {'kind': kind, 'applied': False, 'dir': sched_dir}
    if apply_schedule and not dry_run and kind != 'none':
        report['schedule']['applied'] = apply(kind, plist_paths, os.path.join(sched_dir, 'crontab.txt'), launch_agents_dir, no_launchctl, report)
    elif apply_schedule and not dry_run and kind == 'none':
        report['warnings'].append('--apply-schedule ignored: scheduler is "none" in the answers')
    for cap, tool in a['tools'].items():
        if tool == 'none':
            continue
        man = jload(os.path.join(repo, 'adapters', cap, tool + '.json'))
        if man.get('access') == 'mcp' and not man.get('permissions_allow') and not (a.get('permissions') or {}).get(cap):
            report['warnings'].append(f'{cap}/{tool}: jobs cannot call this MCP server until you list its read-only tools in the answers '
                                      f'("permissions": {{"{cap}": ["mcp__<server>__<tool>", ...]}}) and re-run the installer')
    # 3b. cloud routines: rendered prompts and an index the guided installer reads to create them on request
    report['routines'], report['routines_skipped'] = [], []
    index = []
    seen_ids = {}
    for r in eligible_routines(repo, a['packs'], a['tools']):
        if r['id'] in seen_ids and not r['missing']:
            report['routines_skipped'].append({'id': f"{r['pack']}--{r['id']}", 'missing': [], 'duplicate_of': seen_ids[r['id']]})
            continue
        if r['missing']:
            report['routines_skipped'].append({'id': f"{r['pack']}--{r['id']}", 'missing': r['missing']})
            continue
        key = f"{r['pack']}--{r['id']}"
        seen_ids[r['id']] = key
        meta = r['meta']
        errs = []
        prompt = render.render_text(r['prompt'], table, key, errs)
        if errs:
            raise InstallError('; '.join(errs))
        entry = {'key': key, 'pack': r['pack'], 'id': r['id'],
                 'name': meta['name'],
                 'days': meta['days'], 'time': meta['time'], 'timezone': a['timezone'], 'cron': routine_cron(meta['days'], meta['time']),
                 'connectors_required': {c: a['tools'][c] for c in meta.get('connectors_required', [])},
                 'connectors_optional': {c: a['tools'][c] for c in meta.get('connectors_optional', []) if a['tools'].get(c, 'none') != 'none'},
                 'vault': meta.get('vault', 'write'), 'after': meta.get('after', ''),
                 'prompt_file': os.path.join(ct_home, 'routines', key + '.prompt.md')}
        index.append(entry)
        report['routines'].append({'key': key, 'name': entry['name'], 'days': entry['days'], 'time': entry['time']})
        if not dry_run:
            os.makedirs(os.path.join(ct_home, 'routines'), exist_ok=True)
            with open(entry['prompt_file'], 'w', encoding='utf-8') as fh:
                fh.write(prompt)
    if not dry_run:
        jdump(os.path.join(ct_home, 'routines', 'routines.json'), index) if index else None
    # 4. notes that depend on the answers
    ns_rel = 'library/setup-next-steps.md'
    ns = os.path.join(vault, ns_rel)
    if not os.path.exists(ns):
        files[ns_rel] = None
        report['created'] += 1
        if not dry_run:
            os.makedirs(os.path.dirname(ns), exist_ok=True)
            with open(ns, 'w', encoding='utf-8') as fh:
                fh.write(next_steps(repo, a, on, off, report['routines']))
    if not dry_run:
        for rel in obsidian_seed(vault):
            files[rel] = None
        # 5. manifest with hashes (used by doctor and uninstall)
        sums = {}
        for rel in files:
            p = os.path.join(vault, rel)
            if os.path.isfile(p):
                sums[rel] = render.sha256(p)
        old = {}
        if os.path.exists(manifest_path):
            old = jload(manifest_path).get('files', {})
        old.update(sums)
        jdump(manifest_path, {'version': VERSION, 'installed_at': datetime.datetime.now().isoformat(timespec='seconds'),
                              'packs': a['packs'], 'tools': a['tools'], 'ct_home': ct_home, 'files': old})
        public = {k: v for k, v in a.items() if k not in ('claude_bin',)}
        jdump(os.path.join(vault, '.control-tower', 'answers.json'), public)
    return report


def apply(kind, plist_paths, cron_file, launch_agents_dir, no_launchctl, report):
    if kind == 'launchd':
        dest = launch_agents_dir or os.path.expanduser('~/Library/LaunchAgents')
        os.makedirs(dest, exist_ok=True)
        current = {label for label, _ in plist_paths}
        for f in os.listdir(dest):  # unload and remove jobs that are no longer installed
            label = f[:-6] if f.endswith('.plist') else f
            if f.startswith('com.control-tower.') and label not in current:
                if not no_launchctl and shutil.which('launchctl'):
                    subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{label}'], capture_output=True)
                os.remove(os.path.join(dest, f))
        for label, path in plist_paths:
            link = os.path.join(dest, label + '.plist')
            if os.path.lexists(link):
                os.remove(link)
            os.symlink(path, link)
            if not no_launchctl and shutil.which('launchctl'):
                uid = str(os.getuid())
                subprocess.run(['launchctl', 'bootout', f'gui/{uid}/{label}'], capture_output=True)
                r = subprocess.run(['launchctl', 'bootstrap', f'gui/{uid}', link], capture_output=True, text=True)
                if r.returncode != 0:
                    report['warnings'].append(f'launchctl bootstrap {label}: {r.stderr.strip()}')
        return True
    if kind == 'cron':
        if not shutil.which('crontab'):
            report['warnings'].append('crontab not available: add the lines of schedule/crontab.txt yourself')
            return False
        got = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if got.returncode != 0 and 'no crontab' not in got.stderr.lower():
            report['warnings'].append(f'could not read your crontab, nothing changed: {got.stderr.strip()}')
            return False
        cur = got.stdout if got.returncode == 0 else ''
        cur = re(r'# BEGIN control-tower.*?# END control-tower\n?', '', cur, flags=re.S)
        block = open(cron_file, encoding='utf-8').read() if os.path.exists(cron_file) else ''
        new = cur.rstrip('\n') + ('\n' if cur.strip() else '') + block
        r = subprocess.run(['crontab', '-'], input=new, capture_output=True, text=True)
        return r.returncode == 0
    return False


def print_report(report, dry_run):
    mode = 'DRY RUN: nothing was written.\n' if dry_run else ''
    print(f"\n{mode}Vault: {report['vault']}\nRuntime: {report['ct_home']}")
    print(f"Files: {report['created']} {'would be created' if dry_run else 'created'}, {report['kept']} kept (already existed)")
    print('Jobs: ' + (', '.join(f"{j['id']} ({j['days']} {j['time']})" for j in report['jobs']) or 'none'))
    for j in report['jobs_skipped']:
        print(f"  skipped {j['id']}: " + (f"needs a tool for {', '.join(j['missing'])}" if j['missing'] else 'disabled'))
    s = report['schedule']
    if s:
        if s['kind'] == 'none':
            print('Schedule: none (jobs run only when you start them)')
        else:
            print(f"Schedule: {s['kind']} ({'applied' if s['applied'] else 'generated, not applied: re-run with --apply-schedule'})")
    if report.get('routines'):
        print('Cloud routines available (not created): ' + ', '.join(r['key'] for r in report['routines'])
              + '. Run /install-control-tower routines to create them on claude.ai.')
    for r in report.get('routines_skipped', []):
        why = f"same routine as {r['duplicate_of']}" if r.get('duplicate_of') else f"needs a tool for {', '.join(r['missing'])}"
        print(f"  routine {r['id']} not offered: {why}")
    for w in report['warnings']:
        print('warning: ' + w)
    if not dry_run:
        print('\nNext: open library/setup-next-steps.md in your vault.')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--answers')
    ap.add_argument('--interactive', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--apply-schedule', action='store_true')
    ap.add_argument('--launch-agents-dir', help='where to link launchd plists (default ~/Library/LaunchAgents)')
    ap.add_argument('--no-launchctl', action='store_true', help='link plists but do not load them (tests)')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    try:
        if args.interactive:
            answers = wizard()
        elif args.answers:
            answers = jload(args.answers)
        else:
            ap.error('give --answers FILE or --interactive')
        report = install(answers, dry_run=args.dry_run, apply_schedule=args.apply_schedule,
                         launch_agents_dir=args.launch_agents_dir, no_launchctl=args.no_launchctl)
    except (InstallError, render.RenderError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as exc:
        print(f'error: {args.answers} is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})', file=sys.stderr)
        sys.exit(2)
    except OSError as exc:
        print(f'error: {exc.strerror or exc}: {exc.filename or ""}', file=sys.stderr)
        sys.exit(2)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report, args.dry_run)


if __name__ == '__main__':
    main()
