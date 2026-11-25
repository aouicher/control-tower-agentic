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
