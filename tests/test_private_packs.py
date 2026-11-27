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


class PermissionPolicyTests(unittest.TestCase):
    """Pack job rules are checked by the installer (plan.permission_problem, table in tests/test_permissions.py); the guard
    keeps the run-time limits on files."""

    def test_relative_paths_are_relative_to_the_job_not_the_hook(self):
        guard = plan.guard_rules
        with tempfile.TemporaryDirectory() as v:
            os.makedirs(os.path.join(v, 'work'))
            ev = lambda tool, inp: guard.check({'tool_name': tool, 'tool_input': inp, 'cwd': v}, v)
            self.assertIsNone(ev('Grep', {'pattern': '#to-triage', 'path': 'work'}))
            self.assertIsNone(ev('Read', {'file_path': 'work/x.md'}))
            self.assertIsNotNone(ev('Read', {'file_path': '../outside.md'}))
            self.assertIsNotNone(ev('Grep', {'pattern': 'x', 'path': '../..'}))

    def test_a_job_can_reread_only_its_own_saved_tool_output(self):
        guard = plan.guard_rules
        home = os.path.expanduser('~/.claude/projects/-tmp-ct-test')
        sid, other = 'aaaaaaaa-1111-2222-3333-4444444444aa', 'bbbbbbbb-1111-2222-3333-4444444444bb'
        mine = os.path.join(home, sid, 'tool-results', 'out.txt')
        theirs = os.path.join(home, other, 'tool-results', 'out.txt')
        with tempfile.TemporaryDirectory() as v:
            ev = lambda p, s=sid, t=os.path.join(home, sid + '.jsonl'): guard.check(
                {'tool_name': 'Read', 'tool_input': {'file_path': p}, 'cwd': v, 'session_id': s, 'transcript_path': t}, v)
            self.assertIsNone(ev(mine))
            self.assertIsNotNone(ev(theirs), 'another session')
            self.assertIsNotNone(ev(os.path.join(home, sid, 'other.txt')), 'outside tool-results')
            self.assertIsNotNone(ev(mine, s='../x'), 'bad session id')
            self.assertIsNotNone(ev(mine, t='/tmp/fake.jsonl'), 'transcript outside ~/.claude/projects')

    def test_no_git_or_claude_files_anywhere_in_the_vault(self):
        guard = plan.guard_rules
        with tempfile.TemporaryDirectory() as v:
            for rel in ('notes/sub/.git/config', 'notes/sub/.git/HEAD', 'notes/CLAUDE.md', 'work/x/claude.local.md', 'a/.claude/settings.json',
                        'a/.obsidian/app.json', 'a/.mcp.json', 'a/.vscode/tasks.json'):
                with self.subTest(rel=rel):
                    self.assertIsNotNone(guard.check({'tool_name': 'Write', 'tool_input': {'file_path': os.path.join(v, rel)}, 'cwd': v}, v))
            self.assertIsNone(guard.check({'tool_name': 'Write', 'tool_input': {'file_path': os.path.join(v, 'notes', 'x.md')}, 'cwd': v}, v))

    def test_install_refuses_a_bad_rule_before_writing_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            pd = private_pack(os.path.join(tmp, 'p'))
            jp = os.path.join(pd, 'jobs', 'acme-brief', 'job.json')
            job = json.load(open(jp))
            job['permissions']['allow'] = ['Bash(sh -c:*)']
            json.dump(job, open(jp, 'w'))
            a = answers(tmp, ['acme-private'], [pd])
            with self.assertRaises(install.InstallError):
                install.install(a, log=lambda *x: None)
            self.assertFalse(os.path.exists(a['vault_path']), 'the plan fails before the first write')
            self.assertFalse(os.path.exists(a['ct_home']))
            with self.assertRaises(install.InstallError):
                install.install(answers(tmp, ['acme-private'], [pd], permissions={'tracker': ['Bash']}), dry_run=True)

    def test_rules_are_checked_after_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            pd = private_pack(os.path.join(tmp, 'p'))
            write(os.path.join(pd, 'vocabulary.json'), json.dumps({'team': {'singular': 'x; touch PWNED', 'plural': 'xs'}}))
            jp = os.path.join(pd, 'jobs', 'acme-brief', 'job.json')
            job = json.load(open(jp))
            job['permissions']['allow'] = ['Bash(git log {{ct.team}}:*)']
            json.dump(job, open(jp, 'w'))
            with self.assertRaises(install.InstallError):
                install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)


