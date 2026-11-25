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
import re
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
    for jid, cfg in (answers.get('jobs') or {}).items():
        t = (cfg or {}).get('time')
        if t is not None and not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', str(t)):
            errors.append(f'answers: job "{jid}" time must be HH:MM')
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


def eligible_jobs(repo, packs, tools):
    """Jobs whose capabilities all have a chosen tool."""
    jobs = []
    for p in packs:
        manifest = jload(os.path.join(repo, 'packs', p, 'pack.json'))
        for j in manifest.get('jobs', []):
            meta = jload(os.path.join(repo, 'packs', p, 'jobs', j, 'job.json'))
            missing = [c for c in meta['capabilities'] if tools.get(c, 'none') == 'none']
            jobs.append({'pack': p, 'id': j, 'meta': meta, 'missing': missing})
    return jobs


def adapter_doc(repo, capability, tool):
    with open(os.path.join(repo, 'adapters', capability, 'contract.md'), encoding='utf-8') as fh:
        contract = fh.read()
    with open(os.path.join(repo, 'adapters', capability, tool + '.md'), encoding='utf-8') as fh:
        doc = fh.read()
    return (f'<!-- Installed by control-tower {VERSION}: capability {capability}, tool {tool}. '
            f'Jobs and skills read this file to know how to query the tool. -->\n\n'
            f'# {capability.capitalize()} adapter: {tool}\n\n## Contract\n\n{contract}\n\n---\n\n{doc}\n')


def next_steps(repo, answers, jobs_on, jobs_off):
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
    lines += ['', '## 4. Cloud routines (optional)', '',
              'Prompts for claude.ai cloud routines are in each pack under `routines/` of the control tower repository. '
              'Create them in claude.ai and link your computer so they can read this vault.', '',
              '## 5. Health check', '', '```bash', f"python3 <repository>/installer/doctor.py --vault {answers['vault_path']} --ct-home {answers['ct_home']}", '```', '']
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
def job_settings(repo, answers, job):
    vault = expand(answers['vault_path'])
    allow = list(BASE_ALLOW) + [render.render_text(p, {'vault_path': vault}, job['id'], []) for p in job['meta']['permissions'].get('allow', [])]
    deny = list(BASE_DENY) + list(job['meta']['permissions'].get('deny', []))
    deny += ['Read(**/.env*)', 'Read(**/.ssh/**)', 'Read(**/.aws/**)', 'Read(**/.gnupg/**)', 'Read(**/*credentials*)', 'Read(**/id_rsa*)', 'Read(**/id_ed25519*)']
    # defence in depth (the guard hook enforces the same): jobs can never edit their own settings, the vault rules or the installer state
    deny += [f'Edit({vault}/{p}/**)' for p in ('.claude', '.control-tower', '.obsidian', '_system/templates')] + [f'Edit({vault}/CLAUDE.md)', f'Edit({vault}/.mcp.json)']
    for cap in job['meta']['capabilities']:
        tool = answers['tools'].get(cap, 'none')
        if tool != 'none':
            man = jload(os.path.join(repo, 'adapters', cap, tool + '.json'))
            allow += man.get('permissions_allow', [])
            allow += list((answers.get('permissions') or {}).get(cap, []))
            deny += man.get('permissions_deny', [])
    guard = f"python3 {expand(answers['ct_home'])}/bin/guard.py --vault {vault}"
    return {'permissions': {'allow': sorted(set(allow)), 'deny': sorted(set(deny))},
            'hooks': {'PreToolUse': [{'matcher': GUARD_MATCHER, 'hooks': [{'type': 'command', 'command': guard, 'timeout': 10}]}]}}


def parse_days(spec):
    spec = spec.lower().strip()
    if spec in ('daily', 'every day', '*'):
        return [1, 2, 3, 4, 5, 6, 0]
    out = []
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-')
            i, j = DAYS[a[:3]], DAYS[b[:3]]
            order = [1, 2, 3, 4, 5, 6, 0]
            ia, ib = order.index(i), order.index(j)
            out += order[ia:ib + 1] if ia <= ib else order[ia:] + order[:ib + 1]
        else:
            out.append(DAYS[part[:3]])
    return sorted(set(out), key=lambda d: (d + 6) % 7)


