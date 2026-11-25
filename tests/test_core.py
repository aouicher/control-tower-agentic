#!/usr/bin/env python3
"""Structural tests for core/vault. Standard library only.

Run:  python3 -m unittest tests/test_core.py -v   (from the repository root)

The core is rendered into a throwaway directory (never into a real vault), then checked:
layout, frontmatter, tokens, links and embeds, dashboards, skills, language, safety.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, 'core', 'vault')
RENDER = os.path.join(ROOT, 'installer', 'render.py')

LAYOUT_DIRS = [
    '_inbox', 'cockpit', 'work/projects', 'work/areas', 'work/workstreams', 'work/decisions', 'work/risks',
    'team', 'journal/daily', 'journal/meetings', 'journal/reports', 'library',
    '_system/templates', '_system/dashboards', '_system/tools', '_system/archive', '_system/attachments',
    '.claude/skills',
]
TEMPLATES = ['daily', 'weekly', 'meeting', 'project', 'area', 'workstream', 'risk', 'decision', 'team', 'person', 'report', 'resource']
SKILLS = ['today', 'weekly-review', 'meeting', 'research', 'time-review', 'inbox']
DASHBOARDS = ['projects', 'workstreams', 'people', 'teams', 'decisions', 'risks', 'reports']
TYPE_VALUES = {'project', 'area', 'workstream', 'decision', 'risk', 'team', 'person', 'report', 'meeting', 'resource', 'hub', 'daily', 'weekly'}
FRENCH = re.compile(r'[àâäçéèêëîïôöùûüÿœ]', re.I)


def parse_frontmatter(text):
    m = re.match(r'---\n(.*?)\n---\n', text, re.S)
    if not m:
        return None
    props = {}
    for line in m.group(1).split('\n'):
        k = re.match(r'^([A-Za-z_][\w-]*):\s*(.*)$', line)
        if k:
            props[k.group(1)] = k.group(2).strip()
    return props


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.vault = os.path.join(cls.tmp.name, 'vault')
        answers = os.path.join(cls.tmp.name, 'answers.json')
        json.dump({'owner_name': 'Test User', 'owner_handle': 'me', 'timezone': 'UTC'}, open(answers, 'w'))
        r = subprocess.run([sys.executable, RENDER, '--src', CORE, '--dst', cls.vault,
                            '--vocab', os.path.join(ROOT, 'core', 'vocabulary.json'), '--answers', answers],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        cls.files = []
        for root, _, fs in os.walk(cls.vault):
            for f in fs:
                cls.files.append(os.path.relpath(os.path.join(root, f), cls.vault))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def read(self, rel):
        with open(os.path.join(self.vault, rel), encoding='utf-8') as fh:
            return fh.read()

    def md(self):
        return [f for f in self.files if f.endswith('.md')]

    def test_layout(self):
        for d in LAYOUT_DIRS:
            self.assertTrue(os.path.isdir(os.path.join(self.vault, d)), f'missing folder {d}')
        for f in ('CLAUDE.md', 'cockpit.md', 'cockpit/today.md', 'cockpit/my-work.md', 'cockpit/commitments.md', 'cockpit/overview.md'):
            self.assertIn(f, self.files)

    def test_no_leftover_tokens(self):
        for f in self.md() + [x for x in self.files if x.endswith('.base')]:
            self.assertNotRegex(self.read(f), r'\{\{ct\.', f'{f} still has a token')

    def test_obsidian_placeholders_survive(self):
        self.assertIn('{{title}}', self.read('_system/templates/project.md'))
        self.assertRegex(self.read('_system/templates/daily.md'), r'\{\{date:')

    def test_templates_exist_and_have_valid_frontmatter(self):
        for t in TEMPLATES:
            rel = f'_system/templates/{t}.md'
            self.assertIn(rel, self.files, rel)
            fm = parse_frontmatter(self.read(rel))
            self.assertIsNotNone(fm, f'{rel} has no frontmatter')
            self.assertIn('tags', fm, rel)

    def test_typed_templates_use_known_types(self):
        for t in TEMPLATES:
            fm = parse_frontmatter(self.read(f'_system/templates/{t}.md'))
            self.assertIn(fm.get('type'), TYPE_VALUES, f'{t}: type={fm.get("type")}')

    def test_free_text_values_are_quoted_or_safe(self):
        for f in self.md():
            fm = parse_frontmatter(self.read(f))
            if not fm:
                continue
            for k, v in fm.items():
                if v and not v.startswith(('"', "'", '[', '{', '|', '>')) and re.search(r':\s|\s#', v):
                    self.fail(f'{f}: unquoted value with ": " or " #": {k}: {v}')

    def test_task_tags_are_the_documented_ones(self):
        allowed = {'to-triage', 'waiting', 'committed', 'deadline'}
        for f in self.md():
            for line in self.read(f).split('\n'):
                if re.match(r'\s*- \[[ x-]\]', line):
                    for tag in re.findall(r'(?<![\w`])#([A-Za-z][\w-]*)', line):
                        self.assertIn(tag, allowed, f'{f}: unknown task tag #{tag}')

    def test_embeds_resolve(self):
        names = {os.path.splitext(os.path.basename(f))[0] for f in self.files} | {os.path.basename(f) for f in self.files}
        for f in self.md():
            for m in re.finditer(r'!\[\[([^\]|#]+)', self.read(f)):
                self.assertIn(m.group(1).strip(), names, f'{f}: embed [[{m.group(1)}]] has no target')

    def test_wikilinks_resolve_or_are_placeholders(self):
        names = {os.path.splitext(os.path.basename(f))[0] for f in self.files}
        for f in self.md():
            body = re.sub(r'```.*?```', '', self.read(f), flags=re.S)
            body = re.sub(r'`[^`\n]*`', '', body)  # inline code may show link syntax as an example
            for m in re.finditer(r'(?<!!)\[\[([^\]|#]+)', body):
                target = m.group(1).strip()
                if target and target != ' ':
                    self.assertIn(target, names, f'{f}: [[{target}]] has no target')

    def test_dashboards(self):
        for d in DASHBOARDS:
            rel = f'_system/dashboards/{d}.base'
            self.assertIn(rel, self.files, rel)
            text = self.read(rel)
            self.assertIn('filters:', text, rel)
            self.assertIn('views:', text, rel)
            for folder in re.findall(r'inFolder\("([^"]+)"\)', text):
                self.assertTrue(os.path.isdir(os.path.join(self.vault, folder)), f'{rel}: folder {folder} missing')

    def test_skills(self):
        for s in SKILLS:
            rel = f'.claude/skills/{s}/SKILL.md'
            self.assertIn(rel, self.files, rel)
            fm = parse_frontmatter(self.read(rel))
            self.assertEqual(fm.get('name'), s, f'{rel}: name must equal the folder')
            self.assertIn('description', fm, rel)

    def test_claude_md_is_short_and_has_safety_rules(self):
        text = self.read('CLAUDE.md')
        self.assertLessEqual(len(text.split('\n')), 110)
        for needle in ('_system/archive', 'to-triage', 'secrets'):
            self.assertIn(needle, text, f'CLAUDE.md should mention {needle}')

    def test_everything_is_english(self):
        for f in self.md() + [x for x in self.files if x.endswith('.base')]:
            hit = FRENCH.search(self.read(f))
            self.assertIsNone(hit, f'{f}: accented character {hit.group(0) if hit else ""} (English only)')

    def test_duplicate_tasks_tool_runs_on_an_empty_vault(self):
        r = subprocess.run([sys.executable, os.path.join(self.vault, '_system/tools/duplicate-tasks.py'), self.vault],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r'\b0 probable duplicate')


if __name__ == '__main__':
    unittest.main()
