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
  * reads Claude Code's stream-json output and writes what was refused during the run to <ct-home>/logs/<id>.denials.json,
    and the run's outcome (ok, refused, auth, server, timeout, network, failed), the MCP servers that did not start and the hosts the
    sandbox blocked to <ct-home>/logs/<id>.run.json (the /job-permissions skill reads both)
  * when a run's outcome is not ok, sends a desktop notification that says what happened and what to type in the vault
    (best effort)
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

import guard  # installed next to this file: the script's folder is on the path

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
    midnight = lambda d: int(datetime.datetime.combine(d, datetime.time(), now.tzinfo).timestamp())  # local midnight
    return '\n'.join([
        '## Run context', '', 'Computed by the job runner: take every date and time from here and do not run `date`.', '',
        f'- Now: {now:%Y-%m-%d %H:%M} ({now:%d/%m/%Y at %H:%M}), {DAYS[day.weekday()]}, {zone}',
        f'- Today: {day}', f'- Year: {day.year}', f'- ISO week: {week(day)}',
        f'- Last complete ISO week: {week(day - 7 * one)}', f'- The week before: {week(day - 14 * one)}',
        f'- Previous working day: {before}, {DAYS[before.weekday()]}',
        f'- Unix time (epoch seconds, for tools that take one): now {int(now.timestamp())}, today 00:00 {midnight(day)}, '
        f'previous working day 00:00 {midnight(before)}', ''])


def redact(text, tail=False):
    """The text with values that look like secrets hidden, then cut to 300 characters (its start, or its end)."""
    clean = SECRET_VALUE.sub(lambda m: m.group(1) + '[hidden]', str(text))
    return clean[-300:] if tail else clean[:300]


def guard_reasons(msgs, hook):
    """{tool_use_id: reason} for the calls the guard hook (its exact command, from the job's settings) stopped: Claude Code
    reports each as an error tool result that starts with the hook's message, and as a permission denial of the same id
    (runtime fact F10)."""
    stopped = re.compile(r'PreToolUse:[^\s:]+ hook error: \[' + re.escape(hook) + r'\]: ' + re.escape(BLOCKED) + r'(.*)', re.S)
    out = {}
    for m in msgs:
        for b in ((m.get('message') or {}).get('content') or []) if m.get('type') == 'user' else []:
            match = stopped.match(b.get('content')) if isinstance(b, dict) and b.get('is_error') and isinstance(b.get('content'), str) else None
            if match:
                out[b.get('tool_use_id')] = match.group(1).strip()
    return out


def guard_command(settings):
    """The guard hook's command in a job's settings (the installer writes one), or '' when there is none."""
    hooks = [h for e in (settings.get('hooks') or {}).get('PreToolUse') or [] for h in e.get('hooks') or []]
    return next((str(h.get('command')) for h in hooks if 'guard.py' in str(h.get('command'))), '')


def denials(data, msgs, at, hook=''):
    """What was refused during the run: Claude Code's permission denials (a rule missing), and among them the guard's blocks,
    which no rule can allow. A guard message only labels a call Claude Code reports as refused, so text cannot add one."""
    out, guarded = [], guard_reasons(msgs, hook) if hook else {}
    for d in data.get('permission_denials') or []:
        if not isinstance(d, dict):
            continue
        if d.get('tool_use_id') in guarded:
            out.append({'tool': 'guard', 'input': '', 'reason': redact(guarded[d['tool_use_id']]), 'source': 'guard', 'at': at})
            continue
        tool, inp = str(d.get('tool_name') or '?'), d.get('tool_input')
        if tool == 'Bash' and isinstance(inp, dict):
            text = inp.get('command', '')
        elif isinstance(inp, dict):  # never keep values of keys that look like credentials
            text = json.dumps({k: v for k, v in inp.items() if not SECRET_KEY.search(str(k))}, ensure_ascii=False, sort_keys=True)
        else:
            text = inp or ''
        out.append({'tool': tool, 'input': redact(text), 'reason': 'not allowed for this job', 'source': 'permissions', 'at': at})
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


def notice(name, vault, result, servers=()):
    """What the notification says about a run of outcome `result`, or None when all went well: what happened, and the words
    that start the fix in the vault. A server that needs a sign-in or did not start does not make the run fail, so it is
    named here."""
    def named(status):
        names = [s['name'][:40] for s in servers if s['status'] == status]
        return names[0] + (f' and {len(names) - 1} more' if len(names) > 1 else '') if names else 'a tool'
    what = {'refused': 'was blocked', 'network': 'was blocked', 'timeout': 'ran out of time', 'failed': 'failed',
            'auth': f'could not reach {named("needs-auth")}: sign in again', 'server': f'could not start {named("failed")}'}.get(result)
    return f'{name} {what}. Open Claude on your {os.path.basename(os.path.normpath(vault))} folder and say: fix my job.' if what else None


def messages(text):
    """The JSON objects of Claude Code's stream-json output, one per line."""
    out = []
    for line in text.split('\n'):  # never splitlines: U+2028 and its kin stay unescaped inside a JSON string
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if isinstance(m, dict):
            out.append(m)
    return out


def init_of(msgs):
    return next((m for m in msgs if m.get('type') == 'system' and m.get('subtype') == 'init'), {})


def result_of(msgs):
    return next((m for m in reversed(msgs) if m.get('type') == 'result'), {})


