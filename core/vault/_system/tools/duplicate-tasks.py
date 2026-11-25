#!/usr/bin/env python3
"""List open tasks that appear in several notes of the vault.

Usage: python3 duplicate-tasks.py [VAULT_PATH] [--md]

The vault path is the first CLI argument, else the CT_VAULT_PATH environment
variable, else the current directory. Read-only.

A task lives once. This script spots the copies. Two open tasks are considered
close when they share many words (Jaccard >= 0.5) or the same identifier
(issue key such as ABC-123, or a pull request number such as #1234).
Daily notes (journal/daily), templates and other system folders are ignored.
"""
import collections
import itertools
import os
import re
import sys

SKIP = re.compile(r'(^|/)(\.obsidian|\.claude|_system|journal/daily)(/|$)')
STOP = set(
    'the a an and or of to in on at for with without by from is are be been it this that '
    'as not no but if then than so up out into over per via me my we our you your'.split()
)
IDS = re.compile(r'\b[A-Z][A-Z0-9]+-\d+\b|#\d{3,6}\b')


def tokens(text):
    text = re.sub(r'\[\[[^\]]+\]\]|[@📅#]\S+|`', '', text)
    return {w for w in re.findall(r'[\w\-.]+', text.lower()) if w not in STOP and len(w) > 2}


def collect(root):
    tasks = []
    for r, dirs, files in os.walk(root):
        rel = os.path.relpath(r, root)
        if SKIP.search(rel + '/'):
            dirs[:] = []
            continue
        for x in files:
            if not x.endswith('.md') or x == 'CLAUDE.md':
                continue
            p = x if rel == '.' else os.path.join(rel, x)
            with open(os.path.join(r, x), encoding='utf-8') as fh:
                for i, line in enumerate(fh, 1):
                    m = re.match(r'\s*- \[ \]\s*(\S.*)', line)
                    if m:
                        txt = m.group(1).strip()
                        tasks.append((p, i, txt, tokens(txt), set(IDS.findall(txt))))
    return tasks


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    root = os.path.expanduser(args[0] if args else os.environ.get('CT_VAULT_PATH', '.'))
    tasks = collect(root)
    n = len(tasks)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, j in itertools.combinations(range(n), 2):
        a, b = tasks[i], tasks[j]
        if a[0] == b[0] or not a[3] or not b[3]:
            continue
        jac = len(a[3] & b[3]) / len(a[3] | b[3])
        if jac >= 0.5 or (a[4] & b[4]):
            parent[find(i)] = find(j)

    groups = collections.defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    dups = [g for g in groups.values() if len(g) > 1]

    md = '--md' in sys.argv
    print(f"{n} open tasks analysed, {len(dups)} probable duplicate group(s)")
    for g in dups:
        if md:
            print(f"\n| {tasks[g[0]][2][:90]} |\n|---|")
            for i in g:
                print(f"| `{tasks[i][0]}` line {tasks[i][1]} |")
        else:
            print('\n*', tasks[g[0]][2][:100])
            for i in g:
                print(f"    {tasks[i][0]}:{tasks[i][1]}")


if __name__ == '__main__':
    main()