class PackContentTests(unittest.TestCase):
    """What a pack may ship, and how its ids and patterns are read."""

    def test_patterns_are_segment_aware_and_the_doctor_agrees(self):
        self.assertTrue(plan.path_match('x.base', '*.base'))
        self.assertFalse(plan.path_match('_system/dashboards/people.base', '*.base'), '* does not cross /')
        self.assertTrue(plan.path_match('_system/dashboards/people.base', '**/*.base'))
        self.assertTrue(plan.path_match('.claude/skills/time-review/SKILL.md', '.claude/skills/time-review'), 'a folder covers its files')
        self.assertTrue(plan.path_match('CLAUDE.md', './CLAUDE.md'))
        self.assertFalse(plan.path_match('a/b', '../a'))
        with tempfile.TemporaryDirectory() as tmp:
            pd = private_pack(os.path.join(tmp, 'p'), replaces=[], excludes=['CLAUDE.md', '_system/dashboards'])
            os.remove(os.path.join(pd, 'vault', 'CLAUDE.md.tmpl'))
            os.remove(os.path.join(pd, 'vault', '_system', 'templates', 'daily.md'))
            a = answers(tmp, ['acme-private'], [pd])
            install.install(a, log=lambda *x: None)
            self.assertFalse(os.path.exists(os.path.join(a['vault_path'], 'CLAUDE.md')))
            self.assertFalse(os.path.exists(os.path.join(a['vault_path'], '_system', 'dashboards')))
            fails = [i for i in doctor.check(a['vault_path'], a['ct_home'], 'python3').items if i['level'] == 'FAIL']
            self.assertEqual(fails, [], 'excluded CLAUDE.md and dashboards are not reported missing')

    def test_replaces_needs_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            pd = private_pack(os.path.join(tmp, 'p'), replaces=['CLAUDE.md', 'cockpit.md'])
            with self.assertRaises(install.InstallError) as ctx:
                install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)
            self.assertIn('ships no such file', str(ctx.exception))

    def test_a_symlinked_public_pack_stays_public(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = os.path.join(tmp, 'kit')
            shutil.copytree(ROOT, kit, ignore=shutil.ignore_patterns('.git', 'tests', '__pycache__', '*.local'))
            outside = private_pack(os.path.join(tmp, 'outside'), pid='evil')
            os.symlink(outside, os.path.join(kit, 'packs', 'evil'))
            with self.assertRaises(install.InstallError) as ctx:
                install.install(answers(tmp, ['evil']), repo=kit, dry_run=True)
            self.assertIn('only private packs', str(ctx.exception))

    def test_ids_cannot_become_paths_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kw in ({'id': '../../x'}, {'jobs': ['../../escape']}, {'routines': ['../r']}, {'id': 'Acme'}):
                with self.subTest(**kw):
                    pd = private_pack(os.path.join(tmp, 'p' + str(abs(hash(str(kw))))), **kw)
                    with self.assertRaises(install.InstallError):
                        install.install(answers(tmp, [kw.get('id', 'acme-private')], [pd]), dry_run=True)
            self.assertFalse(os.path.exists(os.path.join(tmp, 'escape')))

    def test_protected_files_whatever_their_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rel in ('.claude/settings.json', '.CLAUDE/settings.json', '.Claude/Settings.json', '.control-tower/manifest.json',
                        '.Obsidian/app.json', '.mcp.json', '.Mcp.json', '.git/config', '.GIT/hooks/post-commit', '.claude/hooks/x.sh',
                        '.github/workflows/x.yml', '.vscode/settings.json', '.claude/adapters/x.md'):
                with self.subTest(rel=rel):
                    pd = private_pack(os.path.join(tmp, 'p' + str(abs(hash(rel)))))
                    write(os.path.join(pd, 'vault', rel), '{}')
                    with self.assertRaises(install.InstallError):
                        install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)

    def test_shippable_and_protected_lists_come_from_the_guard(self):
        sys.path.insert(0, os.path.join(ROOT, 'scheduler'))
        import guard
        for p in list(guard.PROTECTED) + list(guard.PROTECTED_FILES):
            shippable = any(plan.path_match(p + '/x', s, ignore_case=True) or plan.path_match(p, s, ignore_case=True)
                            for s in plan.PACK_SHIPPABLE)
            with self.subTest(protected=p):
                self.assertTrue(shippable or plan.forbidden_pack_file(p + '/x') or plan.forbidden_pack_file(p))
        self.assertEqual(install.PROTECTED_DIRS, guard.PROTECTED, 'job deny rules use the guard list')
        for pid in install.list_packs():  # the public packs pass the same rule
            plan.check_pack(plan.resolve_packs(ROOT)[pid])

    def test_pack_folders_must_be_real_and_inside_the_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = os.path.join(tmp, 'outside')
            write(os.path.join(outside, 'notes', 'secret.md'), 'TOPSECRET')
            for sub_dir in ('vault', 'jobs'):
                with self.subTest(folder=sub_dir):
                    pd = private_pack(os.path.join(tmp, 'p-' + sub_dir))
                    shutil.rmtree(os.path.join(pd, sub_dir))
                    os.symlink(outside, os.path.join(pd, sub_dir))
                    with self.assertRaises(install.InstallError):
                        install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)
            pd = private_pack(os.path.join(tmp, 'p-vocab'), vocabulary='../../etc/x.json')
            with self.assertRaises(install.InstallError):
                install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)

    def test_nested_git_or_claude_folders_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rel in ('.claude/skills/x/.git/hooks/post-commit', '.claude/rules/x/.claude/settings.json', '_system/templates/.git/config'):
                with self.subTest(rel=rel):
                    pd = private_pack(os.path.join(tmp, 'p' + str(abs(hash(rel)))))
                    write(os.path.join(pd, 'vault', rel), 'x')
                    with self.assertRaises(install.InstallError):
                        install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)

    def test_pack_files_may_not_grant_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            headers = ('---\nname: x\n{{ct.team}}: Read\n---\n', '---\nname: x\nmodel: opus\n---\n', '---\nname: "x\\u0061"\n---\n',
                       '---\nname: x\nallowed-tools: Read\n---\n', '\ufeff---\r\nname: x\r\nallowed-tools: Bash\r\n---\r\n',
                       '---\nname: x\nallowed_tools: [Write]\n---\n', '---\nname: x\n"Allowed-Tools":\n  - Bash\n---\n',
                       '---\nname: x\nallowed-tools: [Read,\n  Bash]\n---\n', '---\nname: x\nallowed-tools:\n  # c\n  - Bash\n---\n',
                       '---\nname: x\n? allowed-tools\n: Bash\n---\n')
            for i, header in enumerate(headers):
                with self.subTest(header=header[:40]):
                    pd = private_pack(os.path.join(tmp, f'p{i}'))
                    write(os.path.join(pd, 'vocabulary.json'), json.dumps({'team': {'singular': 'allowed-tools', 'plural': 'x'}}))
                    write(os.path.join(pd, 'vault', '.claude', 'skills', 'x', 'SKILL.md'), header + '# x\n')
                    with self.assertRaises(install.InstallError):
                        install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)
        for pid in install.list_packs():  # the public packs and the core never use it
            plan.check_pack(plan.resolve_packs(ROOT)[pid])

    def test_symlinks_in_a_pack_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = os.path.join(tmp, 'secret.txt')
            write(secret, 'TOPSECRET')
            for where in ('vault/notes/leak.md', 'jobs/acme-brief/extra.md'):
                with self.subTest(where=where):
                    pd = private_pack(os.path.join(tmp, 'p' + str(abs(hash(where)))))
                    os.makedirs(os.path.dirname(os.path.join(pd, where)), exist_ok=True)
                    os.symlink(secret, os.path.join(pd, where))
                    with self.assertRaises(install.InstallError) as ctx:
                        install.install(answers(tmp, ['acme-private'], [pd]), dry_run=True)
                    self.assertIn('symlink', str(ctx.exception))


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

    def test_runtime_mode_is_remembered(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = self.existing_vault(tmp)
            before = self.snapshot(v)
            pd = private_pack(os.path.join(tmp, 'p'))
            install.install(answers(tmp, ['acme-private'], [pd], vault_mode='runtime'), log=lambda *x: None)
            plain = answers(tmp, ['acme-private'], [pd])  # the user's own answers file, without vault_mode
            for kw in ({}, {'update': True}):
                with self.subTest(**kw):
                    self.assertEqual(install.install(plain, log=lambda *x: None, **kw)['vault_mode'], 'runtime')
                    self.assertEqual(self.snapshot(v), before, 'no kit file lands in a runtime-only vault')
            report = install.install(answers(tmp, ['acme-private'], [pd], vault_mode='full'), dry_run=True, log=lambda *x: None)
            self.assertEqual(report['vault_mode'], 'full', 'switching to full is possible, only when asked explicitly')

    def test_wide_vault_settings_are_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = self.existing_vault(tmp)
            write(os.path.join(v, '.claude', 'settings.json'), json.dumps({'permissions': {'allow': ['Bash(git commit:*)']}}))
            write(os.path.join(v, '.claude', 'skills', 'mine', 'SKILL.md'), '---\nname: mine\nallowed-tools: Bash\n---\n')
            pd = private_pack(os.path.join(tmp, 'p'))
            report = install.install(answers(tmp, ['acme-private'], [pd], vault_mode='runtime'), dry_run=True, log=lambda *x: None)
            self.assertTrue(any('none runs until it is empty' in w for w in report['warnings']))
            self.assertTrue(any('declares allowed-tools' in w for w in report['warnings']))
            write(os.path.join(v, '.claude', 'settings.local.json'), json.dumps({'enabledMcpjsonServers': []}))
            os.remove(os.path.join(v, '.claude', 'settings.json'))
            install.install(answers(tmp, ['acme-private'], [pd], vault_mode='runtime'), log=lambda *x: None)
            levels = {i['check']: i['level'] for i in doctor.check(v, os.path.join(tmp, 'ct'), 'python3').items}
            self.assertNotIn('vault file .claude/settings.local.json', levels, 'harmless settings are not flagged')
            for risky in ({'env': {'X': '1'}}, {'permissions': {'additionalDirectories': ['/']}}, {'apiKeyHelper': 'x'},
                          {'enabledMcpjsonServers': ['evil']}, {'enableAllProjectMcpServers': True}):
                with self.subTest(risky=risky):
                    write(os.path.join(v, '.claude', 'settings.local.json'), json.dumps(risky))
                    levels = {i['check']: i['level'] for i in doctor.check(v, os.path.join(tmp, 'ct'), 'python3').items}
                    self.assertEqual(levels.get('vault file .claude/settings.local.json'), 'warn')
            write(os.path.join(v, '.claude', 'settings.json'), json.dumps({'hooks': {}}))
            levels = {i['check']: i['level'] for i in doctor.check(v, os.path.join(tmp, 'ct'), 'python3').items}
            self.assertEqual(levels.get('vault file .claude/settings.json'), 'FAIL', 'jobs load it: the runner refuses to start them')

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
