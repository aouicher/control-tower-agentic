#!/usr/bin/env python3
"""Health check of a control tower installation. Read-only. Standard library only.

    python3 installer/doctor.py --vault ~/my-vault --ct-home ~/.control-tower [--json]

Prints one line per check (ok / warn / FAIL) and exits with 1 when something failed.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

LAYOUT = ['_inbox', 'cockpit', 'work/projects', 'work/areas', 'work/workstreams', 'work/decisions', 'work/risks', 'team',
          'journal/daily', 'journal/meetings', 'journal/reports', 'library', '_system/templates', '_system/dashboards',
          '_system/tools', '_system/archive', '_system/attachments', '.claude/skills']
CORE_SKILLS = ['today', 'weekly-review', 'meeting', 'research', 'time-review']


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, name, detail=''):
        self.items.append({'level': level, 'check': name, 'detail': detail})

    @property
    def failed(self):
        return any(i['level'] == 'FAIL' for i in self.items)


def frontmatter(text):
    m = re.match(r'---\n(.*?)\n---\n', text, re.S)
    if not m:
        return None
    props = {}
    for line in m.group(1).split('\n'):
        k = re.match(r'^([A-Za-z_][\w-]*):\s*(.*)$', line)
        if k:
            props[k.group(1)] = k.group(2).strip()
    return props


def read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def check(vault, ct_home, claude_bin='claude'):
    r = Report()
    vault = os.path.abspath(os.path.expanduser(vault))
    ct_home = os.path.abspath(os.path.expanduser(ct_home))
    r.add('ok' if sys.version_info >= (3, 8) else 'FAIL', 'python >= 3.8', sys.version.split()[0])
    r.add('ok' if shutil.which(claude_bin) else 'warn', 'claude CLI on PATH', claude_bin if shutil.which(claude_bin) else 'not found: install Claude Code')
    r.add('ok' if shutil.which('git') else 'warn', 'git on PATH')
    if not os.path.isdir(vault):
        r.add('FAIL', 'vault folder', f'{vault} does not exist')
        return r
    missing = [d for d in LAYOUT if not os.path.isdir(os.path.join(vault, d))]
    r.add('ok' if not missing else 'FAIL', 'vault folder layout', ', '.join(missing) or f'{len(LAYOUT)} folders')
    r.add('ok' if os.path.isfile(os.path.join(vault, 'CLAUDE.md')) else 'FAIL', 'CLAUDE.md at the vault root')
    # notes: frontmatter and leftover tokens
    bad_fm, tokens, unquoted, count = [], [], [], 0
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in ('.obsidian', '.control-tower', '.control-tower-backup', '_attachments')]
        for f in files:
            if not f.endswith(('.md', '.base')):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, vault)
            if rel.startswith('_system/templates') and False:
                continue
            text = read(p)
            if re.search(r'\{\{ct\.', text):
                tokens.append(rel)
            if f.endswith('.md') and not rel.startswith(('.claude/skills', '.claude/adapters', '.claude/rules')) and rel != 'CLAUDE.md':
                count += 1
                fm = frontmatter(text)
                if fm is None:
                    bad_fm.append(rel)
                else:
                    for k, v in fm.items():
                        if v and not v.startswith(('"', "'", '[', '{', '|', '>', '{{')) and re.search(r':\s|\s#', v):
                            unquoted.append(f'{rel}: {k}')
    r.add('ok' if not tokens else 'FAIL', 'no leftover {{ct.*}} token', ', '.join(tokens[:5]))
    r.add('ok' if not bad_fm else 'warn', f'frontmatter present ({count} notes)', ', '.join(bad_fm[:5]))
    r.add('ok' if not unquoted else 'warn', 'frontmatter values quoted when needed', ', '.join(unquoted[:5]))
    # skills
    sk_dir = os.path.join(vault, '.claude', 'skills')
    skills = sorted(os.listdir(sk_dir)) if os.path.isdir(sk_dir) else []
    bad = []
    for s in skills:
        p = os.path.join(sk_dir, s, 'SKILL.md')
        if not os.path.isfile(p):
            bad.append(f'{s}: no SKILL.md')
            continue
        fm = frontmatter(read(p)) or {}
        if fm.get('name') != s or 'description' not in fm:
            bad.append(f'{s}: name/description')
    r.add('ok' if not bad and set(CORE_SKILLS) <= set(skills) else 'FAIL', f'vault skills ({len(skills)})', ', '.join(bad) or ', '.join(skills))
    # manifest
    mp = os.path.join(vault, '.control-tower', 'manifest.json')
    manifest = None
    if os.path.isfile(mp):
        manifest = json.loads(read(mp))
        import hashlib
        changed = 0
        for rel, sha in manifest.get('files', {}).items():
            p = os.path.join(vault, rel)
            if os.path.isfile(p) and sha and hashlib.sha256(open(p, 'rb').read()).hexdigest() != sha:
                changed += 1
        r.add('ok', 'install manifest', f"packs: {', '.join(manifest.get('packs', []))}; {changed} installed file(s) edited since install (normal)")
    else:
        r.add('warn', 'install manifest', 'not found: this vault was not created by the installer')
    # adapters
    if manifest:
        for cap, tool in (manifest.get('tools') or {}).items():
            if tool != 'none':
                ok = os.path.isfile(os.path.join(vault, '.claude', 'adapters', f'{cap}.md'))
                r.add('ok' if ok else 'FAIL', f'adapter note {cap} ({tool})')
    # obsidian
    obs = os.path.join(vault, '.obsidian')
    if os.path.isdir(obs):
        cp = os.path.join(obs, 'community-plugins.json')
        plugins = json.loads(read(cp)) if os.path.isfile(cp) else []
        r.add('ok' if 'obsidian-tasks-plugin' in plugins else 'warn', 'Obsidian Tasks plugin enabled', 'install it from Community plugins' if 'obsidian-tasks-plugin' not in plugins else '')
        core = os.path.join(obs, 'core-plugins.json')
        if os.path.isfile(core):
            c = json.loads(read(core))
            r.add('ok' if (c.get('bases') is True if isinstance(c, dict) else 'bases' in c) else 'warn', 'Obsidian Bases core plugin enabled')
    else:
        r.add('warn', 'Obsidian configuration', 'open the vault once in Obsidian to create .obsidian/')
    # runtime and jobs
    if not os.path.isdir(ct_home):
        r.add('warn', 'runtime folder', f'{ct_home} not found (no jobs installed)')
        return r
    for f in ('install.json', 'bin/run_job.py', 'bin/guard.py'):
        r.add('ok' if os.path.isfile(os.path.join(ct_home, f)) else 'FAIL', f'runtime file {f}')
    jobs_dir = os.path.join(ct_home, 'jobs')
    for j in sorted(os.listdir(jobs_dir)) if os.path.isdir(jobs_dir) else []:
        jd = os.path.join(jobs_dir, j)
        need = [f for f in ('prompt.md', 'job.json', 'settings.json') if not os.path.isfile(os.path.join(jd, f))]
        if need:
            r.add('FAIL', f'job {j}', 'missing ' + ', '.join(need))
            continue
        try:
            st = json.loads(read(os.path.join(jd, 'settings.json')))
            guard = bool(st.get('hooks', {}).get('PreToolUse'))
            writes = [a for a in st['permissions']['allow'] if a.startswith(('Write', 'Edit(')) or a in ('Write', 'Edit', 'Bash')]
            ok_scope = all(a.startswith('Edit(' + vault) for a in writes)
            r.add('ok' if guard and ok_scope else 'FAIL', f'job {j}', 'guard hook and vault-scoped writes' if guard and ok_scope else 'missing guard hook or unscoped write permission')
        except (ValueError, KeyError):
            r.add('FAIL', f'job {j}', 'settings.json is not valid')
    for risky in ('.claude/settings.json', '.claude/settings.local.json', '.mcp.json'):
        if os.path.isfile(os.path.join(vault, risky)):
            r.add('warn', f'vault file {risky}', 'unattended jobs load the vault settings: anything allowed there widens what jobs can do, review it')
    sched = os.path.join(ct_home, 'schedule')
    if os.path.isdir(os.path.join(sched, 'launchd')) and shutil.which('plutil'):
        for f in sorted(os.listdir(os.path.join(sched, 'launchd'))):
            rc = subprocess.run(['plutil', '-lint', os.path.join(sched, 'launchd', f)], capture_output=True).returncode
            r.add('ok' if rc == 0 else 'FAIL', f'launchd file {f}')
    applied = os.path.isdir(os.path.expanduser('~/Library/LaunchAgents')) and any(
        f.startswith('com.control-tower.') for f in os.listdir(os.path.expanduser('~/Library/LaunchAgents')))
    if os.path.isdir(sched):
        r.add('ok' if applied or os.path.isfile(os.path.join(sched, 'crontab.txt')) else 'warn', 'schedule generated',
              'jobs run on schedule only after --apply-schedule' if not applied else 'applied')
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--vault', required=True)
    ap.add_argument('--ct-home', default='~/.control-tower')
    ap.add_argument('--claude-bin', default='claude')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    rep = check(args.vault, args.ct_home, args.claude_bin)
    if args.json:
        print(json.dumps(rep.items, indent=2))
    else:
        icons = {'ok': 'ok  ', 'warn': 'warn', 'FAIL': 'FAIL'}
        for i in rep.items:
            print(f"[{icons[i['level']]}] {i['check']}" + (f": {i['detail']}" if i['detail'] else ''))
        print(f"\n{sum(i['level'] == 'ok' for i in rep.items)} ok, {sum(i['level'] == 'warn' for i in rep.items)} warning(s), "
              f"{sum(i['level'] == 'FAIL' for i in rep.items)} failure(s)")
    sys.exit(1 if rep.failed else 0)


if __name__ == '__main__':
    main()
