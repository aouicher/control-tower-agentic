#!/usr/bin/env python3
"""Remove the control tower runtime and, optionally, the files the installer created in the vault.

    python3 installer/uninstall.py --ct-home ~/.control-tower [--vault ~/my-vault] [--remove-vault-files] [--yes]

Safe by default:
  * without --yes it only lists what it would do;
  * your notes are never removed. With --remove-vault-files, only files that the installer created AND that you
    have not edited since (same checksum as in the manifest) are deleted, then empty folders;
  * scheduled jobs are unloaded (launchd) or removed from the crontab block "control-tower".
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import install  # noqa: E402


def sha(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ct-home', default='~/.control-tower')
    ap.add_argument('--vault')
    ap.add_argument('--remove-vault-files', action='store_true')
    ap.add_argument('--launch-agents-dir')
    ap.add_argument('--no-launchctl', action='store_true')
    ap.add_argument('--yes', action='store_true')
    args = ap.parse_args()
    ct = os.path.abspath(os.path.expanduser(args.ct_home))
    plan = []
    # the runtime folder is removed recursively: only accept one the installer made
    vault_abs = os.path.realpath(os.path.expanduser(args.vault)) if args.vault else None
    if os.path.isdir(ct):
        marker = os.path.join(ct, 'install.json')
        bad = os.path.realpath(ct) in (os.path.realpath(os.path.expanduser('~')), '/') or os.path.realpath(ct) == vault_abs
        try:
            ok = not bad and 'vault' in json.load(open(marker, encoding='utf-8'))
        except (OSError, ValueError):
            ok = False
        if not ok:
            print(f'refusing: {ct} is not a control tower runtime folder (no install.json from the installer). Nothing was removed.',
                  file=sys.stderr)
            sys.exit(2)

    # scheduled jobs
    sched = os.path.join(ct, 'schedule')
    agents = install.own_agents(install.agents_dir(args.launch_agents_dir), sched)  # another install's agents stay
    cron = install.cron_applied(sched)
    plan += [('unload', f) for f in agents] + ([('crontab', 'remove the control-tower block')] if cron else [])
    loaded = (['launchd'] if agents else []) + (['cron'] if cron else [])
    if os.path.isdir(ct):
        plan.append(('rmtree', ct))

    # vault files
    removable, modified = [], []
    if args.vault and args.remove_vault_files:
        vault = os.path.abspath(os.path.expanduser(args.vault))
        mp = os.path.join(vault, '.control-tower', 'manifest.json')
        if not os.path.isfile(mp):
            print('no manifest in the vault: nothing will be removed there', file=sys.stderr)
        else:
            for rel, checksum in json.load(open(mp, encoding='utf-8')).get('files', {}).items():
                p = os.path.join(vault, rel)
                if not os.path.isfile(p):
                    continue
                (removable if checksum and sha(p) == checksum else modified).append(rel)
            plan.append(('remove-files', f'{len(removable)} unmodified installed file(s)'))
            plan.append(('keep-files', f'{len(modified)} file(s) you edited are kept'))

    for kind, what in plan:
        print(f'{"would " if not args.yes else ""}{kind}: {what}')
    if not plan:
        print('nothing to do')
    if not args.yes:
        print('\nDry run. Add --yes to apply.')
        return
    report = {'warnings': []}
    for kind in loaded:
        install.apply(kind, [], sched, args.launch_agents_dir, args.no_launchctl, report, unload=True)
    for w in report['warnings']:
        print(f'warning: {w}', file=sys.stderr)
    for kind, what in plan:
        if kind == 'rmtree':
            shutil.rmtree(what)
    if removable:
        vault = os.path.abspath(os.path.expanduser(args.vault))
        parents = set()
        for rel in removable:
            os.remove(os.path.join(vault, rel))
            parents.add(os.path.dirname(os.path.join(vault, rel)))
        for d in sorted(parents, key=len, reverse=True):  # only folders that held installed files, deepest first
            while d != vault and os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                d = os.path.dirname(d)
        shutil.rmtree(os.path.join(vault, '.control-tower'), ignore_errors=True)
    print('\nDone.')


if __name__ == '__main__':
    main()
