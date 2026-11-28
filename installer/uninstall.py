#!/usr/bin/env python3
"""Remove the control tower runtime and, optionally, the files the installer created in the vault.

    python3 installer/uninstall.py --ct-home ~/.control-tower [--vault ~/my-vault] [--remove-vault-files]
                                   [--remove-connections] [--remove-kit] [--yes]
    python3 installer/uninstall.py --ct-home ~/.control-tower --schedule-only [--yes]

Safe by default:
  * without --yes it only lists what it would do, the kit's own folder included;
  * your notes are never removed. With --remove-vault-files, only files that the installer created AND that you
    have not edited since (same checksum as in the manifest) are deleted, then empty folders;
  * scheduled jobs are unloaded (launchd) or removed from the crontab block "control-tower"; --schedule-only does
    only that;
  * --remove-connections removes from the vault (`claude mcp remove`) only the MCP servers Claude added for you
    (`connections_added`) whose entry nobody changed since;
  * --remove-kit removes the kit's own folder last, with the runtime, only when its origin holds everything in it (no
    edited, untracked or ignored file but build output, no commit, stash, worktree or rebase of its own), it holds
    neither the vault nor the runtime, and no other vault installed from it runs automatically (its /control-tower
    could no longer stop it).
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import install  # noqa: E402
import scheduling  # noqa: E402
import update  # noqa: E402
from plan import claude_bin, fingerprint, jload, kit_commit, vault_servers  # noqa: E402


def sha(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def inside(path, folder):
    return (os.path.realpath(path) + os.sep).startswith(os.path.realpath(folder) + os.sep)


def from_this_kit(home):
    """Whether the runtime folder `home` may have been installed from this kit: only its vault's manifest naming another
    folder says no. A runtime, vault or manifest that is missing or cannot be read (a drive not mounted) counts as yes."""
    try:
        vault = jload(os.path.join(home, 'install.json')).get('vault')
        repo = jload(os.path.join(vault, '.control-tower', 'manifest.json')).get('repo')
    except (OSError, ValueError, AttributeError, TypeError):
        return True
    return not repo or os.path.realpath(repo) == os.path.realpath(install.REPO)


def other_installs(sched, launch_agents_dir):
    """The runtime folders of the other installs from this kit that run automatically (launchd agents, crontab block)."""
    dest = scheduling.agents_dir(launch_agents_dir)
    mine = set(scheduling.own_agents(dest, sched))
    homes = {os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(os.path.join(dest, f)))))  # <home>/schedule/launchd/x.plist
             for f in (sorted(os.listdir(dest)) if os.path.isdir(dest) else []) if f.startswith('com.control-tower.') and f not in mine}
    if shutil.which('crontab'):
        cron = subprocess.run(['crontab', '-l'], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30).stdout
        homes |= {m.group(0).split('\n', 1)[0][len(scheduling.CRON_BEGIN):].strip() for m in scheduling.CRON_BLOCK.finditer(cron)
                  if not scheduling.own_cron_block(m.group(0), sched)}  # its header names its runtime folder
    return sorted(h for h in homes if h and from_this_kit(h))


def kit_problem(ct, vault, launch_agents_dir):
    """Why the kit's own folder cannot be removed, or None."""
    if not kit_commit(install.REPO):
        return "the kit's folder is not its own git checkout"
    held = [p for p in (vault, ct) if inside(p, install.REPO)]
    if held:
        return f"the kit's folder holds {held[0]}"
    others = other_installs(os.path.join(ct, 'schedule'), launch_agents_dir)
    if others:
        return (f"another vault that may come from it runs automatically ({', '.join(others[:3])}, or a runtime that could not be checked): "
                "without the kit, its /control-tower could not stop it")
    try:
        work = update.developer_work(strict=True)
    except update.Stop as exc:
        return str(exc)
    return f"the kit's folder holds a developer's work its origin does not have ({', '.join(work[:5])})" if work else None


def added_connections(vault):
    """(to remove, kept) among the MCP servers Claude added to the vault for the user (`connections_added`): one whose
    entry changed since it was added is kept, one already gone is left out."""
    try:
        answers, servers = jload(os.path.join(vault, '.control-tower', 'answers.json'), {}), vault_servers(vault)
    except ValueError as exc:
        print(f'warning: the answers or the .mcp.json of this vault cannot be read ({exc}): no connection is removed', file=sys.stderr)
        return [], []
    prints, remove, kept = answers.get('fingerprints') or {}, [], []
    for name in answers.get('connections_added') or []:
        if name in servers:
            (remove if prints.get(name) == fingerprint(servers[name]) else kept).append(name)
    return remove, kept


def installed_files(vault):
    """(unedited, edited) files the installer wrote in the vault, by the manifest's checksums; never a path outside it."""
    unedited, edited = [], []
    try:
        files = jload(os.path.join(vault, '.control-tower', 'manifest.json')).get('files', {})
    except (ValueError, AttributeError) as exc:
        print(f"warning: this vault's manifest cannot be read ({exc}): no vault file is removed", file=sys.stderr)
        return [], []
    for rel, checksum in files.items():
        p = os.path.join(vault, rel)
        if os.path.isabs(rel) or not inside(p, vault) or not os.path.isfile(p):
            continue
        (unedited if checksum and sha(p) == checksum else edited).append(rel)
    return unedited, edited