def local_time(hhmm, timezone):
    """Convert a time in the user's timezone to the machine's local time, returning (HH:MM, warning or None)."""
    tz = zoneinfo.ZoneInfo(timezone)  # validated before; never fall back silently to machine time
    h, m = map(int, hhmm.split(':'))
    now = datetime.datetime.now(tz)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    local = target.astimezone()
    if local.utcoffset() == now.utcoffset():
        return hhmm, None
    return local.strftime('%H:%M'), (f'{hhmm} {timezone} converted to {local.strftime("%H:%M")} machine time '
                                     '(today\'s offsets; re-run the installer after a daylight-saving change)')


def launchd_plist(label, args, days, hhmm, log):
    h, m = map(int, hhmm.split(':'))
    cal = ''.join(f'<dict><key>Weekday</key><integer>{d}</integer><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer></dict>' for d in days)
    arr = ''.join(f'<string>{a}</string>' for a in args)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">\n<dict>\n'
            f'  <key>Label</key><string>{label}</string>\n  <key>ProgramArguments</key>\n  <array>{arr}</array>\n'
            f'  <key>StartCalendarInterval</key>\n  <array>{cal}</array>\n'
            f'  <key>StandardOutPath</key><string>{log}</string>\n  <key>StandardErrorPath</key><string>{log}</string>\n'
            '  <key>ProcessType</key><string>Background</string>\n</dict>\n</plist>\n')


def cron_line(args, days, hhmm):
    h, m = map(int, hhmm.split(':'))
    dow = ','.join(str(d) for d in days)
    return f'{m} {h} * * {dow} ' + ' '.join(a if re.fullmatch(r'[\w./:=-]+', a) else "'" + a + "'" for a in args)


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
        args = ['python3', os.path.join(ct_home, 'bin', 'run_job.py'), '--job', j['id'], '--ct-home', ct_home]
        days = parse_days(sched['days'])
        lt, warn = local_time(sched['time'], a['timezone'])
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
    if kind == 'cron' and cron_lines and not dry_run:
        os.makedirs(sched_dir, exist_ok=True)
        with open(os.path.join(sched_dir, 'crontab.txt'), 'w', encoding='utf-8') as fh:
            fh.write('# BEGIN control-tower\n' + '\n'.join(cron_lines) + '\n# END control-tower\n')
    report['schedule'] = {'kind': kind, 'applied': False, 'dir': sched_dir}
    if apply_schedule and not dry_run and kind != 'none':
        report['schedule']['applied'] = apply(kind, plist_paths, os.path.join(sched_dir, 'crontab.txt'), launch_agents_dir, no_launchctl, report)
    for cap, tool in a['tools'].items():
        if tool == 'none':
            continue
        man = jload(os.path.join(repo, 'adapters', cap, tool + '.json'))
        if man.get('access') == 'mcp' and not man.get('permissions_allow') and not (a.get('permissions') or {}).get(cap):
            report['warnings'].append(f'{cap}/{tool}: jobs cannot call this MCP server until you list its read-only tools in the answers '
                                      f'("permissions": {{"{cap}": ["mcp__<server>__<tool>", ...]}}) and re-run the installer')
    # 4. notes that depend on the answers
    ns_rel = 'library/setup-next-steps.md'
    ns = os.path.join(vault, ns_rel)
    if not os.path.exists(ns):
        files[ns_rel] = None
        report['created'] += 1
        if not dry_run:
            os.makedirs(os.path.dirname(ns), exist_ok=True)
            with open(ns, 'w', encoding='utf-8') as fh:
                fh.write(next_steps(repo, a, on, off))
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
        if not os.path.exists(cron_file) or not shutil.which('crontab'):
            report['warnings'].append('crontab not available: add the lines of schedule/crontab.txt yourself')
            return False
        cur = subprocess.run(['crontab', '-l'], capture_output=True, text=True).stdout
        cur = re.sub(r'# BEGIN control-tower.*?# END control-tower\n?', '', cur, flags=re.S)
        new = cur.rstrip('\n') + ('\n' if cur.strip() else '') + open(cron_file, encoding='utf-8').read()
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
        print(f"Schedule: {s['kind']} ({'applied' if s['applied'] else 'generated, not applied: re-run with --apply-schedule'})")
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
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report, args.dry_run)


if __name__ == '__main__':
    main()
