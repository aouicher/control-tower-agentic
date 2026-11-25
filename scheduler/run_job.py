#!/usr/bin/env python3
"""Run one scheduled job unattended with Claude Code. Standard library only.

Usage:
    python3 run_job.py --job <id> --ct-home <dir> [--dry-run]

Layout read from <ct-home>:
    install.json                    {"vault": ..., "claude_bin": ..., "timezone": ...}
    jobs/<id>/prompt.md             the rendered prompt
    jobs/<id>/job.json              id, model, timeout
    jobs/<id>/settings.json         permissions and the guard hook for this job

What it does:
  * one run at a time per job (lock directory with the PID; a stale lock is reclaimed)
  * runs `claude -p` inside the vault with the job's settings and `--permission-mode dontAsk`
    (anything not explicitly allowed is refused) and a time limit (default 30 minutes)
  * appends the cost, turns and the final answer to <ct-home>/logs/<id>.log, errors to <id>.stderr.log
  * sends a desktop notification when the run fails (best effort)
Set CT_CLAUDE_BIN to use another executable (used by the tests).
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

DEFAULT_TIMEOUT = 1800
EXTRA_PATH = ['~/.local/bin', '/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin']


def load(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True


def acquire_lock(lock_dir):
    os.makedirs(os.path.dirname(lock_dir), exist_ok=True)
    try:
        os.mkdir(lock_dir)
    except FileExistsError:
        try:
            pid = int(open(os.path.join(lock_dir, 'pid')).read().strip())
        except (OSError, ValueError):
            pid = -1
        if pid > 0 and pid_alive(pid):
            return False
        shutil.rmtree(lock_dir, ignore_errors=True)
        os.mkdir(lock_dir)
    with open(os.path.join(lock_dir, 'pid'), 'w') as fh:
        fh.write(str(os.getpid()))
    return True


def notify(title, message):
    try:
        if sys.platform == 'darwin' and shutil.which('osascript'):
            subprocess.run(['osascript', '-e', f'display notification "{message}" with title "{title}"'],
                           capture_output=True, timeout=10)
        elif shutil.which('notify-send'):
            subprocess.run(['notify-send', title, message], capture_output=True, timeout=10)
    except Exception:
        pass


def build_command(claude_bin, job, prompt, settings_path):
    return [claude_bin, '-p', prompt, '--model', job.get('model', 'sonnet'),
            '--permission-mode', 'dontAsk', '--setting-sources', 'project',
            '--settings', settings_path, '--output-format', 'json']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--job', required=True)
    ap.add_argument('--ct-home', required=True)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    home = os.path.abspath(os.path.expanduser(args.ct_home))
    install = load(os.path.join(home, 'install.json'))
    jdir = os.path.join(home, 'jobs', args.job)
    job = load(os.path.join(jdir, 'job.json'))
    with open(os.path.join(jdir, 'prompt.md'), encoding='utf-8') as fh:
        prompt = fh.read()
    settings = os.path.join(jdir, 'settings.json')
    vault = os.path.expanduser(install['vault'])
    claude_bin = os.environ.get('CT_CLAUDE_BIN') or install.get('claude_bin', 'claude')
    cmd = build_command(claude_bin, job, prompt, settings)

    if args.dry_run:
        shown = list(cmd)
        shown[2] = prompt[:80].replace('\n', ' ') + ('...' if len(prompt) > 80 else '')
        print(json.dumps({'cwd': vault, 'command': shown}, indent=2))
        return 0

    logs = os.path.join(home, 'logs')
    os.makedirs(logs, exist_ok=True)
    log, err = os.path.join(logs, f'{args.job}.log'), os.path.join(logs, f'{args.job}.stderr.log')
    now = lambda: datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    lock = os.path.join(home, 'locks', args.job + '.lock')
    if not acquire_lock(lock):
        with open(log, 'a', encoding='utf-8') as fh:
            fh.write(f'{now()} {args.job} skipped: already running\n')
        return 0
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join([os.path.expanduser(p) for p in EXTRA_PATH] + [env.get('PATH', '')])
    started = now()
    try:
        proc = subprocess.run(cmd, cwd=vault, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=int(job.get('timeout', DEFAULT_TIMEOUT)))
        rc, out, errtxt = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        rc, out, errtxt = 124, '', 'timed out'
    except FileNotFoundError:
        rc, out, errtxt = 127, '', f'executable not found: {claude_bin}'
    finally:
        shutil.rmtree(lock, ignore_errors=True)

    summary, failed = '', rc != 0
    try:
        data = json.loads(out)
        failed = failed or bool(data.get('is_error'))
        summary = f"cost=${data.get('total_cost_usd', '?')} turns={data.get('num_turns', '?')} error={data.get('is_error', '?')}\n"
        summary += '\n'.join(str(data.get('result', '')).split('\n')[:60])
    except (json.JSONDecodeError, AttributeError):
        summary = out[:2000]
    with open(log, 'a', encoding='utf-8') as fh:
        fh.write(f'=== {started} {args.job} rc={rc}\n{summary}\n\n')
    if errtxt:
        with open(err, 'a', encoding='utf-8') as fh:
            fh.write(f'=== {started} {args.job}\n{errtxt}\n')
    if failed:
        notify('Control tower', f'Job {args.job} failed (rc={rc}). See {log}')
    return rc


if __name__ == '__main__':
    sys.exit(main())
