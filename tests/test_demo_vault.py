#!/usr/bin/env python3
"""Tests of examples/build_demo_vault.py: the demo vault is built into a throwaway directory, then checked.

Run:  python3 -W ignore -m unittest tests/test_demo_vault.py -v   (from the repository root)
"""
import datetime
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
import doctor  # noqa: E402

SCRIPT = os.path.join(ROOT, 'examples', 'build_demo_vault.py')
DAY = datetime.date(2026, 1, 1)  # a Thursday in ISO week 2026-W01: the previous week is in 2025
SKIP_DIRS = ('.obsidian', '.control-tower')
TASK = re.compile(r'^\s*- \[( |x)\] (.*)$')


class DemoVaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.vault = os.path.join(cls.tmp.name, 'demo')
        r = subprocess.run([sys.executable, SCRIPT, '--out', cls.vault, '--date', DAY.isoformat()], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        cls.stdout = r.stdout
        cls.md = []
        for root, dirs, files in os.walk(cls.vault):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            cls.md += [os.path.relpath(os.path.join(root, f), cls.vault) for f in files if f.endswith('.md')]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def read(self, rel):
        with open(os.path.join(self.vault, rel), encoding='utf-8') as fh:
            return fh.read()

    def notes(self):
        return [f for f in self.md if not f.startswith('.claude/') and f != 'CLAUDE.md']

    def test_doctor_has_no_failure(self):
        result = doctor.check(self.vault, self.vault + '-runtime', 'python3')
        self.assertEqual([i for i in result.items if i['level'] == 'FAIL'], [])

    def test_wikilinks_resolve(self):
        names = set()
        for root, _, files in os.walk(self.vault):
            names |= {os.path.splitext(f)[0] for f in files}
        for f in self.md:
            if f.startswith('_system/templates/'):
                continue
            body = re.sub(r'```.*?```', '', self.read(f), flags=re.S)
            body = re.sub(r'`[^`\n]*`', '', body)
            for m in re.finditer(r'(?<!!)\[\[([^\]|#]+)', body):
                self.assertIn(m.group(1).strip(), names, f'{f}: [[{m.group(1)}]] has no target')

    def test_frontmatter_parses_and_free_text_is_quoted(self):
        for f in self.notes():
            fm = doctor.frontmatter(self.read(f))
            self.assertIsNotNone(fm, f'{f}: no frontmatter')
            for k, v in fm.items():
                if v and not v.startswith(('"', "'", '[', '{', '|', '>')) and re.search(r':\s|\s#', v):
                    self.fail(f'{f}: unquoted value with ": " or " #": {k}: {v}')

    def test_tasks_cover_overdue_today_and_triage(self):
        overdue = today = triage = 0
        for f in self.notes():
            if f.startswith('journal/daily/'):
                continue  # the cockpit queries ignore daily notes
            for line in self.read(f).split('\n'):
                m = TASK.match(line)
                if not m or m.group(1) == 'x':
                    continue
                due = re.search(r'📅 (\d{4}-\d{2}-\d{2})', line)
                if due:
                    d = datetime.date.fromisoformat(due.group(1))
                    overdue += d < DAY
                    today += d == DAY
                triage += '#to-triage' in line
        self.assertGreaterEqual(overdue, 1)
        self.assertGreaterEqual(today, 1)
        self.assertGreaterEqual(triage, 1)

    def test_no_leftover_token(self):
        for f in self.md:
            self.assertNotIn('{{ct.', self.read(f), f)

    def test_refuses_a_non_empty_folder_that_is_not_a_vault(self):
        other = os.path.join(self.tmp.name, 'other')
        os.makedirs(other)
        open(os.path.join(other, 'keep.txt'), 'w').close()
        for extra in ([], ['--force']):
            r = subprocess.run([sys.executable, SCRIPT, '--out', other] + extra, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertTrue(os.path.isfile(os.path.join(other, 'keep.txt')))


if __name__ == '__main__':
    unittest.main()