def refuse(why):
    print(f'refusing: {why}. Nothing was removed.', file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ct-home', default='~/.control-tower')
    ap.add_argument('--vault')
    ap.add_argument('--remove-vault-files', action='store_true')
    ap.add_argument('--schedule-only', action='store_true', help='unload the schedule and keep everything else')
    ap.add_argument('--remove-connections', action='store_true', help='also remove the MCP servers Claude added for you (needs --vault)')
    ap.add_argument('--remove-kit', action='store_true', help="also remove the kit's own folder, last (needs --vault)")
    ap.add_argument('--launch-agents-dir')
    ap.add_argument('--no-launchctl', action='store_true')
    ap.add_argument('--yes', action='store_true')
    args = ap.parse_args()
    ct = os.path.abspath(os.path.expanduser(args.ct_home))
    vault = os.path.abspath(os.path.expanduser(args.vault)) if args.vault else None
    if args.schedule_only and (args.remove_vault_files or args.remove_connections or args.remove_kit):
        refuse('--schedule-only keeps everything else, it goes with no other removal')
    if not vault and (args.remove_connections or args.remove_kit):
        refuse('--remove-connections and --remove-kit need --vault')
    if os.path.isdir(ct):  # the runtime folder is removed recursively: only accept one the installer made
        bad = os.path.realpath(ct) in (os.path.realpath(os.path.expanduser('~')), '/') or (vault and os.path.realpath(ct) == os.path.realpath(vault))
        try:
            ok = not bad and 'vault' in jload(os.path.join(ct, 'install.json'))
        except (OSError, ValueError):
            ok = False
        if not ok:
            refuse(f'{ct} is not a control tower runtime folder (no install.json from the installer)')
    why = kit_problem(ct, vault, args.launch_agents_dir) if args.remove_kit else None
    if why:
        refuse(why)

    sched = os.path.join(ct, 'schedule')
    agents = scheduling.own_agents(scheduling.agents_dir(args.launch_agents_dir), sched)  # another install's agents stay
    cron = scheduling.cron_applied(sched)
    plan = [('unload', f) for f in agents] + ([('crontab', 'remove the control-tower block')] if cron else [])
    loaded = (['launchd'] if agents else []) + (['cron'] if cron else [])
    remove, kept = added_connections(vault) if args.remove_connections else ([], [])
    plan += [('remove-connection', n) for n in remove] + [('keep-connection', f'{n}: changed since it was added') for n in kept]
    claude = claude_bin(ct)  # read before the runtime goes
    if os.path.isdir(ct) and not args.schedule_only:
        plan.append(('rmtree', ct))
    unedited = []
    if vault and args.remove_vault_files:
        if not os.path.isfile(os.path.join(vault, '.control-tower', 'manifest.json')):
            print('no manifest in the vault: nothing will be removed there', file=sys.stderr)
        else:
            unedited, edited = installed_files(vault)
            plan += [('remove-files', f'{len(unedited)} unmodified installed file(s)'), ('keep-files', f'{len(edited)} file(s) you edited are kept')]
    if args.remove_kit:
        plan.append(('remove-kit', install.REPO))

    for kind, what in plan:
        print(f'{"would " if not args.yes else ""}{kind}: {what}')
    try:  # they run on claude.ai: nothing here removes them, and a damaged index never blocks the uninstall
        routines = [str(r['name']) for r in jload(os.path.join(ct, 'routines', 'routines.json'), [])]
    except (ValueError, TypeError, KeyError):
        routines = []
    if routines:
        print('cloud routines are not removed from here: delete on claude.ai the ones you created: ' + ', '.join(routines))
    if not plan:
        print('nothing to do')
    if not args.yes:
        print('\nDry run. Add --yes to apply.')
        return
    report = {'warnings': []}
    for kind in loaded:
        scheduling.apply(kind, [], sched, args.launch_agents_dir, args.no_launchctl, report, unload=True)
    for name in remove:  # from the vault's folder: its .mcp.json is the project scope
        try:
            r = subprocess.run([claude, 'mcp', 'remove', '--scope', 'project', '--', name], cwd=vault, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=60)
            if r.returncode:
                report['warnings'].append(f'{name} was not removed: {r.stderr.strip()[:200]}')
        except (OSError, subprocess.TimeoutExpired) as exc:
            report['warnings'].append(f'{name} was not removed: {exc}')
    for w in report['warnings']:
        print(f'warning: {w}', file=sys.stderr)
    if ('rmtree', ct) in plan:
        shutil.rmtree(ct)
    if unedited:
        parents = set()
        for rel in unedited:
            os.remove(os.path.join(vault, rel))
            parents.add(os.path.dirname(os.path.join(vault, rel)))
        for d in sorted(parents, key=len, reverse=True):  # only folders that held installed files, deepest first
            while d != vault and os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                d = os.path.dirname(d)
        shutil.rmtree(os.path.join(vault, '.control-tower'), ignore_errors=True)
    if args.remove_kit:
        shutil.rmtree(install.REPO)
    print('\nDone.')


if __name__ == '__main__':
    main()
