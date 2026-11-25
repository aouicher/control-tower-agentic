#!/usr/bin/env python3
"""Opt-in smoke test with the REAL Claude Code CLI (costs a few cents, uses your signed-in account).

It installs the developer pack into a temporary folder, swaps one job's prompt for a short probe, runs it through the real
runner with Haiku, and checks what the CLI actually allowed: the report written in the vault, the protected areas untouched.
This is the only test that exercises Claude Code's own permission rules; the fake claude cannot.

    CT_REAL_CLAUDE=1 python3 tests/e2e/smoke_real_claude.py
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
import install  # noqa: E402

PROBE = """You are a test probe. Never ask questions. Do exactly these steps, then stop:
0. Read the file .claude/adapters/code.md with the Read tool and note its first heading.
1. With the Write tool, write the file journal/reports/smoke.md containing two lines: smoke ok, then the heading you read in step 0 (or UNREADABLE if step 0 was refused)
2. Write the file .claude/settings.json containing {}
3. Write the file ../outside.md containing x
Reply with one line per step: the step number and whether it succeeded or was refused."""


def main():
    if os.environ.get('CT_REAL_CLAUDE') != '1':
        print('skipped: set CT_REAL_CLAUDE=1 to run (uses the real claude CLI and your account)')
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        vault, ct = os.path.join(tmp, "smoke vault's"), os.path.join(tmp, 'ct')
        answers = {'owner_name': 'Smoke', 'owner_handle': 'smoke', 'timezone': 'UTC', 'vault_path': vault, 'ct_home': ct,
                   'packs': ['developer'], 'tools': {'code': 'github'}, 'scheduler': 'none'}
        install.install(answers, log=lambda *a: None)
        jd = os.path.join(ct, 'jobs', 'morning-prs')
        open(os.path.join(jd, 'prompt.md'), 'w').write(PROBE)
        job = json.load(open(os.path.join(jd, 'job.json')))
        job.update(model='haiku', timeout=300)
        json.dump(job, open(os.path.join(jd, 'job.json'), 'w'))
        settings_before = open(os.path.join(vault, '.claude', 'settings.json')).read() if os.path.exists(os.path.join(vault, '.claude', 'settings.json')) else None
        r = subprocess.run([sys.executable, os.path.join(ct, 'bin', 'run_job.py'), '--job', 'morning-prs', '--ct-home', ct], capture_output=True, text=True)
        log = open(os.path.join(ct, 'logs', 'morning-prs.log')).read() if os.path.exists(os.path.join(ct, 'logs', 'morning-prs.log')) else r.stderr
        checks = [
            ('the job ran (rc=0)', r.returncode == 0),
            ('report written inside the vault', os.path.isfile(os.path.join(vault, 'journal', 'reports', 'smoke.md'))),
            ('the job could read its adapter note', os.path.isfile(os.path.join(vault, 'journal', 'reports', 'smoke.md'))
             and 'UNREADABLE' not in open(os.path.join(vault, 'journal', 'reports', 'smoke.md')).read()),
            ('.claude/settings.json untouched', (open(os.path.join(vault, '.claude', 'settings.json')).read() if os.path.exists(os.path.join(vault, '.claude', 'settings.json')) else None) == settings_before),
            ('nothing written outside the vault', not os.path.exists(os.path.join(tmp, 'outside.md'))),
        ]
        for name, ok in checks:
            print(('  ok   ' if ok else '  FAIL ') + name)
        print('\n--- job log ---\n' + log[-1200:])
        return 0 if all(ok for _, ok in checks) else 1


if __name__ == '__main__':
    sys.exit(main())
