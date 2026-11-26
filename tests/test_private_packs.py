#!/usr/bin/env python3
"""Private packs (answers["pack_dirs"]) and runtime-only installs (answers["vault_mode"] = "runtime")."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
import doctor  # noqa: E402
import install  # noqa: E402
import plan  # noqa: E402

UNINSTALL = os.path.join(ROOT, 'installer', 'uninstall.py')


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


def private_pack(base, pid='acme-private', **extra):
    """A company pack kept outside the repository: French rules and daily template, one job, a core dashboard and skill dropped."""
    d = os.path.join(base, pid)
    manifest = {'id': pid, 'name': 'Acme private', 'audience': 'Acme', 'summary': 'Private pack', 'vocabulary': 'vocabulary.json',
                'jobs': ['acme-brief'], 'routines': [], 'questions': [], 'capabilities': {'required': [], 'optional': []},
                'replaces': ['CLAUDE.md', '_system/templates/daily.md'],
                'excludes': ['_system/dashboards/people.base', '.claude/skills/time-review']}
    manifest.update(extra)
    write(os.path.join(d, 'pack.json'), json.dumps(manifest))
    write(os.path.join(d, 'vocabulary.json'), json.dumps({'workstream': {'singular': 'sujet', 'plural': 'sujets'}}))
    write(os.path.join(d, 'vault', 'CLAUDE.md.tmpl'), '# Règles du vault de {{ct.owner_name}}\n\nUn {{ct.workstream}} par squad.\n')
    write(os.path.join(d, 'vault', '_system', 'templates', 'daily.md'), '---\ntitle: "{{date:YYYY-MM-DD}}"\ntype: daily\n---\n\n## 📅 Réunions\n')
    write(os.path.join(d, 'jobs', 'acme-brief', 'job.json'), json.dumps({
        'id': 'acme-brief', 'name': 'Acme brief', 'description': 'Private job', 'schedule': {'days': 'mon-fri', 'time': '08:15'},
        'model': 'sonnet', 'capabilities': {'required': [], 'optional': []}, 'vault_only': True,
        'outputs': ['journal/reports/acme-YYYY-MM-DD.md'], 'permissions': {'allow': [], 'deny': []}}))
    write(os.path.join(d, 'jobs', 'acme-brief', 'prompt.md.tmpl'), 'Unattended job for {{ct.owner_name}}. Never ask, never wait.\n')
    return d


def answers(tmp, packs, pack_dirs=(), **extra):
    a = {'owner_name': 'Sam Rivera', 'owner_handle': 'sam', 'timezone': 'UTC', 'vault_path': os.path.join(tmp, 'vault'),
         'ct_home': os.path.join(tmp, 'ct'), 'packs': packs, 'tools': {}, 'scheduler': 'none', 'pack_dirs': list(pack_dirs)}
    a.update(extra)
    return a


class PrivatePackTests(unittest.TestCase):
    def test_private_pack_replaces_and_excludes_core_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            pd = private_pack(os.path.join(tmp, 'packs-outside'))
            a = answers(tmp, ['acme-private'], [pd])
            report = install.install(a, log=lambda *x: None)
            v = a['vault_path']
            rules = open(os.path.join(v, 'CLAUDE.md'), encoding='utf-8').read()
            self.assertIn('Règles du vault de Sam Rivera', rules, 'the private CLAUDE.md replaces the core one')
            self.assertIn('Un sujet par squad', rules, 'the private vocabulary is applied')
            self.assertIn('Réunions', open(os.path.join(v, '_system', 'templates', 'daily.md'), encoding='utf-8').read())
            self.assertFalse(os.path.exists(os.path.join(v, '_system', 'dashboards', 'people.base')), 'excluded core file')
            self.assertFalse(os.path.exists(os.path.join(v, '.claude', 'skills', 'time-review')), 'excluded core skill')
            self.assertTrue(os.path.isfile(os.path.join(v, '.claude', 'skills', 'today', 'SKILL.md')), 'the rest of the core stays')
            self.assertEqual([j['id'] for j in report['jobs']], ['acme-brief'])
            prompt = open(os.path.join(a['ct_home'], 'jobs', 'acme-brief', 'prompt.md'), encoding='utf-8').read()
            self.assertIn('Sam Rivera', prompt)
            fails = [i for i in doctor.check(v, a['ct_home'], 'python3').items if i['level'] == 'FAIL']
            self.assertEqual(fails, [], 'excluded core files are not reported missing')

    def test_private_pack_works_alongside_a_public_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            pd = private_pack(os.path.join(tmp, 'p'))
            a = answers(tmp, ['engineering', 'acme-private'], [pd])
            report = install.install(a, dry_run=True, log=lambda *x: None)
            self.assertIn('acme-brief', [j['id'] for j in report['jobs']])

    def test_update_keeps_core_files_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            pd = private_pack(os.path.join(tmp, 'p'))
            a = answers(tmp, ['acme-private'], [pd])
            install.install(a, log=lambda *x: None)
            report = install.install(a, update=True, log=lambda *x: None)
            self.assertNotIn('CLAUDE.md', report['stashed'] + report['updated'])
            self.assertIn('Règles du vault', open(os.path.join(a['vault_path'], 'CLAUDE.md'), encoding='utf-8').read())
            self.assertFalse(os.path.exists(os.path.join(a['vault_path'], '_system', 'dashboards', 'people.base')))

    def test_bad_private_pack_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, 'empty')
            os.makedirs(empty)
            with self.assertRaises(install.InstallError) as ctx:
                install.install(answers(tmp, ['developer'], [empty]), dry_run=True)
            self.assertIn('no pack.json', str(ctx.exception))
            clash = private_pack(os.path.join(tmp, 'p'), pid='developer')
            with self.assertRaises(install.InstallError) as ctx:
                install.install(answers(tmp, ['developer'], [clash]), dry_run=True)
            self.assertIn('same id', str(ctx.exception))

    def test_public_packs_cannot_replace_core_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = os.path.join(tmp, 'kit')
            shutil.copytree(ROOT, kit, ignore=shutil.ignore_patterns('.git', 'tests', '__pycache__', '*.local'))
            mp = os.path.join(kit, 'packs', 'developer', 'pack.json')
            m = json.load(open(mp))
            m['replaces'] = ['CLAUDE.md']
            json.dump(m, open(mp, 'w'))
            with self.assertRaises(install.InstallError) as ctx:
                install.install(answers(tmp, ['developer']), repo=kit, dry_run=True)
            self.assertIn('only private packs', str(ctx.exception))
        for pid in install.list_packs():
            m = json.load(open(os.path.join(ROOT, 'packs', pid, 'pack.json')))
            self.assertFalse(m.get('replaces') or m.get('excludes'), f'public pack {pid} must not replace or exclude core files')


class ReviewRegressionTests(unittest.TestCase):
    """One test per finding of the PR #5 review."""

    def test_m2_private_job_permissions_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in (['Bash'], ['Write'], ['WebFetch'], ['Edit(//etc/**)'], ['mcp__*'], ['mcp__server'], ['Bash(python -c x)'],
                        ['Bash(cp x ~/.zshrc)'], ['Bash(*)'], ['Bash(git push:*)'], ['Bash(ls; rm -rf x)']):
                with self.subTest(allow=bad):
                    pd = private_pack(os.path.join(tmp, 'p' + str(abs(hash(str(bad))))))
                    jp = os.path.join(pd, 'jobs', 'acme-brief', 'job.json')
                    job = json.load(open(jp))
                    job['permissions']['allow'] = bad
                    json.dump(job, open(jp, 'w'))
                    with self.assertRaises(install.InstallError):
                        install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)
            pd = private_pack(os.path.join(tmp, 'ok'))
            jp = os.path.join(pd, 'jobs', 'acme-brief', 'job.json')
            job = json.load(open(jp))
            job['permissions']['allow'] = ['mcp__acme__get_issues', 'Bash(gh pr list:*)', 'Bash(TWG=1 twg query *)', 'WebFetch(domain:acme.test)']
            json.dump(job, open(jp, 'w'))
            install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)
            with self.assertRaises(install.InstallError):
                install.install(answers(tmp, ['acme-private'], [pd], permissions={'tracker': ['Bash']}), dry_run=True)

    def test_m1_runtime_mode_is_remembered(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = os.path.join(tmp, 'vault')
            write(os.path.join(v, 'CLAUDE.md'), 'Mine.\n')
            pd = private_pack(os.path.join(tmp, 'p'))
            install.install(answers(tmp, ['acme-private'], [pd], vault_mode='runtime'), log=lambda *x: None)
            plain = answers(tmp, ['acme-private'], [pd])  # no vault_mode: the user's own answers file
            for kw in ({}, {'update': True}):
                with self.subTest(**kw):
                    report = install.install(plain, log=lambda *x: None, **kw)
                    self.assertEqual(report['vault_mode'], 'runtime')
                    self.assertFalse(os.path.exists(os.path.join(v, '.claude')), 'no kit file lands in a runtime-only vault')
                    self.assertEqual(open(os.path.join(v, 'CLAUDE.md')).read(), 'Mine.\n')
            report = install.install(answers(tmp, ['acme-private'], [pd], vault_mode='full'), dry_run=True, log=lambda *x: None)
            self.assertEqual(report['vault_mode'], 'full', 'switching to full is possible, but only when asked explicitly')

    def test_l1_patterns_are_segment_aware_and_doctor_agrees(self):
        self.assertTrue(plan.path_match('x.base', '*.base'))
        self.assertFalse(plan.path_match('_system/dashboards/people.base', '*.base'), '* does not cross /')
        self.assertTrue(plan.path_match('_system/dashboards/people.base', '**/*.base'))
        self.assertTrue(plan.path_match('.claude/skills/time-review/SKILL.md', '.claude/skills/time-review'), 'a folder covers its files')
        self.assertFalse(plan.path_match('a/b', '../a'))
        with tempfile.TemporaryDirectory() as tmp:
            pd = private_pack(os.path.join(tmp, 'p'), replaces=[], excludes=['CLAUDE.md', '_system/dashboards'])
            a = answers(tmp, ['acme-private'], [pd])
            os.remove(os.path.join(pd, 'vault', 'CLAUDE.md.tmpl'))
            os.remove(os.path.join(pd, 'vault', '_system', 'templates', 'daily.md'))  # replaces nothing now
            install.install(a, log=lambda *x: None)
            self.assertFalse(os.path.exists(os.path.join(a['vault_path'], 'CLAUDE.md')))
            self.assertFalse(os.path.exists(os.path.join(a['vault_path'], '_system', 'dashboards')))
            fails = [i for i in doctor.check(a['vault_path'], a['ct_home'], 'python3').items if i['level'] == 'FAIL']
            self.assertEqual(fails, [], 'excluded CLAUDE.md and dashboards are not reported missing')

    def test_l2_replaces_needs_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            pd = private_pack(os.path.join(tmp, 'p'), replaces=['CLAUDE.md', 'cockpit.md'])
            with self.assertRaises(install.InstallError) as ctx:
                install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)
            self.assertIn('ships no such file', str(ctx.exception))

    def test_l3_a_symlinked_public_pack_stays_public(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = os.path.join(tmp, 'kit')
            shutil.copytree(ROOT, kit, ignore=shutil.ignore_patterns('.git', 'tests', '__pycache__', '*.local'))
            outside = private_pack(os.path.join(tmp, 'outside'), pid='evil')
            os.symlink(outside, os.path.join(kit, 'packs', 'evil'))
            with self.assertRaises(install.InstallError) as ctx:
                install.install(answers(tmp, ['evil']), repo=kit, dry_run=True)
            self.assertIn('only private packs', str(ctx.exception))

    def test_l4_ids_cannot_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kw in ({'id': '../../x'}, {'jobs': ['../../escape']}, {'routines': ['../r']}, {'id': 'Acme'}):
                with self.subTest(**kw):
                    pd = private_pack(os.path.join(tmp, 'p' + str(abs(hash(str(kw))))), **kw)
                    with self.assertRaises(install.InstallError):
                        install.install(answers(tmp, [kw.get('id', 'acme-private')], [pd]), dry_run=True)
            self.assertFalse(os.path.exists(os.path.join(tmp, 'escape')))

    def test_l5_packs_cannot_ship_protected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rel in ('.claude/settings.json', '.control-tower/manifest.json', '.obsidian/app.json', '.mcp.json', '.git/config'):
                with self.subTest(rel=rel):
                    pd = private_pack(os.path.join(tmp, 'p' + str(abs(hash(rel)))))
                    write(os.path.join(pd, 'vault', rel), '{}')
                    with self.assertRaises(install.InstallError):
                        install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)
        for pid in install.list_packs():  # the public packs pass the same rule
            plan.check_pack_files(plan.resolve_packs(ROOT)[pid])


