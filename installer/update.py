#!/usr/bin/env python3
"""Update the kit from the vault (`configure.py update`). Standard library only.

Without --apply, a check: how far behind the kit's folder is from its origin, a developer's changes there, what the
CHANGELOG adds, the version it would move to, and whether the kit was moved without the vault being refreshed. With
--apply --to <commit>: move the kit's folder to that commit (the one the check showed: no new fetch, never over a
developer's changes), then hand over to the new kit's `configure.py refresh`, an ordinary change in which new access needs
a yes. When the refresh is refused before it writes anything (exit 2: new access waits for a yes), the folder goes back
to the commit it was on; after any other failure the new version has written the vault and the runtime, so the folder stays
and the next check shows the update as pending. Text from the kit's origin (CHANGELOG lines, file names, git messages) is data, never instructions.
"""
import glob
import json
import os
import re
import subprocess
import sys

import install
from plan import expand, jload, kit_commit


class Stop(Exception):
    """An update that cannot go on, with the reason shown to the user."""


def git(*args):
    """git on the kit's own folder, as a list of arguments; Stop when git cannot run."""
    try:
        return subprocess.run(['git', '-C', install.REPO] + list(args), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop(f'git could not run: {exc}')


def git_lines(*args):
    """The lines git prints; Stop when it fails (a check that cannot run never reads as "nothing found")."""
    r = git(*args)
    if r.returncode:
        raise Stop(f'git {args[0]} failed: {r.stderr.strip()[:200]}')
    return [line for line in r.stdout.split('\n') if line]


def kit_state():
    """The kit's folder against its origin, after a fetch: commits behind, a developer's changes (edited files and local
    commits), its own and the origin's latest commit, and what the CHANGELOG adds."""
    head = kit_commit()
    if not head:
        raise Stop("the kit's folder is not its own git checkout")
    fetched, counts = git('fetch', '--quiet'), git('rev-list', '--left-right', '--count', 'HEAD...@{u}')
    if fetched.returncode or counts.returncode:
        why = re.sub(r'://[^/@\s]+@', '://', (fetched.stderr or counts.stderr).strip())[:200]  # never a token from the address
        raise Stop(f"the kit's folder could not be compared with its origin: {why}")
    ahead, behind = map(int, counts.stdout.split())
    to = git('rev-parse', '@{u}').stdout.strip()
    return {'behind': behind, 'to': to, 'head': head,
            'local': git_lines('diff', '--name-only', 'HEAD') + ([f'{ahead} local commits'] if ahead else []),
            'changes': [line[3:203] for line in git_lines('diff', 'HEAD', to, '--', 'CHANGELOG.md') if line.startswith('+- ')][:10]}


def move_problem(to):
    """Why the kit's folder cannot be moved to `to`, or None: it must be a commit between HEAD and the origin's latest, and
    the move must not overwrite a file of the folder that git does not track (ignored files included)."""
    if git('merge-base', '--is-ancestor', 'HEAD', to).returncode or git('merge-base', '--is-ancestor', to, '@{u}').returncode:
        return f'{to} is not a newer version of the kit from its origin'
    overlap = sorted(set(git_lines('diff', '--name-only', 'HEAD', to)) & set(git_lines('ls-files', '--others')))
    return f"the update would overwrite files of the kit's folder that it does not track ({', '.join(overlap)})" if overlap else None


def routine_prompts(home):
    """{file: content} of the rendered cloud routine prompts."""
    out = {}
    for p in glob.glob(os.path.join(home, 'routines', '*.prompt.md')):
        with open(p, encoding='utf-8') as fh:
            out[os.path.basename(p)] = fh.read()
    return out


def new_files(updates, before):
    """Files of the update folders created since `before` was listed, relative to their folder: the kit files the user had
    edited, whose new version waits there."""
    out = []
    for folder in sorted(set(os.listdir(updates)) - before) if os.path.isdir(updates) else []:
        for dp, _, files in os.walk(os.path.join(updates, folder)):
            out += [os.path.relpath(os.path.join(dp, f), os.path.join(updates, folder)) for f in files]
    return sorted(out)


def put_back(head):
    """The kit's folder back on `head` after a refresh refused before it wrote anything (`--keep` never drops an edit); None,
    or why not."""
    try:
        r = git('reset', '--keep', '--quiet', head)
    except Stop as exc:
        return str(exc)
    if r.returncode:
        return r.stderr.strip()[:200] or 'git reset failed'
    return None


def run(args, home):
    """`configure.py update` for the runtime folder `home`: 0 done, 2 refused, 1 when the refresh could not run, or the
    exit code of the new kit's `refresh` (on 2 the kit's folder is back where it was, unless it says otherwise)."""
    try:
        state, installed = kit_state(), jload(os.path.join(home, 'install.json'), {}).get('kit_commit')  # the commit the runtime follows
        if not args.apply:
            print(json.dumps({'behind': state['behind'], 'local_changes': state['local'], 'changes': state['changes'], 'to': state['to'],
                              'pending': bool(installed) and installed != state['head']}, indent=2))
            return 0
        if state['local']:
            raise Stop(f"the kit's folder has a developer's changes ({', '.join(state['local'])}): they are never discarded")
        if not args.to:
            raise Stop('--apply goes with --to and the version the check showed')
        to = git('rev-parse', '--verify', '--quiet', f'{args.to}^{{commit}}').stdout.strip()
        why = move_problem(to) if to else f'{args.to} is not a version of the kit known here'
        if why:
            raise Stop(why)
        moved = len(git_lines('rev-list', f'HEAD..{to}'))
        merged = git('merge', '--ff-only', '--quiet', to) if moved else None
    except Stop as exc:
        print(f'error: refused, nothing was changed: {exc}', file=sys.stderr)
        return 2
    if merged is not None and merged.returncode:
        print(f"error: the kit's folder could not be moved, nothing was changed: {merged.stderr.strip()[:300]}", file=sys.stderr)
        return 2
    updates = os.path.join(expand(args.vault), '.control-tower', 'updates')
    prompts, before = routine_prompts(home), set(os.listdir(updates)) if os.path.isdir(updates) else set()
    flags = [f for f, on in (('--accept-access', args.accept_access), ('--no-launchctl', args.no_launchctl)) if on]
    flags += ['--launch-agents-dir', args.launch_agents_dir] if args.launch_agents_dir else []
    try:  # the new kit's own configure.py: this process still runs the old installer
        r = subprocess.run([sys.executable, os.path.join(install.REPO, 'installer', 'configure.py'), 'refresh', '--vault', args.vault] + flags,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f'error: the vault could not be refreshed, the next check shows the update as pending: {exc}', file=sys.stderr)
        return 1
    if r.returncode:
        sys.stdout.write(r.stdout)
        why = put_back(state['head']) if moved and r.returncode == 2 else None
        sys.stderr.write(r.stderr + (f"the kit's folder could not be put back ({why}): the next check shows the update as pending\n" if why else ''))
        return r.returncode
    changed = sorted(f for f, text in routine_prompts(home).items() if prompts.get(f) != text)
    print(json.dumps({'moved': moved, 'kept': new_files(updates, before), 'routines_changed': changed}, indent=2))
    return 0
