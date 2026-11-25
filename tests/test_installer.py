#!/usr/bin/env python3
"""End-to-end tests of the installer, the doctor and the uninstaller in throwaway directories.

Run:  python3 -W ignore -m unittest tests/test_installer.py -v   (from the repository root)
Nothing outside the temporary directories is touched: no real vault, no real ~/.claude, no launchctl, no crontab.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
import doctor  # noqa: E402
import install  # noqa: E402

INSTALL = os.path.join(ROOT, 'installer', 'install.py')
UNINSTALL = os.path.join(ROOT, 'installer', 'uninstall.py')


def answers_for(tmp, packs, scheduler='launchd', tools=None):
    tools = dict(tools or {})
    if tools == {}:
        for p in packs:
            manifest = json.load(open(os.path.join(ROOT, 'packs', p, 'pack.json'), encoding='utf-8'))
            for q in manifest['questions']:
                choice = next((c for c in q['choices'] if c != 'none'), 'none')
                tools.setdefault(q['capability'], choice)
    return {'owner_name': 'Test User', 'owner_handle': 'tester', 'timezone': 'UTC',
            'vault_path': os.path.join(tmp, 'vault'), 'ct_home': os.path.join(tmp, 'ct'),
            'packs': packs, 'tools': tools, 'scheduler': scheduler}


class InstallTests(unittest.TestCase):
    def test_every_pack_installs_and_passes_the_doctor(self):
        for pack in install.list_packs():
            with self.subTest(pack=pack), tempfile.TemporaryDirectory() as tmp:
                a = answers_for(tmp, [pack])
                report = install.install(a, log=lambda *x: None)
                self.assertGreater(report['created'], 40)
                result = doctor.check(a['vault_path'], a['ct_home'], 'python3')
                fails = [i for i in result.items if i['level'] == 'FAIL']
                self.assertEqual(fails, [], f'{pack}: doctor failures')
                self.assertTrue(report['jobs'], f'{pack}: no job installed although every tool was chosen')

    def test_all_packs_together_do_not_collide(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, install.list_packs())
            try:
                install.install(a)
            except install.InstallError as exc:
                self.fail(f'packs collide: {exc}')

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'])
            report = install.install(a, dry_run=True)
            self.assertGreater(report['created'], 0)
            self.assertFalse(os.path.exists(a['vault_path']))
            self.assertFalse(os.path.exists(a['ct_home']))

    def test_second_run_is_idempotent_and_keeps_user_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['product'])
            install.install(a)
            note = os.path.join(a['vault_path'], 'cockpit.md')
            with open(note, 'a', encoding='utf-8') as fh:
                fh.write('\nMy own line.\n')
            again = install.install(a)
            self.assertEqual(again['created'], 0, 'a second run must not create anything new')
            self.assertIn('My own line.', open(note, encoding='utf-8').read())

    def test_jobs_need_their_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['engineering'], tools={'calendar': 'none', 'tracker': 'none', 'code': 'none', 'errors': 'none', 'quality': 'none', 'logs': 'none'})
            report = install.install(a)
            self.assertEqual(report['jobs'], [])
            self.assertTrue(report['jobs_skipped'])
            self.assertTrue(os.path.isdir(os.path.join(a['vault_path'], '.claude/skills/weekly-digest')))

    def test_job_files_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['engineering'])
            report = install.install(a)
            vault = os.path.realpath(a['vault_path'])
            for j in report['jobs']:
                jd = os.path.join(a['ct_home'], 'jobs', j['id'])
                prompt = open(os.path.join(jd, 'prompt.md'), encoding='utf-8').read()
                self.assertNotIn('{{ct.', prompt)
                self.assertIn('never ask', prompt.lower())
                st = json.load(open(os.path.join(jd, 'settings.json')))
                allow = st['permissions']['allow']
                self.assertNotIn('Write', allow)
                self.assertNotIn('Bash', allow)
                edits = [r for r in allow if r.startswith('Edit(')]
                self.assertEqual(edits, [f"Edit(/{os.path.abspath(a['vault_path'])}/**)"], 'one absolute (//) vault-wide write rule')
                hook = st['hooks']['PreToolUse'][0]['hooks'][0]['command']
                self.assertIn('guard.py', hook)
                self.assertIn('Agent', st['permissions']['deny'])
                for protected in ('.claude/**', '.control-tower/**', '.obsidian/**', '.git/**'):
                    self.assertIn(f'Edit(/{os.path.abspath(a["vault_path"])}/{protected})', st['permissions']['deny'], f'{j["id"]}: {protected} must be protected')
                self.assertTrue(all(r.startswith('Edit(//') for r in st['permissions']['deny'] if r.startswith('Edit(')))
                self.assertTrue(os.path.isfile(os.path.join(a['ct_home'], 'bin', 'guard.py')))

    def test_routines_are_rendered_and_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['engineering'])
            report = install.install(a)
            index = json.load(open(os.path.join(a['ct_home'], 'routines', 'routines.json')))
            self.assertEqual({r['key'] for r in index}, {r['key'] for r in report['routines']})
            self.assertTrue(index)
            for r in index:
                prompt = open(r['prompt_file'], encoding='utf-8').read()
                self.assertNotIn('{{ct.', prompt)
                self.assertRegex(r['cron'], r'^\d{1,2} \d{1,2} \* \* [0-6](,[0-6])*$')
                self.assertEqual(r['timezone'], 'UTC')
            prompts = ''.join(open(r['prompt_file'], encoding='utf-8').read() for r in index)
            self.assertIn('Test User', prompts, 'answers must be rendered into the prompts')
            note = open(os.path.join(a['vault_path'], 'library', 'setup-next-steps.md'), encoding='utf-8').read()
            self.assertIn('/install-control-tower routines', note)

    def test_routines_need_their_connectors_and_dry_run_writes_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['engineering'], tools={'calendar': 'none', 'tracker': 'none', 'code': 'none', 'errors': 'none', 'quality': 'none', 'logs': 'none'})
            report = install.install(a, dry_run=True)
            skipped = {r['id'] for r in report['routines_skipped']}
            self.assertIn('engineering--daily-note', skipped, 'daily-note needs the calendar connector')
            self.assertIn('engineering--weekly-review', {r['key'] for r in report['routines']})
            self.assertFalse(os.path.exists(a['ct_home']))

    def test_routine_names_are_unique_across_packs(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = install.install(answers_for(tmp, install.list_packs()), dry_run=True)
            names = [r['name'] for r in report['routines']]
            self.assertEqual(len(names), len(set(names)), names)

    def test_user_schedule_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'], scheduler='cron')
            a['jobs'] = {'morning-prs': {'time': '07:15', 'days': 'mon,wed'}}
            report = install.install(a)
            job = next(j for j in report['jobs'] if j['id'] == 'morning-prs')
            self.assertEqual((job['time'], job['days']), ('07:15', 'mon,wed'))
            cron = open(os.path.join(a['ct_home'], 'schedule', 'crontab.txt'), encoding='utf-8').read()
            self.assertIn('# BEGIN control-tower', cron)
            local, shift, _ = install.local_time('07:15', 'UTC')  # the schedule uses machine time
            h, m = (int(x) for x in local.split(':'))
            dow = ','.join(str(d) for d in install.shift_days([1, 3], shift))
            self.assertRegex(cron, rf'{m} {h} \* \* {dow} \S*python\S* .*run_job\.py --job morning-prs')

    def test_apply_schedule_links_plists_without_loading_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'], scheduler='launchd')
            la = os.path.join(tmp, 'LaunchAgents')
            report = install.install(a, apply_schedule=True, launch_agents_dir=la, no_launchctl=True)
            self.assertTrue(report['schedule']['applied'])
            links = [f for f in os.listdir(la) if f.startswith('com.control-tower.')]
            self.assertTrue(links)
            self.assertTrue(all(os.path.islink(os.path.join(la, f)) for f in links))

    def test_validation_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad, text in ((dict(packs=['nope']), 'unknown pack'), (dict(tools={'tracker': 'notatool'}), 'no adapter'),
                              (dict(timezone='Mars/Base'), 'timezone'), (dict(owner_handle='bad handle!'), 'owner_handle'),
                              (dict(scheduler='systemd'), 'scheduler')):
                a = answers_for(tmp, ['developer'])
                a.update(bad)
                with self.subTest(bad=bad), self.assertRaises(install.InstallError) as ctx:
                    install.install(a, dry_run=True)
                self.assertIn(text, str(ctx.exception))

    def test_obsidian_config_is_seeded_only_for_a_new_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'])
            os.makedirs(os.path.join(a['vault_path'], '.obsidian'))
            install.install(a)
            self.assertEqual(os.listdir(os.path.join(a['vault_path'], '.obsidian')), [], 'an existing .obsidian must not be touched')
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'])
            install.install(a)
            daily = json.load(open(os.path.join(a['vault_path'], '.obsidian', 'daily-notes.json')))
            self.assertEqual(daily['folder'], 'journal/daily')
            obs = os.path.join(a['vault_path'], '.obsidian')
            self.assertFalse(json.load(open(os.path.join(obs, 'app.json')))['readableLineLength'], 'would override the width snippet')
            self.assertIn('wide-pages', json.load(open(os.path.join(obs, 'appearance.json')))['enabledCssSnippets'])
            self.assertTrue(os.path.isfile(os.path.join(obs, 'snippets', 'wide-pages.css')))

    def test_next_steps_note_lists_the_commands_but_installer_runs_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['engineering'])
            install.install(a)
            note = open(os.path.join(a['vault_path'], 'library', 'setup-next-steps.md'), encoding='utf-8').read()
            self.assertIn('claude mcp add', note)
            self.assertIn('Tasks', note)
            self.assertIn('read-only', note.lower())

    def test_wizard_builds_valid_answers(self):
        scripted = iter(['Sam', 'sam', 'UTC', '/tmp/ct-wizard-vault', 'developer', 'github', 'none', 'none', 'none', 'none'])
        a = install.wizard(ask=lambda prompt: next(scripted, ''), out=lambda *x: None)
        self.assertEqual(a['packs'], ['developer'])
        self.assertEqual(a['tools'].get('code'), 'github')
        install.validate(a)

    def test_cli_dry_run_and_error_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'])
            p = os.path.join(tmp, 'answers.json')
            json.dump(a, open(p, 'w'))
            ok = subprocess.run([sys.executable, INSTALL, '--answers', p, '--dry-run'], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn('DRY RUN', ok.stdout)
            a['packs'] = ['ghost']
            json.dump(a, open(p, 'w'))
            bad = subprocess.run([sys.executable, INSTALL, '--answers', p], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)
            self.assertIn('unknown pack', bad.stderr)


class RobustnessTests(unittest.TestCase):
    def test_bad_days_fail_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'])
            a['jobs'] = {'morning-prs': {'days': 'funday'}}
            with self.assertRaises(install.InstallError) as ctx:
                install.install(a)
            self.assertIn('unknown day', str(ctx.exception))
            self.assertFalse(os.path.exists(a['vault_path']))
            a['jobs'] = {'morning-prs': '08:00'}
            with self.assertRaises(install.InstallError):
                install.install(a)

    def test_invalid_json_answers_give_a_plain_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'answers.json')
            open(p, 'w').write('{"packs": [')
            r = subprocess.run([sys.executable, INSTALL, '--answers', p], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertIn('not valid JSON', r.stderr)
            self.assertNotIn('Traceback', r.stderr)
            r = subprocess.run([sys.executable, INSTALL, '--answers', os.path.join(tmp, 'missing.json')], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertNotIn('Traceback', r.stderr)

    def test_disabled_job_leaves_the_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'], scheduler='launchd')
            la = os.path.join(tmp, 'LA')
            install.install(a, apply_schedule=True, launch_agents_dir=la, no_launchctl=True)
            self.assertTrue(os.path.lexists(os.path.join(la, 'com.control-tower.morning-prs.plist')))
            a['jobs'] = {'morning-prs': {'enabled': False}}
            install.install(a, apply_schedule=True, launch_agents_dir=la, no_launchctl=True)
            self.assertFalse(os.path.lexists(os.path.join(la, 'com.control-tower.morning-prs.plist')))
            self.assertFalse(os.path.exists(os.path.join(a['ct_home'], 'jobs', 'morning-prs')))
            self.assertTrue(os.path.lexists(os.path.join(la, 'com.control-tower.weekly-wrap.plist')))

    def test_optional_capabilities_do_not_block_a_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'], tools={'code': 'github', 'tracker': 'none', 'errors': 'none', 'calendar': 'none'})
            ids = {j['id'] for j in install.install(a, dry_run=True)['jobs']}
            self.assertEqual(ids, {'morning-prs', 'weekly-wrap'}, 'a developer with GitHub only gets the jobs')
            a = answers_for(tmp, ['marketing'], tools={'analytics': 'none', 'crm': 'none', 'tracker': 'none', 'calendar': 'none'})
            ids = {j['id'] for j in install.install(a, dry_run=True)['jobs']}
            self.assertEqual(ids, {'content-reminders'}, 'a vault-only job needs no tool')

    def test_hook_command_survives_spaces_and_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'])
            a['vault_path'] = os.path.join(tmp, "my vault's notes")
            a['ct_home'] = os.path.join(tmp, 'ct home')
            report = install.install(a)
            st = json.load(open(os.path.join(a['ct_home'], 'jobs', report['jobs'][0]['id'], 'settings.json')))
            cmd = st['hooks']['PreToolUse'][0]['hooks'][0]['command']
            ok = {'tool_name': 'Write', 'tool_input': {'file_path': os.path.join(a['vault_path'], 'journal', 'reports', 'r.md')}, 'cwd': a['vault_path']}
            bad = {'tool_name': 'Write', 'tool_input': {'file_path': os.path.join(a['vault_path'], '.git', 'config')}, 'cwd': a['vault_path']}
            self.assertEqual(subprocess.run(cmd, shell=True, input=json.dumps(ok), text=True, capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run(cmd, shell=True, input=json.dumps(bad), text=True, capture_output=True).returncode, 2)


class UpdateTests(unittest.TestCase):
    """`--update` after a new version of the kit: untouched files refreshed, edited files kept, deleted files left deleted."""
    def test_update_respects_what_the_user_did(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            kit = os.path.join(tmp, 'kit')
            shutil.copytree(ROOT, kit, ignore=shutil.ignore_patterns('.git', 'tests', '__pycache__', '*.local'))
            a = answers_for(tmp, ['developer'], scheduler='none')
            install.install(a, repo=kit, log=lambda *x: None)
            v = a['vault_path']
            skill = os.path.join(v, '.claude', 'skills', 'today', 'SKILL.md')
            claude_md = os.path.join(v, 'CLAUDE.md')
            research = os.path.join(v, '.claude', 'skills', 'research', 'SKILL.md')
            with open(claude_md, 'a', encoding='utf-8') as fh:
                fh.write('\nMy own rule.\n')
            os.remove(research)
            # a new version of the kit changes three files and adds one
            for rel in ('core/vault/.claude/skills/today/SKILL.md', 'core/vault/CLAUDE.md.tmpl', 'core/vault/.claude/skills/research/SKILL.md'):
                with open(os.path.join(kit, rel), 'a', encoding='utf-8') as fh:
                    fh.write('\nKit v2 line.\n')
            os.makedirs(os.path.join(kit, 'core', 'vault', 'library'), exist_ok=True)
            open(os.path.join(kit, 'core', 'vault', 'library', 'whats-new.md'), 'w').write('---\ntitle: "New"\ntype: resource\n---\n# New\n')

            dry = install.install(a, repo=kit, dry_run=True, update=True, log=lambda *x: None)
            self.assertNotIn('Kit v2 line.', open(skill, encoding='utf-8').read(), 'a dry run changes nothing')
            self.assertIn('.claude/skills/today/SKILL.md', dry['updated'])

            report = install.install(a, repo=kit, update=True, log=lambda *x: None)
            self.assertIn('Kit v2 line.', open(skill, encoding='utf-8').read(), 'an untouched file is refreshed')
            text = open(claude_md, encoding='utf-8').read()
            self.assertIn('My own rule.', text)
            self.assertNotIn('Kit v2 line.', text, 'an edited file is never overwritten')
            self.assertEqual(report['stashed'], ['CLAUDE.md'])
            stashed = open(os.path.join(report['stash_dir'], 'CLAUDE.md'), encoding='utf-8').read()
            self.assertIn('Kit v2 line.', stashed, 'the new version is saved for a manual merge')
            self.assertFalse(os.path.exists(research), 'a file the user deleted is not recreated')
            self.assertTrue(os.path.isfile(os.path.join(v, 'library', 'whats-new.md')), 'new kit files are added')

            again = install.install(a, repo=kit, update=True, log=lambda *x: None)
            self.assertEqual(again['updated'], [], 'a second update has nothing left to refresh')
            self.assertEqual(again['stashed'], ['CLAUDE.md'], 'the edited file is still reported until merged')
            self.assertIn('Kit v2 line.', open(skill, encoding='utf-8').read())

    def test_update_needs_an_installed_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(install.InstallError):
                install.install(answers_for(tmp, ['developer']), update=True, dry_run=True)


class CrontabTests(unittest.TestCase):
    """apply() against a fake `crontab` binary: the user's own lines survive, the block is replaced, read errors abort."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = os.path.join(self.tmp.name, 'bin')
        os.makedirs(self.bin)
        self.store = os.path.join(self.tmp.name, 'crontab.store')
        open(self.store, 'w').write('0 1 * * * my-own-backup\n')
        fake = os.path.join(self.bin, 'crontab')
        open(fake, 'w').write('#!/bin/sh\nif [ -n "$FAIL_READ" ] && [ "$1" = "-l" ]; then echo "permission denied" >&2; exit 1; fi\n'
                              f'if [ "$1" = "-l" ]; then cat {self.store}; else cat > {self.store}; fi\n')
        os.chmod(fake, 0o755)
        self.path = os.environ['PATH']
        os.environ['PATH'] = self.bin + os.pathsep + self.path

    def tearDown(self):
        os.environ['PATH'] = self.path
        os.environ.pop('FAIL_READ', None)
        self.tmp.cleanup()

    def test_block_is_installed_and_replaced_keeping_user_lines(self):
        a = answers_for(self.tmp.name, ['developer'], scheduler='cron')
        report = install.install(a, apply_schedule=True)
        self.assertTrue(report['schedule']['applied'], report['warnings'])
        cur = open(self.store).read()
        self.assertIn('my-own-backup', cur)
        self.assertEqual(cur.count('# BEGIN control-tower'), 1)
        install.install(a, apply_schedule=True)
        self.assertEqual(open(self.store).read().count('# BEGIN control-tower'), 1, 'a second apply replaces the block')

    def test_read_error_leaves_the_crontab_alone(self):
        os.environ['FAIL_READ'] = '1'
        report = install.install(answers_for(self.tmp.name, ['developer'], scheduler='cron'), apply_schedule=True)
        self.assertFalse(report['schedule']['applied'])
        self.assertEqual(open(self.store).read(), '0 1 * * * my-own-backup\n')