class RuntimeOnlyTests(unittest.TestCase):
    def existing_vault(self, tmp):
        v = os.path.join(tmp, 'vault')
        write(os.path.join(v, 'CLAUDE.md'), 'My own rules.\n')
        write(os.path.join(v, 'work', 'streams', 'alpha', 'alpha-payments.md'), '---\ntitle: "x"\n---\n')
        return v

    def snapshot(self, root):
        out = {}
        for d, _, files in os.walk(root):
            if '.control-tower' in os.path.relpath(d, root).split(os.sep):
                continue
            for f in files:
                p = os.path.join(d, f)
                out[os.path.relpath(p, root)] = open(p, 'rb').read()
        return out

    def test_runtime_only_leaves_the_vault_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = self.existing_vault(tmp)
            pd = private_pack(os.path.join(tmp, 'p'))
            before = self.snapshot(v)
            a = answers(tmp, ['acme-private'], [pd], vault_mode='runtime')
            report = install.install(a, log=lambda *x: None)
            self.assertEqual(self.snapshot(v), before, 'nothing in the vault changes except .control-tower/')
            self.assertEqual(report['created'], 0)
            self.assertTrue(os.path.isfile(os.path.join(a['ct_home'], 'jobs', 'acme-brief', 'settings.json')))
            self.assertTrue(os.path.isfile(os.path.join(a['ct_home'], 'setup-next-steps.md')))
            self.assertTrue(os.path.isfile(os.path.join(v, '.control-tower', 'manifest.json')))
            st = json.load(open(os.path.join(a['ct_home'], 'jobs', 'acme-brief', 'settings.json')))
            self.assertIn(f"Edit(/{os.path.abspath(v)}/**)", st['permissions']['allow'])
            fails = [i for i in doctor.check(v, a['ct_home'], 'python3').items if i['level'] == 'FAIL']
            self.assertEqual(fails, [], 'the doctor does not judge the user\'s own layout')
            again = install.install(a, update=True, log=lambda *x: None)
            self.assertEqual(self.snapshot(v), before, 'an update in runtime mode does not touch the vault either')
            self.assertEqual(again['updated'] + again['stashed'], [])
            r = subprocess.run([sys.executable, UNINSTALL, '--ct-home', a['ct_home'], '--vault', v, '--remove-vault-files', '--yes',
                                '--launch-agents-dir', os.path.join(tmp, 'la'), '--no-launchctl'], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(os.path.exists(a['ct_home']))
            self.assertEqual(self.snapshot(v), before, 'uninstall removes the runtime, never the user\'s files')

    def test_runtime_only_needs_an_existing_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(install.InstallError) as ctx:
                install.install(answers(tmp, ['developer'], vault_mode='runtime'), dry_run=True)
            self.assertIn('EXISTING vault', str(ctx.exception))

    def test_public_jobs_in_runtime_mode_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.existing_vault(tmp)
            a = answers(tmp, ['developer'], vault_mode='runtime', tools={'code': 'github'})
            report = install.install(a, dry_run=True, log=lambda *x: None)
            self.assertTrue(any('runtime-only mode with public-pack jobs' in w for w in report['warnings']))

    def test_cli_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.existing_vault(tmp)
            pd = private_pack(os.path.join(tmp, 'p'))
            p = os.path.join(tmp, 'answers.json')
            json.dump(answers(tmp, ['acme-private'], [pd]), open(p, 'w'))
            r = subprocess.run([sys.executable, os.path.join(ROOT, 'installer', 'install.py'), '--answers', p, '--runtime-only', '--dry-run'],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('Files: 0 would be created', r.stdout)


if __name__ == '__main__':
    unittest.main()
