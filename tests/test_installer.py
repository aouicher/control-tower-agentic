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
                for rule in allow:
                    if rule.startswith('Edit('):
                        self.assertIn(os.path.basename(vault), rule)
                hook = st['hooks']['PreToolUse'][0]['hooks'][0]['command']
                self.assertIn('guard.py', hook)
                self.assertIn('Agent', st['permissions']['deny'])
                for protected in ('.claude/**', '.control-tower/**', '.obsidian/**'):
                    self.assertIn(f'Edit({os.path.abspath(a["vault_path"])}/{protected})', st['permissions']['deny'], f'{j["id"]}: {protected} must be protected')
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
            local = install.local_time('07:15', 'UTC')[0]  # the schedule uses machine time: expected value depends on the machine
            h, m = (int(x) for x in local.split(':'))
            self.assertRegex(cron, rf'{m} {h} \* \* 1,3 python3 .*run_job\.py --job morning-prs')

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


class UninstallTests(unittest.TestCase):
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
