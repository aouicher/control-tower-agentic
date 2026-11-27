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
  * writes a `## Run context` block (now, today, ISO weeks, previous working day, in the installed timezone) at the top of
    the prompt, so a job never runs `date`
  * one run at a time per job (lock directory with the PID; a stale lock is reclaimed)
  * runs `claude -p` inside the vault with the job's settings and `--permission-mode dontAsk`
    (anything not explicitly allowed is refused) and a time limit (default 30 minutes)
  * appends the cost, turns and the final answer to <ct-home>/logs/<id>.log, errors to <id>.stderr.log
  * writes what was refused during the run to <ct-home>/logs/<id>.denials.json (the /job-permissions skill reads it)
  * sends a desktop notification when the run fails (best effort)
Set CT_CLAUDE_BIN to use another executable (used by the tests).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEOUT = 1800
EXTRA_PATH = ['~/.local/bin', '/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin']
BLOCKED = 'BLOCKED by control-tower guard: '
SECRET_KEY = re.compile(r'token|secret|passw|api.?key|auth|cookie|credential|bearer', re.I)
SECRET_VALUE = re.compile(r'\b(\w*(?:token|secret|passw|api_?key|auth)\w*=|bearer\s+|token\s+)\S+', re.I)

# Shipped skills that mention a `date` command say this first: a job finds its dates in the Run context, a person gets them
# from `date` in an interactive session.
RUN_CONTEXT_RULE = 'If the prompt has a `## Run context`, take dates and times from it and do not run `date`; otherwise get them as below.'
DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')


def now_in(timezone):
    try:
        return datetime.datetime.now(ZoneInfo(timezone))
    except (ZoneInfoNotFoundError, ValueError):  # unknown zone, or no time zone data on this computer: UTC, the installer's default
        return datetime.datetime.now(datetime.timezone.utc)


def run_context(now):
    """Every date a job needs, computed once by the runner (`now` is timezone-aware)."""
    day, one = now.date(), datetime.timedelta(days=1)

    def week(d):
        year, number, _ = d.isocalendar()
        monday = d - d.weekday() * one
        return f'{year}-W{number:02d}, Monday {monday} to Sunday {monday + 6 * one}'
    before = day - {0: 3, 6: 2}.get(day.weekday(), 1) * one  # Monday and Sunday: Friday; Saturday: Friday too (1 day)
    zone = getattr(now.tzinfo, 'key', None) or now.tzname()
    return '\n'.join([
        '## Run context', '', 'Computed by the job runner: take every date and time from here and do not run `date`.', '',
        f'- Now: {now:%Y-%m-%d %H:%M} ({now:%d/%m/%Y at %H:%M}), {DAYS[day.weekday()]}, {zone}',
        f'- Today: {day}', f'- Year: {day.year}', f'- ISO week: {week(day)}',
        f'- Last complete ISO week: {week(day - 7 * one)}', f'- The week before: {week(day - 14 * one)}',
        f'- Previous working day: {before}, {DAYS[before.weekday()]}', ''])


def redact(text):
    return SECRET_VALUE.sub(lambda m: m.group(1) + '[hidden]', str(text))[:300]


def denials(data, errtxt, at):
    """What was refused during the run: Claude Code's permission denials (rule missing) and the guard's blocks."""
    out = []
    for d in (data.get('permission_denials') if isinstance(data, dict) else None) or []:
        if not isinstance(d, dict):
            continue
        tool, inp = str(d.get('tool_name') or '?'), d.get('tool_input')
        if tool == 'Bash' and isinstance(inp, dict):
            text = inp.get('command', '')
        elif isinstance(inp, dict):  # never keep values of keys that look like credentials
            text = json.dumps({k: v for k, v in inp.items() if not SECRET_KEY.search(str(k))}, ensure_ascii=False, sort_keys=True)
        else:
            text = inp or ''
        out.append({'tool': tool, 'input': redact(text), 'reason': 'not allowed for this job', 'source': 'permissions', 'at': at})
    for line in (errtxt or '').splitlines():
        if BLOCKED in line:
            out.append({'tool': 'guard', 'input': '', 'reason': redact(line.split(BLOCKED, 1)[1]), 'source': 'guard', 'at': at})
    return out


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
        if pid == -1:
            try:  # another runner may be between mkdir and writing its pid: a fresh lock without pid is held
                if time.time() - os.stat(lock_dir).st_mtime < 60:
                    return False
            except OSError:
                pass
        shutil.rmtree(lock_dir, ignore_errors=True)
        try:
            os.mkdir(lock_dir)
        except FileExistsError:
            return False  # lost the race to another runner
    with open(os.path.join(lock_dir, 'pid'), 'w') as fh:
        fh.write(str(os.getpid()))
    return True


def notify(title, message):
    try:
        if sys.platform == 'darwin' and shutil.which('osascript'):
            esc = lambda s: s.replace('\\', '\\\\').replace('"', '\\"')
            subprocess.run(['osascript', '-e', f'display notification "{esc(message)}" with title "{esc(title)}"'],
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
    if not os.path.isfile(os.path.join(jdir, 'job.json')):
        installed = sorted(os.listdir(os.path.join(home, 'jobs'))) if os.path.isdir(os.path.join(home, 'jobs')) else []
        print(f'unknown job "{args.job}". Installed jobs: {", ".join(installed) or "none"}', file=sys.stderr)
        return 2
    job = load(os.path.join(jdir, 'job.json'))
    with open(os.path.join(jdir, 'prompt.md'), encoding='utf-8') as fh:
        prompt = run_context(now_in(install.get('timezone') or 'UTC')) + '\n' + fh.read()
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
        # own process group, so a timeout also stops what claude started (shell commands, MCP servers)
        proc = subprocess.Popen(cmd, cwd=vault, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
        try:
            out, errtxt = proc.communicate(timeout=int(job.get('timeout', DEFAULT_TIMEOUT)))
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.communicate()
            rc, out, errtxt = 124, '', 'timed out'
    except FileNotFoundError:
        rc, out, errtxt = 127, '', f'executable not found: {claude_bin}'
    except OSError as exc:  # not executable, bad interpreter...
        rc, out, errtxt = 126, '', f'cannot run {claude_bin}: {exc}'
    finally:
        shutil.rmtree(lock, ignore_errors=True)

    summary, failed, data = '', rc != 0, None
    try:
        data = json.loads(out)
        failed = failed or bool(data.get('is_error'))
        summary = f"cost=${data.get('total_cost_usd', '?')} turns={data.get('num_turns', '?')} error={data.get('is_error', '?')}\n"
        summary += '\n'.join(str(data.get('result', '')).split('\n')[:60])
    except (json.JSONDecodeError, AttributeError):
        summary = out[:2000]
    refused = denials(data, errtxt, started)
    with open(os.path.join(logs, f'{args.job}.denials.json'), 'w', encoding='utf-8') as fh:  # the latest run only
        json.dump(refused, fh, indent=2, ensure_ascii=False)
    with open(log, 'a', encoding='utf-8') as fh:
        fh.write(f'=== {started} {args.job} rc={rc}\n{summary}\n')
        if refused:
            fh.write(f'denied: {len(refused)} (see logs/{args.job}.denials.json)\n')
        fh.write('\n')
    if errtxt:
        with open(err, 'a', encoding='utf-8') as fh:
            fh.write(f'=== {started} {args.job}\n{errtxt}\n')
    if failed:
        notify('Control tower', f'Job {args.job} failed (rc={rc}). See {log}')
    return rc


if __name__ == '__main__':
    sys.exit(main())
