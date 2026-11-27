#!/usr/bin/env python3
"""Documentation tests: relative links resolve, docs are English, example answers files install cleanly."""
import glob
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
import install  # noqa: E402

DOCS = [os.path.join(ROOT, f) for f in ('README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CHANGELOG.md')] + \
    sorted(glob.glob(os.path.join(ROOT, 'docs', '**', '*.md'), recursive=True)) + [os.path.join(ROOT, 'examples', 'README.md')]


class DocTests(unittest.TestCase):
    def test_relative_links_resolve(self):
        for doc in DOCS:
            text = open(doc, encoding='utf-8').read()
            for target in re.findall(r'\]\(([^)\s]+)\)', text):
                if target.startswith(('http', '#', 'mailto:')):
                    continue
                path = os.path.normpath(os.path.join(os.path.dirname(doc), target.split('#')[0]))
                with self.subTest(doc=os.path.relpath(doc, ROOT), link=target):
                    self.assertTrue(os.path.exists(path), f'broken link {target}')

    def test_nothing_tells_the_user_to_edit_the_answers(self):
        # every change goes through /control-tower or /job-permissions (installer/configure.py): never a hand edit
        import glob
        import re
        bad = re.compile(r'edit (your|the) answers|answers file under|add .* to your answers|edit [^.\n]*answers\.json'
                         r'|(list|add|set|put) [^.\n]* in (your|the) answers', re.I)
        files = (glob.glob(os.path.join(ROOT, 'docs', '**', '*.md'), recursive=True) + glob.glob(os.path.join(ROOT, 'installer', '*.py'))
                 + glob.glob(os.path.join(ROOT, 'core', '**', '*.md*'), recursive=True)
                 + glob.glob(os.path.join(ROOT, 'packs', '**', '*.md*'), recursive=True)
                 + glob.glob(os.path.join(ROOT, '.claude', 'skills', '**', '*.md'), recursive=True) + [os.path.join(ROOT, 'README.md')])
        for path in files:
            for n, line in enumerate(open(path, encoding='utf-8'), 1):
                with self.subTest(file=os.path.relpath(path, ROOT), line=n):
                    self.assertIsNone(bad.search(line))

    def test_the_control_tower_hub_skill(self):
        import re
        text = open(os.path.join(ROOT, 'core', 'vault', '.claude', 'skills', 'control-tower', 'SKILL.md'), encoding='utf-8').read()
        m = re.match(r'---\n(.*?)\n---\n', text, re.S)
        self.assertIsNotNone(m)
        self.assertIn('name: control-tower', m.group(1))
        self.assertIn('description:', m.group(1))
        self.assertNotIn('allowed-tools', text)
        for needle in ('doctor.py', 'configure.py show', 'configure.py set', '--dry-run', '--accept-access', '/job-permissions',
                       'configure.py fresh-copy', 'never edit'):
            self.assertIn(needle.lower(), text.lower(), f'the hub must mention: {needle}')
        for route in ('automate', 'update', 'uninstall'):  # only what works today is offered
            self.assertNotRegex(text.lower(), rf'say:? ["\'*]*{route}\b')

    def test_every_question_from_a_list_is_asked_in_pages(self):
        # the question tool shows at most 4 options: a longer list goes through configure.py choices, never by hand
        import glob
        import re
        skills = (glob.glob(os.path.join(ROOT, 'core', 'vault', '.claude', 'skills', '*', 'SKILL.md'))
                  + glob.glob(os.path.join(ROOT, 'packs', '*', 'vault', '.claude', 'skills', '*', 'SKILL.md*'))
                  + glob.glob(os.path.join(ROOT, '.claude', 'skills', '*', 'SKILL.md')))
        for path in skills:
            for n, line in enumerate(open(path, encoding='utf-8'), 1):
                with self.subTest(skill=os.path.relpath(path, ROOT), line=n):
                    m = re.search(r'options? ((?:"[^"]+"(?:,| and| or| /)? ?)+)', line)
                    if m:
                        self.assertLessEqual(len(re.findall(r'"[^"]+"', m.group(1))), 4, 'at most 4 options per question')
                    if re.search(r'multi-select|let me choose', line, re.I):
                        self.assertIn('configure.py choices', line, 'a list is asked through configure.py choices')

    def test_docs_are_english(self):
        for doc in DOCS:
            text = open(doc, encoding='utf-8').read()
            with self.subTest(doc=os.path.relpath(doc, ROOT)):
                self.assertIsNone(re.search(r'[àâçéèêëîïôùûüœ]', text, re.I), 'accented letters found')

    def test_example_answers_install(self):
        for path in sorted(glob.glob(os.path.join(ROOT, 'examples', 'answers', '*.json'))):
            with self.subTest(answers=os.path.basename(path)), tempfile.TemporaryDirectory() as tmp:
                a = json.load(open(path, encoding='utf-8'))
                a['vault_path'] = os.path.join(tmp, 'vault')
                a['ct_home'] = os.path.join(tmp, 'ct')
                report = install.install(a, dry_run=True, log=lambda *x: None)
                self.assertGreater(report['created'], 40)

    def test_acme_notes_have_frontmatter(self):
        for path in glob.glob(os.path.join(ROOT, 'examples', 'acme-notes', '**', '*.md'), recursive=True):
            with self.subTest(note=os.path.relpath(path, ROOT)):
                self.assertTrue(open(path, encoding='utf-8').read().startswith('---\n'))


if __name__ == '__main__':
    unittest.main()