class UninstallTests(unittest.TestCase):
    def test_uninstall_refuses_a_folder_it_did_not_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            precious = os.path.join(tmp, 'precious')
            os.makedirs(precious)
            open(os.path.join(precious, 'notes.md'), 'w').write('keep me')
            r = subprocess.run([sys.executable, UNINSTALL, '--ct-home', precious, '--yes', '--launch-agents-dir', os.path.join(tmp, 'la'), '--no-launchctl'],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertTrue(os.path.isfile(os.path.join(precious, 'notes.md')))

    def test_uninstall_keeps_edited_files_and_removes_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = answers_for(tmp, ['developer'], scheduler='none')
            install.install(a)
            edited = os.path.join(a['vault_path'], 'CLAUDE.md')
            with open(edited, 'a', encoding='utf-8') as fh:
                fh.write('\nMy rule.\n')
            mine = os.path.join(a['vault_path'], 'work', 'projects', 'my-note.md')
            open(mine, 'w').write('# mine\n')
            cmd = [sys.executable, UNINSTALL, '--ct-home', a['ct_home'], '--vault', a['vault_path'], '--remove-vault-files',
                   '--launch-agents-dir', os.path.join(tmp, 'la'), '--no-launchctl']
            dry = subprocess.run(cmd, capture_output=True, text=True)
            self.assertIn('Dry run', dry.stdout)
            self.assertTrue(os.path.isdir(a['ct_home']), 'a dry run must not remove anything')
            done = subprocess.run(cmd + ['--yes'], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertFalse(os.path.exists(a['ct_home']))
            self.assertTrue(os.path.isfile(edited), 'an edited file must be kept')
            self.assertTrue(os.path.isfile(mine), "the user's own notes are never removed")
            self.assertFalse(os.path.exists(os.path.join(a['vault_path'], 'cockpit.md')))


class SkillTests(unittest.TestCase):
    def test_install_skill_is_safe_and_well_formed(self):
        path = os.path.join(ROOT, '.claude', 'skills', 'install-control-tower', 'SKILL.md')
        text = open(path, encoding='utf-8').read()
        m = __import__('re').match(r'---\n(.*?)\n---\n', text, __import__('re').S)
        self.assertIsNotNone(m)
        self.assertIn('name: install-control-tower', m.group(1))
        self.assertIn('description:', m.group(1))
        for needle in ('--dry-run', 'doctor.py', 'NEVER ask for', 'claude mcp add', 'explicit "yes"', 'uninstall',
                       'routines.json', 'must not create duplicates', 'never updated or deleted', 'prompt_file'):
            self.assertIn(needle, text, f'the install skill must mention: {needle}')
        self.assertIsNone(__import__('re').search(r'[àâäçéèêëîïôöùûüÿœ]', text, __import__('re').I), 'English only')


if __name__ == '__main__':
    unittest.main()
