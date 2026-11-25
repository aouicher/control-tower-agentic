#!/usr/bin/env python3
"""Tests for packs and adapters. Standard library only.

Run:  python3 -W ignore -m unittest tests/test_packs.py -v   (from the repository root)

Every pack is rendered on top of the core inside a throwaway directory and checked against
docs/design/pack-spec.md. Adapters are checked for their manifest and required sections.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDER = os.path.join(ROOT, 'installer', 'render.py')
PACKS_DIR = os.path.join(ROOT, 'packs')
ADAPTERS_DIR = os.path.join(ROOT, 'adapters')

CAPABILITIES = {'calendar', 'tracker', 'code', 'errors', 'quality', 'logs', 'analytics', 'crm'}
ACCESS = {'mcp', 'cli', 'api'}
STATUS = {'documented', 'verified'}
CONTRACT_SECTIONS = ['Purpose', 'Inputs', 'Outputs', 'Pagination', 'Read-only', 'Failure']
ADAPTER_SECTIONS = ['Setup', 'Authentication', 'Field mapping', 'Pitfalls', 'Verification']
FRENCH = re.compile(r'[àâäçéèêëîïôöùûüÿœ]', re.I)
ANSWERS = {'owner_name': 'Test User', 'owner_handle': 'me', 'timezone': 'UTC'}


def pack_ids():
    if not os.path.isdir(PACKS_DIR):
        return []
    return sorted(d for d in os.listdir(PACKS_DIR) if os.path.isfile(os.path.join(PACKS_DIR, d, 'pack.json')))


def adapter_tools():
    out = {}
    if not os.path.isdir(ADAPTERS_DIR):
        return out
    for cap in sorted(os.listdir(ADAPTERS_DIR)):
        d = os.path.join(ADAPTERS_DIR, cap)
        if os.path.isdir(d):
            out[cap] = sorted(f[:-5] for f in os.listdir(d) if f.endswith('.json'))
    return out


def headings(text):
    return ' '.join(re.findall(r'^#{1,4}\s*(.+)$', text, re.M))


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


def render(src, dst, vocab_files, extra=None):
    ans = os.path.join(os.path.dirname(dst), 'answers.json')
    json.dump(ANSWERS, open(ans, 'w'))
    cmd = [sys.executable, RENDER, '--src', src, '--dst', dst, '--answers', ans]
    for v in vocab_files:
        cmd += ['--vocab', v]
    return subprocess.run(cmd + (extra or []), capture_output=True, text=True)


class PackTests(unittest.TestCase):
    def test_at_least_one_pack(self):
        self.assertTrue(pack_ids(), 'no pack found')

    def test_each_pack(self):
        tools = adapter_tools()
        for pid in pack_ids():
            with self.subTest(pack=pid):
                self.check_pack(pid, tools)

    def check_pack(self, pid, tools):
        base = os.path.join(PACKS_DIR, pid)
        manifest = json.load(open(os.path.join(base, 'pack.json'), encoding='utf-8'))
        self.assertEqual(manifest.get('id'), pid)
        for key in ('name', 'audience', 'summary', 'vocabulary', 'capabilities', 'questions'):
            self.assertIn(key, manifest, f'{pid}: pack.json lacks "{key}"')
        self.assertTrue(os.path.isfile(os.path.join(base, 'README.md')), f'{pid}: README.md missing')
        self.assertTrue(os.path.isfile(os.path.join(base, manifest['vocabulary'])), f'{pid}: vocabulary file missing')
        vocab = json.load(open(os.path.join(base, manifest['vocabulary']), encoding='utf-8'))
        for term in ('team', 'workstream', 'risk', 'person'):
            self.assertIn(term, vocab, f'{pid}: vocabulary must define {term}')
            self.assertEqual(set(vocab[term]), {'singular', 'plural'})

        # every referenced file exists
        vault = os.path.join(base, 'vault')
        for s in manifest.get('skills', []):
            self.assertTrue(os.path.isfile(os.path.join(vault, '.claude/skills', s, 'SKILL.md.tmpl')) or
                            os.path.isfile(os.path.join(vault, '.claude/skills', s, 'SKILL.md')), f'{pid}: skill {s} missing')
        for t in manifest.get('templates', []):
            self.assertTrue(os.path.isfile(os.path.join(vault, '_system/templates', t + '.md')), f'{pid}: template {t} missing')
        for d in manifest.get('dashboards', []):
            self.assertTrue(os.path.isfile(os.path.join(vault, '_system/dashboards', d + '.base')), f'{pid}: dashboard {d} missing')
        for c in manifest.get('cockpit_pages', []):
            self.assertTrue(any(os.path.isfile(os.path.join(vault, 'cockpit', c + ext)) for ext in ('.md', '.md.tmpl')), f'{pid}: cockpit page {c} missing')
        for r in manifest.get('routines', []):
            self.assertTrue(os.path.isfile(os.path.join(base, 'routines', r + '.md')), f'{pid}: routine {r} missing')
        for j in manifest.get('jobs', []):
            jd = os.path.join(base, 'jobs', j)
            self.assertTrue(os.path.isfile(os.path.join(jd, 'job.json')), f'{pid}: job {j} lacks job.json')
            self.assertTrue(os.path.isfile(os.path.join(jd, 'prompt.md.tmpl')), f'{pid}: job {j} lacks prompt.md.tmpl')
            job = json.load(open(os.path.join(jd, 'job.json'), encoding='utf-8'))
            self.assertEqual(job.get('id'), j)
            for key in ('name', 'description', 'schedule', 'model', 'capabilities', 'outputs', 'permissions'):
                self.assertIn(key, job, f'{pid}/{j}: job.json lacks {key}')
            self.assertRegex(job['schedule'].get('time', ''), r'^\d{2}:\d{2}$', f'{pid}/{j}: schedule.time')
            for perm in job['permissions'].get('allow', []):
                self.assertNotIn(perm, ('Write', 'Edit', 'Bash', 'WebFetch'), f'{pid}/{j}: unscoped permission "{perm}" (scope it to the vault, for example Edit({{{{ct.vault_path}}}}/**))')
                self.assertNotIn('*', perm.replace('/**)', ')'), f'{pid}/{j}: wildcard permission "{perm}"')
            caps = job['capabilities']
            self.assertIsInstance(caps, dict, f'{pid}/{j}: capabilities must be {{"required": [...], "optional": [...]}}')
            for c in caps.get('required', []) + caps.get('optional', []):
                self.assertIn(c, CAPABILITIES, f'{pid}/{j}: unknown capability {c}')
            self.assertTrue(caps.get('required') or caps.get('optional') or job.get('vault_only'), f'{pid}/{j}: no capability and not vault_only')

        # capabilities and questions
        caps = manifest['capabilities']
        for c in caps.get('required', []) + caps.get('optional', []):
            self.assertIn(c, CAPABILITIES, f'{pid}: unknown capability {c}')
        for q in manifest['questions']:
            for key in ('id', 'ask', 'capability', 'choices'):
                self.assertIn(key, q, f'{pid}: question lacks {key}')
            self.assertIn(q['capability'], CAPABILITIES)
            for ch in q['choices']:
                if ch != 'none':
                    self.assertIn(ch, tools.get(q['capability'], []), f'{pid}: choice "{ch}" has no adapter under adapters/{q["capability"]}/')

        # render on top of the core without collisions or leftover tokens
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, 'vault')
            core = os.path.join(ROOT, 'core')
            r = render(os.path.join(core, 'vault'), dst, [os.path.join(core, 'vocabulary.json'), os.path.join(base, manifest['vocabulary'])])
            self.assertEqual(r.returncode, 0, r.stderr)
            if os.path.isdir(vault):
                r = render(vault, dst, [os.path.join(core, 'vocabulary.json'), os.path.join(base, manifest['vocabulary'])], ['--fail-on-collision'])
                self.assertEqual(r.returncode, 0, f'{pid}: overlay failed: {r.stderr}')
            for root, _, files in os.walk(dst):
                for f in files:
                    p = os.path.join(root, f)
                    if f.endswith(('.md', '.base')):
                        text = open(p, encoding='utf-8').read()
                        self.assertNotRegex(text, r'\{\{ct\.', f'{pid}: leftover token in {os.path.relpath(p, dst)}')
                        self.assertIsNone(FRENCH.search(text), f'{pid}: accented text in {os.path.relpath(p, dst)}')
                        if '/.claude/skills/' in p and f == 'SKILL.md':
                            fm = parse_frontmatter(text)
                            self.assertIsNotNone(fm, p)
                            self.assertEqual(fm.get('name'), os.path.basename(os.path.dirname(p)), f'{pid}: skill name != folder')
                            self.assertIn('description', fm)
            # dashboards of the pack only use folders that exist in the rendered vault
            for d in manifest.get('dashboards', []):
                text = open(os.path.join(dst, '_system/dashboards', d + '.base'), encoding='utf-8').read()
                for folder in re.findall(r'inFolder\("([^"]+)"\)', text):
                    self.assertTrue(os.path.isdir(os.path.join(dst, folder)), f'{pid}/{d}: folder {folder} missing')

        # jobs render too (prompts are plain text with tokens)
        with tempfile.TemporaryDirectory() as tmp:
            for j in manifest.get('jobs', []):
                jd = os.path.join(base, 'jobs', j)
                out = os.path.join(tmp, j)
                core = os.path.join(ROOT, 'core')
                r = render(jd, out, [os.path.join(core, 'vocabulary.json'), os.path.join(base, manifest['vocabulary'])])
                self.assertEqual(r.returncode, 0, f'{pid}/{j}: {r.stderr}')
                text = open(os.path.join(out, 'prompt.md'), encoding='utf-8').read()
                self.assertIn('never ask', text.lower(), f'{pid}/{j}: unattended prompt must say it never asks questions')
                self.assertIn('#to-triage', text, f'{pid}/{j}: prompt must tag proposed tasks #to-triage')
                self.assertIsNone(FRENCH.search(text))


class VocabularyTests(unittest.TestCase):
    def test_no_hardcoded_article_before_a_token(self):
        out = subprocess.run(['git', 'ls-files', 'core', 'packs'], cwd=ROOT, capture_output=True, text=True).stdout.split()
        for rel in out:
            if rel.endswith(('.md', '.tmpl')):
                text = open(os.path.join(ROOT, rel), encoding='utf-8').read()
                with self.subTest(file=rel):
                    self.assertIsNone(re.search(r'\b[aA]n? \{\{ct\.[a-z]+\}\}', text), 'use {{ct.a_<word>}}: the article depends on the word')

    def test_article_forms(self):
        sys.path.insert(0, os.path.join(ROOT, 'installer'))
        import render
        table = render.build_table([os.path.join(ROOT, 'core', 'vocabulary.json'), os.path.join(PACKS_DIR, 'product', 'vocabulary.json')], {})
        self.assertEqual(table['a_workstream'], 'an initiative')
        self.assertEqual(table['A_team'], 'A team')


class RoutineTests(unittest.TestCase):
    def test_routines_are_well_formed(self):
        sys.path.insert(0, os.path.join(ROOT, 'installer'))
        import install
        caps = set(install.CAPABILITIES)
        for pid in sorted(os.listdir(PACKS_DIR)):
            mp = os.path.join(PACKS_DIR, pid, 'pack.json')
            if not os.path.isfile(mp):
                continue
            for rid in json.load(open(mp, encoding='utf-8')).get('routines', []):
                with self.subTest(pack=pid, routine=rid):
                    meta, prompt = install.read_routine(os.path.join(PACKS_DIR, pid, 'routines', rid + '.md'))
                    self.assertEqual(meta['id'], rid)
                    self.assertTrue(meta.get('name'))
                    self.assertTrue(install.parse_days(meta['days']))
                    self.assertRegex(meta['time'], r'^([01]\d|2[0-3]):[0-5]\d$')
                    self.assertIn(meta['vault'], ('write', 'optional'))
                    for key in ('connectors_required', 'connectors_optional'):
                        self.assertIsInstance(meta[key], list)
                        self.assertTrue(set(meta[key]) <= caps, f'{key}: unknown capability')
                    self.assertGreater(len(prompt), 200)
                    self.assertIn('never ask', prompt.lower())
                    self.assertNotIn('```', prompt, 'the prompt is pasted as is: no code fence')
                    self.assertNotIn('{{ct.vault_path}}', prompt, 'a cloud routine cannot see a local path')


class AdapterTests(unittest.TestCase):
    def test_every_capability_has_a_contract_and_a_tool(self):
        tools = adapter_tools()
        self.assertTrue(tools, 'no adapters found')
        for cap, names in tools.items():
            with self.subTest(capability=cap):
                self.assertIn(cap, CAPABILITIES)
                contract = os.path.join(ADAPTERS_DIR, cap, 'contract.md')
                self.assertTrue(os.path.isfile(contract), f'{cap}: contract.md missing')
                text = open(contract, encoding='utf-8').read()
                h = headings(text).lower()
                for sec in CONTRACT_SECTIONS:
                    self.assertIn(sec.lower(), h, f'{cap}/contract.md lacks a "{sec}" section')
                self.assertTrue(names, f'{cap}: no tool adapter')

    def test_manifests_and_docs(self):
        for cap, names in adapter_tools().items():
            for tool in names:
                with self.subTest(adapter=f'{cap}/{tool}'):
                    jp = os.path.join(ADAPTERS_DIR, cap, tool + '.json')
                    man = json.load(open(jp, encoding='utf-8'))
                    self.assertEqual(man.get('tool'), tool)
                    self.assertEqual(man.get('capability'), cap)
                    self.assertIn(man.get('access'), ACCESS)
                    self.assertIn(man.get('status'), STATUS)
                    self.assertTrue(str(man.get('setup_url', '')).startswith('https://'), 'setup_url must be an https URL')
                    self.assertIsInstance(man.get('read_only'), bool, 'read_only must be a boolean')
                    if man.get('read_only') is False:
                        self.assertTrue(man.get('read_only_mitigation'), f'{tool}: a tool without a read-only mode needs a read_only_mitigation (view-only account, read-only token...)')
                    self.assertIsInstance(man.get('permissions_allow'), list)
                    self.assertIsInstance(man.get('permissions_deny', []), list)
                    self.assertTrue(man.get('verify'), 'a verify step is required')
                    md = os.path.join(ADAPTERS_DIR, cap, tool + '.md')
                    self.assertTrue(os.path.isfile(md), f'{tool}.md missing')
                    text = open(md, encoding='utf-8').read()
                    h = headings(text).lower()
                    for sec in ADAPTER_SECTIONS:
                        self.assertIn(sec.lower(), h, f'{tool}.md lacks a "{sec}" section')
                    self.assertIn(man['setup_url'].split('/')[2], text, f'{tool}.md should cite its official documentation')
                    self.assertIsNone(FRENCH.search(text))
                    if man.get('status') == 'verified':
                        self.fail('status "verified" requires a real test: not allowed in the repository tests')

    def test_no_wildcard_permissions(self):
        """MCP tools must be listed one by one. A Bash rule may end with ":*" only after a command and a subcommand."""
        bash_ok = re.compile(r'^Bash\([a-z0-9._-]+( [a-z0-9._-]+)+(:\*)?\)$')
        for cap, names in adapter_tools().items():
            for tool in names:
                man = json.load(open(os.path.join(ADAPTERS_DIR, cap, tool + '.json'), encoding='utf-8'))
                for perm in man['permissions_allow']:
                    if perm.startswith('mcp__'):
                        self.assertNotIn('*', perm, f'{cap}/{tool}: wildcard "{perm}" may allow write tools: list read-only tools explicitly')
                    elif perm.startswith('Bash('):
                        self.assertRegex(perm, bash_ok, f'{cap}/{tool}: Bash rule "{perm}" must name a command and a subcommand')
                    else:
                        self.assertNotIn('*', perm, f'{cap}/{tool}: wildcard "{perm}" is not allowed')

    def test_no_write_permissions_are_allowed(self):
        risky = re.compile(r'(?i)(create|update|delete|write|post|send|put)')
        for cap, names in adapter_tools().items():
            for tool in names:
                man = json.load(open(os.path.join(ADAPTERS_DIR, cap, tool + '.json'), encoding='utf-8'))
                for perm in man['permissions_allow']:
                    self.assertFalse(risky.search(perm), f'{cap}/{tool}: permission "{perm}" looks like a write permission')


if __name__ == '__main__':
    unittest.main()
