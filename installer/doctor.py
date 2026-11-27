#!/usr/bin/env python3
"""Health check of a control tower installation. Read-only. Standard library only.

    python3 installer/doctor.py --vault ~/my-vault --ct-home ~/.control-tower [--json]

Prints one line per check (ok / warn / FAIL) and exits with 1 when something failed.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan import REPO, CorePolicy, core_files, risky_settings  # noqa: E402

LAYOUT = ['_inbox', 'cockpit', 'work/projects', 'work/areas', 'work/workstreams', 'work/decisions', 'work/risks', 'team',
          'journal/daily', 'journal/meetings', 'journal/reports', 'library', '_system/templates', '_system/dashboards',
          '_system/tools', '_system/archive', '_system/attachments', '.claude/skills']
CORE_SKILLS = ['today', 'weekly-review', 'meeting', 'research', 'time-review', 'inbox', 'job-permissions']


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
    r.add('ok' if sys.version_info >= (3, 9) else 'FAIL', 'python >= 3.9', sys.version.split()[0])
    r.add('ok' if shutil.which(claude_bin) else 'warn', 'claude CLI on PATH', claude_bin if shutil.which(claude_bin) else 'not found: install Claude Code')
    r.add('ok' if shutil.which('git') else 'warn', 'git on PATH')
    if not os.path.isdir(vault):
        r.add('FAIL', 'vault folder', f'{vault} does not exist')
        return r
    mp = os.path.join(vault, '.control-tower', 'manifest.json')
    manifest = json.loads(read(mp)) if os.path.isfile(mp) else None  # read once, used below
    if (manifest or {}).get('vault_mode') == 'runtime':
        # runtime-only install: the vault is the user's own layout, only the runtime is checked
        r.add('ok', 'vault (runtime-only install)', 'vault layout, notes and skills are yours: not checked')
        return check_runtime(r, vault, ct_home)
    # same rule as the installer (plan.CorePolicy): a core path is only expected when a private pack did not exclude it
    policy = CorePolicy.from_json(manifest)
    shipped = core_files(REPO)
    expected_dir = lambda d: any(f.startswith(d + '/') and not policy.excluded(f) for f in shipped)
    missing = [d for d in LAYOUT if expected_dir(d) and not os.path.isdir(os.path.join(vault, d))]
    r.add('ok' if not missing else 'FAIL', 'vault folder layout', ', '.join(missing) or 'all expected folders present')
    if not policy.excluded('CLAUDE.md'):
        r.add('ok' if os.path.isfile(os.path.join(vault, 'CLAUDE.md')) else 'FAIL', 'CLAUDE.md at the vault root')
    # notes: frontmatter and leftover tokens
    bad_fm, tokens, unquoted, count = [], [], [], 0
    for root, dirs, files in os.walk(vault):
        # notes only: skip dot-folders (Obsidian ignores them; a runtime folder may live there) except the vault's .claude
        dirs[:] = [d for d in dirs if d not in ('_attachments',) and (not d.startswith('.') or d == '.claude')]
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
    needed = {s for s in CORE_SKILLS if not policy.excluded(f'.claude/skills/{s}/SKILL.md')}
    r.add('ok' if not bad and needed <= set(skills) else 'FAIL', f'vault skills ({len(skills)})', ', '.join(bad) or ', '.join(skills))
    # manifest
    if manifest:
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
                r.add('ok' if ok else 'FAIL', f'adapter note {cap} ({tool})',
                      'installed; the connection itself is not checked: follow library/setup-next-steps.md' if ok else 'missing')
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
    return check_runtime(r, vault, ct_home)


def check_runtime(r, vault, ct_home):
    """Runtime folder, jobs, settings and schedule."""
    if not os.path.isdir(ct_home):
        r.add('warn', 'runtime folder', f'{ct_home} not found (no jobs installed)')
        return r
    for f in ('install.json', 'bin/run_job.py', 'bin/guard.py'):
        r.add('ok' if os.path.isfile(os.path.join(ct_home, f)) else 'FAIL', f'runtime file {f}')
    jobs_dir, sandboxed = os.path.join(ct_home, 'jobs'), []
    for j in sorted(os.listdir(jobs_dir)) if os.path.isdir(jobs_dir) else []:
        jd = os.path.join(jobs_dir, j)
        need = [f for f in ('prompt.md', 'job.json', 'settings.json') if not os.path.isfile(os.path.join(jd, f))]
        if need:
            r.add('FAIL', f'job {j}', 'missing ' + ', '.join(need))
            continue
        try:
            st = json.loads(read(os.path.join(jd, 'settings.json')))
            guard = bool(st.get('hooks', {}).get('PreToolUse'))
            commands = any(str(a).strip().startswith('Bash(') for a in st['permissions']['allow'])
            if commands and not (st.get('sandbox') or {}).get('enabled'):
                r.add('FAIL', f'job {j}', 'runs commands without the sandbox: update the kit to refresh its settings')
                continue
            if commands:
                sandboxed.append(j)
            writes = [a for a in st['permissions']['allow'] if a.startswith(('Write', 'Edit(')) or a in ('Write', 'Edit', 'Bash')]
            ok_scope = bool(writes) and all(a.startswith('Edit(/' + vault + '/') for a in writes)
            r.add('ok' if guard and ok_scope else 'FAIL', f'job {j}', 'guard hook and vault-scoped writes' if guard and ok_scope
                  else 'missing guard hook, or write permission missing or not scoped to the vault (re-run the installer)')
        except (ValueError, KeyError):
            r.add('FAIL', f'job {j}', 'settings.json is not valid')
    if sandboxed and sys.platform.startswith('linux'):  # Claude Code's sandbox needs both on Linux (nothing on macOS)
        missing = [t for t in ('bwrap', 'socat') if not shutil.which(t)]
        r.add('FAIL' if missing else 'ok', 'sandbox tools',
              f'{" and ".join(missing)} missing: {", ".join(sandboxed)} run commands and refuse to run without the sandbox; '
              'installing bubblewrap and socat is a one-time task for an administrator' if missing else 'bwrap and socat found')
    for risky in ('.claude/settings.json', '.claude/settings.local.json'):
        p = os.path.join(vault, risky)
        keys = risky_settings(p) if os.path.isfile(p) else []
        if keys:
            r.add('warn', f'vault file {risky}', f'sets {", ".join(keys)}: unattended jobs load it too, so it can widen what they do')
    if os.path.isfile(os.path.join(vault, '.mcp.json')):
        r.add('warn', 'vault file .mcp.json', 'MCP servers declared in the vault are available to unattended jobs too, review it')
    outside = []
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in ('.obsidian', '.git')]
        for n in dirs + files:
            p = os.path.join(root, n)
            if os.path.islink(p) and not os.path.realpath(p).startswith(os.path.realpath(vault) + os.sep):
                outside.append(os.path.relpath(p, vault))
    r.add('ok' if not outside else 'warn', 'no symlink leaves the vault', 'jobs search through symlinks, remove: ' + ', '.join(outside[:5]) if outside else '')
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
    ap.add_argument('--ct-home', help='runtime folder (default: the one recorded in the vault, else ~/.control-tower)')
    ap.add_argument('--claude-bin', default='claude')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    ct_home = args.ct_home
    if not ct_home:
        try:
            ct_home = json.load(open(os.path.join(os.path.expanduser(args.vault), '.control-tower', 'answers.json'), encoding='utf-8'))['ct_home']
        except (OSError, ValueError, KeyError):
            ct_home = '~/.control-tower'
    rep = check(args.vault, ct_home, args.claude_bin)
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
