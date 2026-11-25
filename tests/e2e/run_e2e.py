#!/usr/bin/env python3
"""End-to-end install test in a disposable HOME. Standard library only; touches nothing outside a temp directory.

For every pack (and all packs together) it: installs from answers, runs the doctor, runs every installed job through the
real runner with the fake `claude`, checks the hook blocks hostile calls, generates and lints the schedule, then uninstalls
and checks that user-edited files survive.

    python3 tests/e2e/run_e2e.py            # from the repository root
Exit code 0 means everything passed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
FAKE = os.path.join(ROOT, 'tests', 'e2e', 'fake_claude.py')
failures = []


def step(name, cond, detail=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (f': {detail}' if detail and not cond else ''))
    if not cond:
        failures.append(name)


def run(cmd, env, **kw):
    return subprocess.run(cmd, env=env, capture_output=True, text=True, **kw)


def scenario(packs):
    label = '+'.join(packs)
    print(f'\n== {label}')
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, HOME=home, CT_CLAUDE_BIN=FAKE, FAKE_CLAUDE_LOG=os.path.join(home, 'fake.log'))
        env.pop('CT_HOME', None)
        vault, ct = os.path.join(home, 'vault'), os.path.join(home, '.control-tower')
        tools = {}
        for p in packs:
            for q in json.load(open(os.path.join(ROOT, 'packs', p, 'pack.json')))['questions']:
                tools.setdefault(q['capability'], next((c for c in q['choices'] if c != 'none'), 'none'))
        answers = {'owner_name': 'E2E User', 'owner_handle': 'e2e', 'timezone': 'UTC', 'vault_path': vault, 'ct_home': ct,
                   'packs': packs, 'tools': tools, 'scheduler': 'launchd' if sys.platform == 'darwin' else 'cron', 'claude_bin': FAKE}
        ap = os.path.join(home, 'answers.json')
        json.dump(answers, open(ap, 'w'))
        inst = os.path.join(ROOT, 'installer', 'install.py')
        r = run([PY, inst, '--answers', ap, '--dry-run'], env)
        step('dry run succeeds and writes nothing', r.returncode == 0 and not os.path.exists(vault), r.stderr[-300:])
        r = run([PY, inst, '--answers', ap], env)
        step('install succeeds', r.returncode == 0, r.stderr[-300:])
        r = run([PY, inst, '--answers', ap], env)
        step('second install is idempotent (0 created)', r.returncode == 0 and 'Files: 0 created' in r.stdout, r.stdout[-200:])
        r = run([PY, os.path.join(ROOT, 'installer', 'doctor.py'), '--vault', vault, '--ct-home', ct, '--claude-bin', FAKE], env)
        step('doctor reports no failure', r.returncode == 0, r.stdout[-400:])
        jobs = sorted(os.listdir(os.path.join(ct, 'jobs'))) if os.path.isdir(os.path.join(ct, 'jobs')) else []
        step('at least one job installed', bool(jobs))
        for j in jobs:
            r = run([PY, os.path.join(ct, 'bin', 'run_job.py'), '--job', j, '--ct-home', ct], env)
            logp = os.path.join(ct, 'logs', f'{j}.log')
            text = open(logp).read() if os.path.exists(logp) else ''
            step(f'job {j} runs and the guard holds', r.returncode == 0 and 'rc=0' in text and 'e2e ok' in text, (text or r.stderr)[-300:])
        calls = [json.loads(x) for x in open(env['FAKE_CLAUDE_LOG'])] if os.path.exists(env['FAKE_CLAUDE_LOG']) else []
        step('jobs ran in the vault with dontAsk', bool(calls) and all(c['mode'] == 'dontAsk' and os.path.realpath(c['cwd']) == os.path.realpath(vault) for c in calls))
        idx = os.path.join(ct, 'routines', 'routines.json')
        routines = json.load(open(idx)) if os.path.exists(idx) else []
        step('cloud routines rendered and indexed', bool(routines) and all(os.path.isfile(r['prompt_file']) and '{{ct.' not in open(r['prompt_file']).read() for r in routines))
        sched = os.path.join(ct, 'schedule')
        step('schedule generated, not loaded', os.path.isdir(sched))
        if sys.platform == 'darwin' and shutil.which('plutil') and os.path.isdir(os.path.join(sched, 'launchd')):
            bad = [f for f in os.listdir(os.path.join(sched, 'launchd')) if run(['plutil', '-lint', os.path.join(sched, 'launchd', f)], env).returncode]
            step('launchd plists lint', not bad, ', '.join(bad))
        if os.environ.get('CT_E2E_CONTAINER') == '1' and answers['scheduler'] == 'cron' and shutil.which('crontab'):
            # only inside the throwaway container: really load the crontab block, then check uninstall removes it
            r = run([PY, inst, '--answers', ap, '--apply-schedule'], env)
            cur = run(['crontab', '-l'], env).stdout
            step('crontab block applied', r.returncode == 0 and '# BEGIN control-tower' in cur, (r.stderr or cur)[-300:])
            step('crontab block lists every job', all(f'--job {j} ' in cur for j in jobs), cur[-300:])
        edited = os.path.join(vault, 'CLAUDE.md')
        open(edited, 'a').write('\nmine\n')
        mine = os.path.join(vault, 'work', 'projects', 'mine.md')
        open(mine, 'w').write('# mine\n')
        un = [PY, os.path.join(ROOT, 'installer', 'uninstall.py'), '--ct-home', ct, '--vault', vault, '--remove-vault-files',
              '--launch-agents-dir', os.path.join(home, 'LA'), '--no-launchctl']
        run(un + ['--yes'], env)
        step('uninstall removes runtime', not os.path.exists(ct))
        if os.environ.get('CT_E2E_CONTAINER') == '1' and shutil.which('crontab'):
            step('uninstall removes the crontab block', '# BEGIN control-tower' not in run(['crontab', '-l'], env).stdout)
        step('uninstall keeps edited and user files', os.path.isfile(edited) and os.path.isfile(mine))
        step('uninstall removed untouched files', not os.path.exists(os.path.join(vault, 'cockpit.md')))


if __name__ == '__main__':
    packs = sorted(d for d in os.listdir(os.path.join(ROOT, 'packs')) if os.path.isfile(os.path.join(ROOT, 'packs', d, 'pack.json')))
    for p in packs:
        scenario([p])
    scenario(packs)
    print('\n' + ('ALL PASSED' if not failures else f'{len(failures)} FAILED: ' + ', '.join(failures)))
    sys.exit(1 if failures else 0)
