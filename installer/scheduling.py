#!/usr/bin/env python3
"""The schedule of an install: the job times in machine time, the launchd agents (macOS) and the crontab block (Linux)
that run the jobs, and loading or unloading them. Standard library only."""
import datetime
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import zoneinfo


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


LAUNCH_AGENTS = '~/Library/LaunchAgents'
CRON_BEGIN, CRON_END = '# BEGIN control-tower', '# END control-tower'
CRON_BLOCK = re.compile(re.escape(CRON_BEGIN) + r'.*?' + re.escape(CRON_END) + r'\n?', re.S)


def cron_header(sched_dir):
    """The first line of the crontab block of the install whose schedule is in `sched_dir`: one block per install."""
    return f'{CRON_BEGIN} {os.path.dirname(sched_dir)}\n'


def own_cron_block(block, sched_dir):
    """Whether a crontab block is this install's: its header names the runtime folder, or names none."""
    return block.startswith((cron_header(sched_dir), CRON_BEGIN + '\n'))


def cron_applied(sched_dir):
    """Whether the user's crontab holds the block of the install whose schedule is in `sched_dir`."""
    if not shutil.which('crontab'):
        return False
    cur = subprocess.run(['crontab', '-l'], capture_output=True, text=True).stdout
    return any(own_cron_block(m.group(0), sched_dir) for m in CRON_BLOCK.finditer(cur))


def agents_dir(launch_agents_dir=None):
    return os.path.abspath(os.path.expanduser(launch_agents_dir or LAUNCH_AGENTS))


def schedule_applied(kind, sched_dir, launch_agents_dir=None):
    """Whether the install whose schedule is in `sched_dir` has its jobs loaded (its launchd agents, or the crontab block)."""
    if kind == 'launchd':
        return bool(own_agents(agents_dir(launch_agents_dir), sched_dir))
    return kind == 'cron' and cron_applied(sched_dir)


def cron_home(block):
    """The runtime folder a crontab block's header names ('' when it names none): the reverse of cron_header."""
    return block.split('\n', 1)[0][len(CRON_BEGIN):].strip()


def agent_home(link):
    """The runtime folder a launchd agent links into (<home>/schedule/launchd/<label>.plist)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(link))))


def own_agents(dest, sched_dir):
    """The launchd agents of the install whose schedule is in `sched_dir` (links into it): another install's stay untouched."""
    mine = os.path.realpath(sched_dir) + os.sep
    return [f for f in sorted(os.listdir(dest)) if f.startswith('com.control-tower.')
            and os.path.realpath(os.path.join(dest, f)).startswith(mine)] if os.path.isdir(dest) else []


def apply(kind, plist_paths, sched_dir, launch_agents_dir, no_launchctl, report, unload=False):
    """Load this install's schedule (launchd agents or the crontab block), or with `unload` remove all of it."""
    plist_paths = [] if unload else plist_paths
    if kind == 'launchd':
        dest = agents_dir(launch_agents_dir)
        os.makedirs(dest, exist_ok=True)
        current = {label for label, _ in plist_paths}
        for f in own_agents(dest, sched_dir):  # stale agents of this install (labels are per job id, one install per job)
            label = f[:-6] if f.endswith('.plist') else f
            if label not in current:
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
            report['warnings'].append('crontab is not available on this computer: the jobs are not scheduled')
            return False
        got = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if got.returncode != 0 and 'no crontab' not in got.stderr.lower():
            report['warnings'].append(f'could not read your crontab, nothing changed: {got.stderr.strip()}')
            return False
        cur = got.stdout if got.returncode == 0 else ''
        cur = CRON_BLOCK.sub(lambda m: '' if own_cron_block(m.group(0), sched_dir) else m.group(0), cur)
        cron_file = os.path.join(sched_dir, 'crontab.txt')
        block = '' if unload or not os.path.exists(cron_file) else open(cron_file, encoding='utf-8').read()
        new = cur.rstrip('\n') + ('\n' if cur.strip() else '') + block
        r = subprocess.run(['crontab', '-'], input=new, capture_output=True, text=True)
        if r.returncode != 0:
            report['warnings'].append(f'could not write your crontab: {r.stderr.strip()}')
        return r.returncode == 0
    return False
