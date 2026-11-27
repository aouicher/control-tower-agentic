"""installer/configure.py `show` and `set`: the one door to the answers. Every change is checked before anything is written,
then applied by the installer; a refused change leaves answers.json byte-identical. Temporary folders only; the schedule
is launchd in a temporary LaunchAgents folder, never loaded (works on Linux too)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import install  # noqa: E402
from test_private_packs import answers  # noqa: E402

CONFIGURE = os.path.join(ROOT, 'installer', 'configure.py')


class ConfigureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = self._tmp.name
        self.la = os.path.join(tmp, 'LaunchAgents')
        self.a = answers(tmp, ['developer'], tools={'code': 'github'}, scheduler='launchd')
        install.install(self.a, log=lambda *x: None)
        self.vault = self.a['vault_path']
        self.path = os.path.join(self.vault, '.control-tower', 'answers.json')

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, CONFIGURE] + list(args) + ['--vault', self.vault, '--launch-agents-dir', self.la,
                                                                          '--no-launchctl'], capture_output=True, text=True)

    def show(self):
        r = self.cli('show')
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def job(self, jid):
        return next(j for j in self.show()['jobs'] if j['id'] == jid)

    def saved(self):
        return json.load(open(self.path))

    def test_show(self):
        s = self.show()
        self.assertEqual(s['packs'], ['developer'])
        self.assertEqual(s['tools']['code'], 'github')
        prs = self.job('morning-prs')
        default = json.load(open(os.path.join(ROOT, 'packs', 'developer', 'jobs', 'morning-prs', 'job.json')))['schedule']
        self.assertEqual((prs['enabled'], prs['days'], prs['time']), (True, default['days'], default['time']))
        self.assertEqual(s['schedule'], {'kind': 'launchd', 'applied': False})

    def test_set_job_time(self):
        r = self.cli('set', '--job', 'morning-prs', '--time', '09:15')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.saved()['jobs']['morning-prs']['time'], '09:15')
        self.assertEqual(self.job('morning-prs')['time'], '09:15')

    def test_set_job_days(self):
        self.assertEqual(self.cli('set', '--job', 'morning-prs', '--days', 'mon,wed').returncode, 0)
        self.assertEqual(self.job('morning-prs')['days'], 'mon,wed')

    def test_set_job_enabled(self):
        self.assertEqual(self.cli('set', '--job', 'morning-prs', '--enabled', 'false').returncode, 0)
        self.assertFalse(self.job('morning-prs')['enabled'])
        self.assertFalse(os.path.isdir(os.path.join(self.a['ct_home'], 'jobs', 'morning-prs')), 'the job is no longer installed')
        before = open(self.path, 'rb').read()
        r = self.cli('set', '--job', 'morning-prs', '--enabled', 'true')
        self.assertEqual(r.returncode, 2, 'turning a job back on gives it access again: the user must see it first')
        self.assertIn('gh pr list', r.stderr)
        self.assertEqual(open(self.path, 'rb').read(), before)
        self.assertEqual(self.cli('set', '--job', 'morning-prs', '--enabled', 'true', '--accept-access').returncode, 0)
        self.assertTrue(self.job('morning-prs')['enabled'])

    def test_set_dry_run_shows_the_effect_and_writes_nothing(self):
        before = open(self.path, 'rb').read()
        r = self.cli('set', '--tool', 'code=none', '--dry-run')
        self.assertEqual(r.returncode, 0, r.stderr)
        effect = json.loads(r.stdout)
        self.assertEqual(effect['jobs_removed'], ['morning-prs', 'weekly-wrap'])
        self.assertEqual(effect['jobs_added'], [])
        self.assertEqual(open(self.path, 'rb').read(), before)
        self.cli('set', '--tool', 'code=none')
        effect = json.loads(self.cli('set', '--tool', 'code=github', '--dry-run').stdout)
        self.assertEqual(effect['jobs_added'], ['morning-prs', 'weekly-wrap'])
        self.assertIn(['morning-prs', 'web', 'api.github.com'], effect['new_access'])

    def test_fresh_copy_keeps_the_user_version_in_the_archive(self):
        rel = 'cockpit.md'
        target = os.path.join(self.vault, rel)
        kit = open(target).read()
        open(target, 'w').write('my own cockpit\n')
        r = self.cli('fresh-copy', '--file', rel)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(target).read(), kit)
        archived = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(self.vault, '_system', 'archive')) for f in fs if f == rel]
        self.assertEqual([open(p).read() for p in archived], ['my own cockpit\n'])
        for bad in ('notes/mine.md', '../outside.md', '.control-tower/answers.json'):
            with self.subTest(file=bad):
                self.assertEqual(self.cli('fresh-copy', '--file', bad).returncode, 2)

    def test_access_is_compared_with_what_the_jobs_can_use_today(self):
        sp = os.path.join(self.a['ct_home'], 'jobs', 'morning-prs', 'settings.json')
        st = json.load(open(sp))
        st['permissions']['allow'] = [r for r in st['permissions']['allow'] if not r.startswith('Bash(gh pr list')]
        json.dump(st, open(sp, 'w'))  # as if the kit was updated with a rule the installed job does not have yet
        effect = json.loads(self.cli('set', '--job', 'morning-prs', '--time', '09:00', '--dry-run').stdout)
        self.assertIn(['morning-prs', 'commands', 'gh pr list'], effect['new_access'])
        self.assertEqual(self.cli('set', '--job', 'morning-prs', '--time', '09:00').returncode, 2)
        for change in (['fresh-copy', '--file', 'cockpit.md'], ['grant', '--job', 'weekly-wrap', '--rule', 'mcp__acme__get_issues']):
            with self.subTest(change=change[0]):
                r = self.cli(*change)
                self.assertEqual(r.returncode, 2, 'every change shows access the user has not seen yet')
                self.assertIn('gh pr list', r.stderr)
                self.assertNotIn('get issues', r.stderr, 'what the user just granted is not asked again')
        self.assertEqual(self.cli('fresh-copy', '--file', 'cockpit.md', '--accept-access').returncode, 0)
        self.assertEqual(self.cli('grant', '--job', 'weekly-wrap', '--rule', 'mcp__acme__get_issues').returncode, 0)

    def test_a_failed_fresh_copy_puts_the_user_version_back(self):
        from unittest import mock
        target = os.path.join(self.vault, 'cockpit.md')
        open(target, 'w').write('my own cockpit\n')
        with mock.patch.object(install, 'step_runtime', side_effect=OSError('disk full')), self.assertRaises(OSError):
            install.install(dict(self.saved(), claude_bin='claude'), update=True, fresh=['cockpit.md'], log=lambda *a: None)
        self.assertEqual(open(target).read(), 'my own cockpit\n')

    def test_fresh_copy_of_a_deleted_file_says_nothing_was_archived(self):
        os.remove(os.path.join(self.vault, 'cockpit.md'))
        r = self.cli('fresh-copy', '--file', 'cockpit.md')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('archive', r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.vault, 'cockpit.md')))

    def test_fresh_copy_of_the_next_steps_note_and_not_of_obsidian_settings(self):
        note = os.path.join(self.vault, 'library', 'setup-next-steps.md')
        kit = open(note).read()
        open(note, 'w').write('my notes\n')
        self.assertEqual(self.cli('fresh-copy', '--file', 'library/setup-next-steps.md').returncode, 0)
        self.assertEqual(open(note).read(), kit)
        r = self.cli('fresh-copy', '--file', '.obsidian/app.json')
        self.assertEqual(r.returncode, 2)
        self.assertIn('Obsidian', r.stderr)

    def test_fresh_copy_refuses_a_file_the_kit_no_longer_writes(self):
        self.assertEqual(self.cli('set', '--tool', 'code=none').returncode, 0)
        note = os.path.join(self.vault, '.claude', 'adapters', 'code.md')
        self.assertTrue(os.path.isfile(note), 'an adapter note stays after its tool is dropped')
        r = self.cli('fresh-copy', '--file', '.claude/adapters/code.md')
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn('no longer', r.stderr)
        self.assertTrue(os.path.isfile(note), 'nothing was moved')

    def test_a_granted_read_tool_clears_the_unreachable_tool_warning(self):
        self.assertEqual(self.cli('set', '--tool', 'tracker=jira').returncode, 0)
        report = lambda: install.install(dict(self.saved(), claude_bin='claude'), dry_run=True, log=lambda *a: None)
        self.assertTrue([w for w in report()['warnings'] if w.startswith('tracker/jira')])
        for job in ('morning-prs', 'weekly-wrap'):  # every job that uses the tracker
            self.assertEqual(self.cli('grant', '--job', job, '--rule', 'mcp__atlassian__search').returncode, 0)
        self.assertFalse([w for w in report()['warnings'] if w.startswith('tracker/jira')])

    def test_another_adapter_s_rules_do_not_make_a_server_reachable(self):
        a = answers(self._tmp.name, ['engineering'], tools={'code': 'github', 'errors': 'sentry', 'quality': 'sonarqube', 'logs': 'datadog'})
        warnings = install.install(dict(a, vault_path=os.path.join(self._tmp.name, 'v2')), dry_run=True, log=lambda *x: None)['warnings']
        self.assertTrue([w for w in warnings if w.startswith('errors/sentry')], 'SonarQube and Datadog rules do not reach Sentry')
        self.assertFalse([w for w in warnings if w.startswith('quality/sonarqube')])
        b = answers(self._tmp.name, ['product'], tools={'tracker': 'jira', 'analytics': 'amplitude'},
                    job_permissions={j: ['mcp__Amplitude__get_charts'] for j in ('product-weekly', 'feedback-digest')},
                    vault_path=os.path.join(self._tmp.name, 'v3'))
        warnings = install.install(b, dry_run=True, log=lambda *x: None)['warnings']
        self.assertTrue([w for w in warnings if w.startswith('tracker/jira')], 'a grant on the Amplitude server does not reach Jira')

    def test_a_runtime_only_install_gets_the_commands_not_a_vault_skill(self):
        vault = os.path.join(self._tmp.name, 'own-vault')
        os.makedirs(vault)
        a = answers(self._tmp.name, ['developer'], tools={'code': 'github', 'tracker': 'jira'}, vault_path=vault, vault_mode='runtime')
        warning = next(w for w in install.install(a, dry_run=True, log=lambda *x: None)['warnings'] if w.startswith('tracker/jira'))
        self.assertIn('configure.py grant', warning)
        self.assertNotIn('fix my job', warning)

    def test_the_next_steps_note_names_only_unreachable_tools(self):
        a = dict(self.saved(), tools={'code': 'github', 'tracker': 'jira'})
        self.assertIn('no read tool allowed yet', install.next_steps(install.REPO, a, [], [], (), {('tracker', 'jira')}))
        self.assertNotIn('no read tool allowed yet', install.next_steps(install.REPO, a, [], [], (), set()))

    def test_set_packs(self):
        r = self.cli('set', '--add-pack', 'product')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.show()['packs'], ['developer', 'product'])
        self.assertEqual(self.cli('set', '--remove-pack', 'product').returncode, 0)
        self.assertEqual(self.show()['packs'], ['developer'])

    def test_set_tool(self):
        self.assertEqual(self.cli('set', '--tool', 'code=none').returncode, 0, 'less access needs no consent')
        prs = self.job('morning-prs')
        self.assertFalse(prs['enabled'])
        self.assertEqual(prs['missing'], ['code'])
        r = self.cli('set', '--tool', 'code=github')
        self.assertEqual(r.returncode, 2)
        self.assertIn('api.github.com', r.stderr)
        self.assertEqual(self.cli('set', '--tool', 'code=github', '--accept-access').returncode, 0)
        self.assertTrue(self.job('morning-prs')['enabled'])

    def test_set_schedule(self):
        self.assertEqual(self.cli('set', '--schedule', 'on').returncode, 0)
        self.assertIn('com.control-tower.morning-prs.plist', os.listdir(self.la))
        self.assertTrue(self.show()['schedule']['applied'])
        self.assertEqual(self.cli('set', '--job', 'morning-prs', '--enabled', 'false').returncode, 0)
        self.assertEqual(sorted(os.listdir(self.la)), ['com.control-tower.weekly-wrap.plist'], 'a loaded schedule follows a change')
        r = self.cli('set', '--job', 'weekly-wrap', '--enabled', 'false')
        self.assertEqual(r.returncode, 0, 'no job left to load is not a failure: ' + r.stderr)
        self.assertEqual(os.listdir(self.la), [])
        self.assertEqual(self.cli('set', '--job', 'weekly-wrap', '--enabled', 'true', '--accept-access').returncode, 0)
        self.assertEqual(self.cli('set', '--schedule', 'off').returncode, 0)
        self.assertFalse([f for f in os.listdir(self.la) if f.startswith('com.control-tower.')])
        self.assertFalse(self.show()['schedule']['applied'])

    def test_a_schedule_that_cannot_be_loaded_is_reported(self):
        bin_dir = os.path.join(self._tmp.name, 'bin')
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, 'launchctl'), 'w') as fh:
            fh.write('#!/bin/sh\n[ "$1" = bootstrap ] && echo "Bootstrap failed: 5: Input/output error" >&2 && exit 5\nexit 0\n')
        os.chmod(os.path.join(bin_dir, 'launchctl'), 0o755)
        env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ['PATH'])
        r = subprocess.run([sys.executable, CONFIGURE, 'set', '--schedule', 'on', '--vault', self.vault, '--launch-agents-dir', self.la],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('Bootstrap failed', r.stderr)

    def test_set_schedule_with_cron(self):
        bin_dir, store = os.path.join(self._tmp.name, 'bin'), os.path.join(self._tmp.name, 'crontab.store')
        os.makedirs(bin_dir)
        open(store, 'w').write('')
        with open(os.path.join(bin_dir, 'crontab'), 'w') as fh:
            fh.write(f'#!/bin/sh\nif [ "$1" = "-l" ]; then cat {store}; else cat > {store}; fi\n')
        os.chmod(os.path.join(bin_dir, 'crontab'), 0o755)
        data = self.saved()
        json.dump(dict(data, scheduler='cron'), open(self.path, 'w'))
        env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ['PATH'])
        cli = lambda *a: subprocess.run([sys.executable, CONFIGURE] + list(a) + ['--vault', self.vault], capture_output=True, text=True, env=env)
        self.assertEqual(cli('set', '--schedule', 'on').returncode, 0)
        self.assertIn('--job morning-prs', open(store).read())
        self.assertEqual(cli('set', '--job', 'morning-prs', '--enabled', 'false').returncode, 0)
        r = cli('set', '--job', 'weekly-wrap', '--enabled', 'false')
        self.assertEqual(r.returncode, 0, 'no job left to load is not a failure: ' + r.stderr)
        self.assertNotIn('control-tower', open(store).read())

    def test_another_install_s_agents_are_never_touched(self):
        os.makedirs(self.la)
        other = os.path.join(self._tmp.name, 'other.plist')
        open(other, 'w').write('<plist/>')
        os.symlink(other, os.path.join(self.la, 'com.control-tower.other-job.plist'))
        self.assertFalse(self.show()['schedule']['applied'], 'an agent of another install is not this schedule')
        self.assertEqual(self.cli('set', '--schedule', 'on').returncode, 0)
        self.assertEqual(self.cli('set', '--schedule', 'off').returncode, 0)
        self.assertEqual(sorted(os.listdir(self.la)), ['com.control-tower.other-job.plist'])

    def test_remove_pack_forgets_its_job_settings_and_grants(self):
        self.assertEqual(self.cli('set', '--add-pack', 'product').returncode, 0)
        job = 'product-weekly'
        self.assertEqual(self.cli('set', '--job', job, '--time', '10:00').returncode, 0)
        for j in (job, 'morning-prs'):
            self.assertEqual(self.cli('grant', '--job', j, '--rule', 'Bash(twg jira:*)').returncode, 0)
        self.assertEqual(self.cli('set', '--remove-pack', 'product').returncode, 0)
        data = self.saved()
        self.assertNotIn(job, data.get('jobs', {}))
        self.assertEqual(data['job_permissions'], {'morning-prs': ['Bash(twg jira:*)']})

    def test_enabled_in_any_case(self):
        self.assertEqual(self.cli('set', '--job', 'morning-prs', '--enabled', 'FALSE').returncode, 0)
        self.assertFalse(self.job('morning-prs')['enabled'])

    def test_bad_changes_are_refused_before_writing(self):
        before = open(self.path, 'rb').read()
        for args in (['--job', 'nope', '--time', '09:00'], ['--job', 'morning-prs', '--days', 'funday'],
                     ['--job', 'morning-prs', '--time', '25:00'], ['--job', 'morning-prs', '--enabled', 'maybe'],
                     ['--tool', 'code=jira'], ['--tool', 'nonsense'], ['--add-pack', 'nope'], ['--remove-pack', 'developer'],
                     ['--time', '09:00'], [], ['--remove-pack', 'product']):
            with self.subTest(args=args):
                r = self.cli('set', *args)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertEqual(open(self.path, 'rb').read(), before)

    def test_an_installer_failure_leaves_the_answers_byte_identical(self):
        before = open(self.path, 'rb').read()
        manifest = os.path.join(self.vault, '.control-tower', 'manifest.json')
        os.remove(manifest)
        os.makedirs(manifest)  # the update cannot read the install manifest; the dry run does not need it
        r = self.cli('set', '--job', 'morning-prs', '--time', '09:00')
        self.assertEqual(r.returncode, 1)
        self.assertIn('refused', r.stderr)
        self.assertEqual(open(self.path, 'rb').read(), before)


class ProbeAndChoicesTests(unittest.TestCase):
    """What a job can see (probe, from Claude Code's init message) and long lists asked in pages of 4 (choices)."""
    FIXTURE = os.path.join(ROOT, 'tests', 'e2e', 'fixtures', 'init_message.json')

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.a = answers(self._tmp.name, ['developer'], tools={'code': 'github'})
        install.install(self.a, log=lambda *x: None)
        self.vault, self.ct = self.a['vault_path'], self.a['ct_home']

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, *args, env=None):
        return subprocess.run([sys.executable, CONFIGURE] + list(args), capture_output=True, text=True, env=env)

    def probe_file(self, tools):
        with open(os.path.join(self.ct, 'probe.json'), 'w') as fh:
            json.dump({'servers': [{'name': 'acme', 'status': 'connected'}], 'tools': tools, 'connectors': 0}, fh)

    def choices(self, *args):
        r = self.cli('choices', '--vault', self.vault, *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_probe_reads_the_init_message_of_a_job_run(self):
        sys.path.insert(0, os.path.join(ROOT, 'installer'))
        import configure
        init = json.load(open(self.FIXTURE))
        seen = configure.probe_result(dict(init, mcp_servers=init['mcp_servers'] + [{'name': 'claude.ai Gmail', 'status': 'connected'}],
                                           tools=init['tools'] + ['mcp__claude_ai_Gmail__search_threads']))
        self.assertEqual(seen['servers'], [{'name': 'facts', 'status': 'connected'}])
        self.assertEqual(seen['tools'], ['mcp__facts__create_fact', 'mcp__facts__get_fact'])
        self.assertEqual(seen['connectors'], 1, 'claude.ai connectors are counted, not offered: jobs cannot use them')

    def test_probe_runs_claude_in_the_job_mode_and_saves_what_it_saw(self):
        fake = os.path.join(self._tmp.name, 'fake-claude')
        with open(fake, 'w') as fh:
            fh.write(f'#!/bin/sh\necho "$@" > {self._tmp.name}/argv\ncat {self.FIXTURE} | tr -d "\\n"; echo\n')
        os.chmod(fake, 0o755)
        r = self.cli('probe', '--vault', self.vault, env=dict(os.environ, CT_CLAUDE_BIN=fake))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('mcp__facts__get_fact', json.loads(r.stdout)['tools'])
        self.assertIn('mcp__facts__get_fact', json.load(open(os.path.join(self.ct, 'probe.json')))['tools'])
        argv = open(os.path.join(self._tmp.name, 'argv')).read()
        for flag in ('--setting-sources project', '--permission-mode dontAsk', '--output-format stream-json', '--max-turns 1'):
            self.assertIn(flag, argv)

    def test_probe_starts_only_the_servers_the_user_named(self):
        json.dump({'mcpServers': {'facts': {'command': 'x'}, 'other': {'command': 'y'}}}, open(os.path.join(self.vault, '.mcp.json'), 'w'))
        fake = os.path.join(self._tmp.name, 'fake-claude')
        with open(fake, 'w') as fh:  # keeps the settings it was given
            fh.write(f'#!/bin/sh\nwhile [ "$1" != "--settings" ]; do shift; done\ncp "$2" {self._tmp.name}/settings.json\n'
                     f'cat {self.FIXTURE} | tr -d "\\n"; echo\n')
        os.chmod(fake, 0o755)
        env = dict(os.environ, CT_CLAUDE_BIN=fake)
        self.assertEqual(self.cli('probe', '--vault', self.vault, env=env).returncode, 0)
        self.assertEqual(json.load(open(os.path.join(self._tmp.name, 'settings.json')))['enabledMcpjsonServers'], [])
        self.assertEqual(self.cli('probe', '--vault', self.vault, '--server', 'facts', env=env).returncode, 0)
        self.assertEqual(json.load(open(os.path.join(self._tmp.name, 'settings.json')))['enabledMcpjsonServers'], ['facts'])
        self.assertEqual(self.cli('probe', '--vault', self.vault, '--server', 'nope', env=env).returncode, 2)

    def test_read_tools_in_pages_of_four(self):
        for n, pages in ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 2), (13, 4)):
            with self.subTest(read_tools=n):
                self.probe_file([f'mcp__acme__get_thing_{i}' for i in range(n)] + ['mcp__acme__create_issue'])
                c = self.choices('--kind', 'read-tools', '--server', 'acme')
                self.assertEqual(len(c['items']), n)
                self.assertEqual(len(c['pages']), pages)
                self.assertTrue(all(2 <= len(p) <= 4 for p in c['pages']), c['pages'])
                if n == 0:
                    self.assertIsNone(c['first'], 'nothing to ask')
                elif n == 1:
                    self.assertEqual(c['first']['options'], c['items'] + ['None'])
                elif n <= 4:
                    self.assertTrue(c['first']['multi_select'])
                    self.assertEqual(c['first']['options'], c['items'])
                else:
                    self.assertEqual(c['first']['options'], [f'All {n} read tools (recommended)', 'Let me choose', 'None'])
                self.assertEqual(c['never'], ['mcp__acme__create_issue'])

    def test_an_action_tool_is_never_an_option(self):
        self.probe_file(['mcp__acme__create_issue', 'mcp__acme__get_issue', 'mcp__acme__search_issues', 'mcp__acme__send_message'])
        c = self.choices('--kind', 'read-tools', '--server', 'acme')
        self.assertEqual(c['items'], ['mcp__acme__get_issue', 'mcp__acme__search_issues'])
        self.assertEqual(c['never'], ['mcp__acme__create_issue', 'mcp__acme__send_message'])
        self.assertNotIn('create_issue', json.dumps(c['first']) + json.dumps(c['pages']))

    def test_connections_reports_and_any_list(self):
        c = self.choices('--kind', 'connections')
        self.assertEqual(c['items'], ['my notes', 'code: github'])
        c = self.choices('--kind', 'reports')
        self.assertEqual((c['items'], c['first']['options']), (['a new report'], ['a new report', 'None']))
        r = self.cli('choices', '--items', 'a', 'b', 'c', 'd', 'e', 'f')
        c = json.loads(r.stdout)
        self.assertEqual(c['first']['options'], ['All 6 (recommended)', 'Let me choose', 'None'])
        self.assertEqual(c['pages'], [['a', 'b', 'c'], ['d', 'e', 'f']])
        self.assertNotEqual(self.cli('choices', '--vault', self.vault, '--kind', 'read-tools').returncode, 0, 'read tools need --server')
        r = self.cli('choices', '--vault', self.vault, '--kind', 'read-tools', '--server', 'unprobed')
        self.assertEqual(r.returncode, 2, 'a server the probe did not start is not a server without read tools')
        self.assertIn('configure.py probe --server unprobed', r.stderr)
        c = json.loads(self.cli('choices', '--items', 'a', 'b', 'c', 'd', 'e', '--recommended', 'none').stdout)
        self.assertEqual((c['first']['options'][0], c['recommended']), ('All 5', []))


if __name__ == '__main__':
    unittest.main()
