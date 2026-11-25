#!/usr/bin/env python3
"""Leak and language scanner for the repository.

Checks every tracked or staged text file for:
  1. secrets and identifiers (generic patterns defined below),
  2. terms listed in `.denylist.local` (never committed: it holds private names),
  3. non-English text in documentation and skills (accented letters).

Usage:
    python3 tools/scan-leaks.py            # scan the working tree (git tracked + untracked, not ignored)
    python3 tools/scan-leaks.py --staged   # scan staged files only
    python3 tools/scan-leaks.py --strict   # also fail on language warnings
    python3 tools/scan-leaks.py --strict --no-denylist   # CI: no private denylist there, by design

Exit code 1 when something is found. Read-only: it never edits files.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT_EXT = {'.md', '.txt', '.yml', '.yaml', '.json', '.sh', '.py', '.base', '.canvas', '.plist', '.toml', '.cfg', '.tmpl', ''}
SELF = os.path.join('tools', 'scan-leaks.py')

# 1. Generic patterns. Each is (name, regex). Keep them narrow to avoid noise.
PATTERNS = [
    ('AWS access key id', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('AWS ARN with account id', re.compile(r'arn:aws[a-z-]*:[a-z0-9-]*:[a-z0-9-]*:\d{12}:')),
    ('12-digit number (possible AWS account id)', re.compile(r'(?<![\d.])\d{12}(?![\d.])')),
    ('private key block', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('GitHub token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b')),
    ('Slack token', re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{10,}\b')),
    ('generic API key assignment', re.compile(r'(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*["\'][A-Za-z0-9_\-]{16,}["\']')),
    ('email address', re.compile(r'\b[A-Za-z0-9._%+-]+@(?!example\.(com|org)\b|users\.noreply\.github\.com\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')),
    ('home directory of a real user', re.compile(r'/Users/(?!you\b|user\b|name\b|alice\b|bob\b)[a-z][a-z0-9_.-]+/')),
]
# Files where a 12-digit example or a documented fake value is expected.
ALLOW_LINE = re.compile(r'(?i)(example|placeholder|fake|dummy|000000000000|123456789012)')

# 3. Language check: accented Latin letters suggest French text.
ACCENT = re.compile(r'[àâäçéèêëîïôöùûüÿœÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒ]')
LANG_PATHS = ('docs/', 'core/', 'packs/', 'adapters/', 'installer/', 'scheduler/', 'examples/', 'README.md', 'CONTRIBUTING.md')


def list_files(staged):
    cmd = ['git', '-C', ROOT, 'diff', '--cached', '--name-only', '--diff-filter=ACM'] if staged else \
          ['git', '-C', ROOT, 'ls-files', '--cached', '--others', '--exclude-standard']
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.split('\n')
    return [f for f in out if f and f != SELF]


def load_denylist():
    path = os.path.join(ROOT, '.denylist.local')
    if not os.path.exists(path):
        return []
    terms = []
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#'):
            terms.append(re.compile(re.escape(line), re.I))
    return terms


def main():
    staged = '--staged' in sys.argv
    strict = '--strict' in sys.argv
    deny = load_denylist()
    findings, warnings = [], []
    if not deny and '--no-denylist' not in sys.argv:  # CI has no private denylist by design: say so explicitly with --no-denylist
        warnings.append(('(setup)', 0, 'no .denylist.local found: private names are NOT checked'))
    for rel in list_files(staged):
        ext = os.path.splitext(rel)[1].lower()
        if ext not in TEXT_EXT:
            continue
        path = os.path.join(ROOT, rel)
        try:
            lines = open(path, encoding='utf-8').read().split('\n')
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for n, line in enumerate(lines, 1):
            if ALLOW_LINE.search(line):
                continue
            for name, rx in PATTERNS:
                if rx.search(line):
                    findings.append((rel, n, name + ': ' + line.strip()[:90]))
            for rx in deny:
                if rx.search(line):
                    findings.append((rel, n, 'private term "' + rx.pattern.replace('\\', '') + '": ' + line.strip()[:90]))
            if rel.startswith(LANG_PATHS) and ACCENT.search(line):
                warnings.append((rel, n, 'accented text (is it English?): ' + line.strip()[:90]))
    for rel, n, msg in findings:
        print(f'LEAK  {rel}:{n}  {msg}')
    for rel, n, msg in warnings:
        print(f'WARN  {rel}:{n}  {msg}')
    print(f'\n{len(findings)} leak(s), {len(warnings)} warning(s)')
    sys.exit(1 if findings or (strict and warnings) else 0)


if __name__ == '__main__':
    main()