def tool_output(msgs, tool=None):
    """The tool results the model saw, as one text (see tool_results)."""
    return '\n'.join(tool_results(msgs, tool))


def tool_results(msgs, tool=None, failed=False):
    """The tool results the model saw (stream-json `user` messages), one text each: every one, or only those of `tool` calls,
    and with `failed` only the ones Claude Code marked as errors."""
    calls = {b.get('id') for m in msgs if tool and m.get('type') == 'assistant' for b in ((m.get('message') or {}).get('content') or [])
             if isinstance(b, dict) and b.get('type') == 'tool_use' and b.get('name') == tool}
    parts = []
    for m in msgs:
        content = (m.get('message') or {}).get('content') if m.get('type') == 'user' else None
        for block in content if isinstance(content, list) else []:
            if (isinstance(block, dict) and block.get('type') == 'tool_result' and (tool is None or block.get('tool_use_id') in calls)
                    and (block.get('is_error') or not failed)):
                inner = block.get('content')
                parts.append(inner if isinstance(inner, str) else '\n'.join(str(b.get('text', '')) for b in inner or [] if isinstance(b, dict)))
    return parts


SANDBOX_BLOCK = re.compile(r'<sandbox_violations>((?:(?!<sandbox_violations>).)*)</sandbox_violations>\s*\Z', re.S)


def blocked_hosts(text):
    """Hosts the sandbox refused, from the `<sandbox_violations>` block Claude Code appends at the very end of one command's
    output; a block anywhere else is text the command printed (a ticket, a page) and is ignored."""
    m = SANDBOX_BLOCK.search(text)
    return sorted({h.lower() for h in re.findall(r'deny network-outbound ([A-Za-z0-9.-]+):\d+', m.group(1))}) if m else []


AUTH = re.compile(r'(?i)\b(401|unauthori[sz]ed|authenticat\w*|needs[- ]auth|sign[- ]?in|log[- ]?in again|expired)\b')


def outcome(rc, failed, refused, servers, hosts, error):
    """The run in one word, for the diagnosis in /job-permissions."""
    if rc == 124:
        return 'timeout'
    if refused:
        return 'refused'
    if hosts:
        return 'network'
    if any(s['status'] == 'needs-auth' for s in servers) or (failed and AUTH.search(error)):
        return 'auth'
    if any(s['status'] == 'failed' for s in servers):  # a connection that did not start: the run may still succeed without it
        return 'server'
    return 'failed' if failed else 'ok'


NO_SERVERS = '{"mcpServers": {}}'  # for a job installed without an mcp.json


def build_command(claude_bin, job, prompt, settings_path):
    # only the MCP servers the installer copied for this job (connected ones, as approved), never the vault's .mcp.json
    mcp = os.path.join(os.path.dirname(settings_path), 'mcp.json')
    return [claude_bin, '-p', prompt, '--model', job.get('model', 'sonnet'),
            '--permission-mode', 'dontAsk', '--setting-sources', 'project', '--settings', settings_path,
            '--mcp-config', mcp if os.path.isfile(mcp) else NO_SERVERS, '--strict-mcp-config', '--output-format', 'stream-json', '--verbose']


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
    risky = guard.risky_settings(os.path.join(vault, '.claude', 'settings.json'))
    if risky:  # project settings load into every job: a rule or a hook there would run with it
        with open(log, 'a', encoding='utf-8') as fh:
            fh.write(f'{now()} {args.job} refused: the vault\'s .claude/settings.json sets {", ".join(risky)}, which would widen '
                     'every job; keep it empty for jobs (Check my setup in /control-tower says what to do)\n')
        notify('Control tower', f'Job {args.job} did not run: the vault settings would widen it. Open Claude in the vault and say: check my setup.')
        return 3
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

    msgs = messages(out)
    data = result_of(msgs)
    failed = rc != 0 or not data or bool(data.get('is_error'))  # no result message at all: the run is not trusted to be fine
    if data:
        summary = f"cost=${data.get('total_cost_usd', '?')} turns={data.get('num_turns', '?')} error={data.get('is_error', '?')}\n"
        summary += '\n'.join(str(data.get('result', '')).split('\n')[:60])
    else:
        summary = out[:2000]
    refused = denials(data, msgs, started, guard_command(load(settings)))
    servers = [{'name': str(s.get('name')), 'status': str(s.get('status'))} for s in init_of(msgs).get('mcp_servers') or []
               if isinstance(s, dict) and s.get('status') != 'connected']
    # the sandbox's own refusals: a command it stopped fails; a command that only printed such a block (a ticket) did not
    hosts = sorted({h for r in tool_results(msgs, 'Bash', failed=True) for h in blocked_hosts(r)})
    why = str(data.get('result', '')) if data.get('is_error') else errtxt or ('' if data else 'no result from Claude Code')
    error = redact(why, tail=True) if failed else ''  # its end says why
    result = outcome(rc, failed, refused, servers, hosts, error)
    with open(os.path.join(logs, f'{args.job}.run.json'), 'w', encoding='utf-8') as fh:  # the latest run, for the diagnosis
        json.dump({'at': started, 'rc': rc, 'outcome': result, 'servers': servers,
                   'blocked_hosts': hosts, 'error': error}, fh, indent=2, ensure_ascii=False)
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
    message = notice(job.get('name', args.job), vault, result, servers)
    if message:
        notify('Control tower', message)
    return rc


if __name__ == '__main__':
    sys.exit(main())
