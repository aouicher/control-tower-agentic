"""The user's own scheduled skills (`my_jobs` in the answers): one generic prompt that reads the skill, the read tools of the
connections and known tools it uses, and the same schedule, doctor and uninstall as pack jobs. Temporary folders only; the
schedule is written for launchd in a temporary folder and never loaded."""
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
SKILL = '---\nname: {name}\ndescription: A digest of my notes.\n---\n\n# Digest\n\nSummarise the notes of the week.\n'


class VaultCase(unittest.TestCase):
    """An installed developer vault, scheduled for launchd in a temporary folder, with a skill `digest`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.la = os.path.join(self._tmp.name, 'LaunchAgents')
        self.a = answers(self._tmp.name, ['developer'], tools={'code': 'github'}, scheduler='launchd')
        install.install(self.a, log=lambda *x: None)
        self.vault, self.ct = self.a['vault_path'], self.a['ct_home']
        self.skill('digest')

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, CONFIGURE] + list(args) + ['--vault', self.vault, '--launch-agents-dir', self.la,
                                                                          '--no-launchctl'], capture_output=True, text=True)

    def skill(self, name, text=None):
        d = os.path.join(self.vault, '.claude', 'skills', name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'SKILL.md'), 'w', encoding='utf-8') as fh:
            fh.write(text if text is not None else SKILL.format(name=name))

    def saved(self):
        return json.load(open(os.path.join(self.vault, '.control-tower', 'answers.json')))

    def job_file(self, job, name):
        return os.path.join(self.ct, 'jobs', job, name)

    def allow(self, job):
        return set(json.load(open(self.job_file(job, 'settings.json')))['permissions']['allow'])

    def mail_connection(self):
        with open(os.path.join(self.vault, '.mcp.json'), 'w') as fh:
            json.dump({'mcpServers': {'mailbox': {'type': 'http', 'url': 'https://mcp.example.com/mcp'}}}, fh)
        with open(os.path.join(self.ct, 'probe.json'), 'w') as fh:
            json.dump({'servers': [{'name': 'mailbox', 'status': 'connected'}], 'tools': ['mcp__mailbox__search_threads'],
                       'connectors': 0}, fh)
        r = self.cli('add-connection', '--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox__search_threads',
                     '--accept-access')
        self.assertEqual(r.returncode, 0, r.stderr)


class MyJobTests(VaultCase):
    def test_a_scheduled_skill_is_a_job_like_any_other(self):
        self.mail_connection()
        r = self.cli('add-job', '--skill', 'digest', '--uses', 'mail', '--days', 'mon', '--time', '07:30', '--accept-access')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.saved()['my_jobs'], {'digest': {'skill': 'digest', 'uses': ['mail']}})
        self.assertEqual(self.saved()['jobs']['digest'], {'days': 'mon', 'time': '07:30'}, 'when it runs is where every job keeps it')
        prompt = open(self.job_file('digest', 'prompt.md'), encoding='utf-8').read()
        self.assertIn('.claude/skills/digest/SKILL.md', prompt)
        self.assertIn('journal/reports/my-digest-YYYY-MM-DD.md', prompt)
        self.assertNotIn('{{', prompt)
        self.assertEqual(self.cli('add-job', '--skill', 'digest', '--id', 'plain', '--accept-access').returncode, 0)
        self.assertEqual(self.allow('digest') - self.allow('plain'), {'mcp__mailbox__search_threads'},
                         'the read tools of what it uses, and nothing else')
        self.assertEqual(list(json.load(open(self.job_file('digest', 'mcp.json')))['mcpServers']), ['mailbox'])
        self.assertEqual(json.load(open(self.job_file('plain', 'mcp.json')))['mcpServers'], {})
        self.assertNotIn('Skill', self.allow('digest'))
        plist = os.path.join(self.ct, 'schedule', 'launchd', 'com.control-tower.digest.plist')
        self.assertTrue(os.path.isfile(plist))
        show = json.loads(self.cli('show').stdout)
        self.assertEqual(next(j for j in show['jobs'] if j['id'] == 'digest')['time'], '07:30')
        import doctor
        self.assertFalse([i for i in doctor.check(self.vault, self.ct, 'python3').items if i['level'] == 'FAIL'])
        os.remove(os.path.join(self.vault, '.claude', 'skills', 'digest', 'SKILL.md'))
        self.assertTrue([i for i in doctor.check(self.vault, self.ct, 'python3').items if i['check'] == 'job digest' and i['level'] == 'warn'])
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'installer', 'uninstall.py'), '--ct-home', self.ct, '--vault', self.vault,
                            '--launch-agents-dir', self.la, '--no-launchctl', '--yes'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.job_file('digest', 'prompt.md')))

    def test_a_known_tool_is_a_source_too(self):
        self.assertEqual(self.cli('add-job', '--skill', 'digest', '--uses', 'code', '--accept-access').returncode, 0)
        self.assertTrue(any(r.startswith('Bash(gh pr list') for r in self.allow('digest')))
        r = self.cli('add-job', '--skill', 'digest', '--id', 'other', '--uses', 'tracker', '--accept-access')
        self.assertEqual(r.returncode, 0, 'a capability with no tool chosen: the job is kept, off')
        self.assertFalse(os.path.exists(self.job_file('other', 'prompt.md')))

    def test_check_skill(self):
        self.assertEqual(self.cli('check-skill', '--skill', 'digest').returncode, 0)
        bad = {'grants tools': '---\nname: x\ndescription: d\nallowed-tools: Bash\n---\n',
               'an unknown key': '---\nname: x\ndescription: d\nmodel: opus\n---\n',
               'no frontmatter': '# x\n',
               'a date command without the Run context': SKILL.format(name='x') + '\nGet the date with `date +%F`.\n'}
        for why, text in bad.items():
            with self.subTest(why):
                self.skill('x', text)
                self.assertEqual(self.cli('check-skill', '--skill', 'x').returncode, 2)
                self.assertEqual(self.cli('add-job', '--skill', 'x', '--accept-access').returncode, 2)
        self.skill('x', SKILL.format(name='x') + '\nGet the date with `date +%F`. If there is a Run context, use it.\n')
        self.assertEqual(self.cli('check-skill', '--skill', 'x').returncode, 2, 'the Run context comes first')
        self.skill('x', SKILL.format(name='x') + '\nIf there is a Run context, use it; otherwise run `date +%F`.\n')
        self.assertEqual(self.cli('check-skill', '--skill', 'x').returncode, 0)
        self.assertEqual(self.cli('check-skill', '--skill', 'missing').returncode, 2)
        self.assertEqual(self.cli('check-skill', '--skill', '../etc').returncode, 2)

    def test_refused_jobs(self):
        cases = {'a pack job id': ['--skill', 'digest', '--id', 'morning-prs'],
                 'an unknown source': ['--skill', 'digest', '--uses', 'nothing-like-it'],
                 'a bad time': ['--skill', 'digest', '--time', '25:00'],
                 'bad days': ['--skill', 'digest', '--days', 'someday'],
                 'a bad id': ['--skill', 'digest', '--id', 'My Report']}
        for why, args in cases.items():
            with self.subTest(why):
                r = self.cli('add-job', *args, '--accept-access')
                self.assertEqual(r.returncode, 2, f'{why}: {r.stdout}')
        dry = json.loads(self.cli('add-job', '--skill', 'digest', '--dry-run').stdout)
        self.assertIn(['digest', 'job', 'runs on its schedule'], dry['new_access'], 'a new unattended run needs a yes')
        self.assertEqual(self.cli('add-job', '--skill', 'digest').returncode, 2)
        self.assertEqual(self.cli('add-job', '--skill', 'digest', '--accept-access').returncode, 0)
        self.assertEqual(self.cli('add-job', '--skill', 'digest', '--accept-access').returncode, 2, 'already scheduled')

    def test_sources_of_a_report_and_removing_it(self):
        self.mail_connection()
        self.assertEqual(self.cli('add-job', '--skill', 'digest', '--accept-access').returncode, 0)
        self.assertEqual(self.cli('set', '--job', 'digest', '--uses', 'mail', '--accept-access').returncode, 0)
        self.assertIn('mcp__mailbox__search_threads', self.allow('digest'))
        r = self.cli('remove-connection', '--id', 'mail')
        self.assertEqual(r.returncode, 2)
        self.assertIn('digest', r.stderr)
        self.assertEqual(self.cli('set', '--job', 'morning-prs', '--uses', 'mail').returncode, 2, 'pack jobs do not take sources')
        self.assertEqual(self.cli('grant', '--job', 'digest', '--rule', 'WebFetch(domain:example.com)', '--accept-access').returncode, 0)
        self.assertEqual(self.cli('remove-job', '--id', 'digest').returncode, 0)
        saved = self.saved()
        for key in ('my_jobs', 'jobs', 'job_permissions'):
            self.assertNotIn('digest', saved.get(key, {}))
        self.assertFalse(os.path.exists(self.job_file('digest', 'prompt.md')))
        self.assertEqual(self.cli('remove-connection', '--id', 'mail').returncode, 0)

    def test_your_reports_never_share_a_file_with_a_pack_report(self):
        from test_private_packs import private_pack
        pd = private_pack(os.path.join(self._tmp.name, 'outside'))
        job = os.path.join(pd, 'jobs', 'acme-brief', 'job.json')
        meta = json.load(open(job))
        meta['outputs'] = ['journal/reports/my-digest-YYYY-MM-DD.md']
        with open(job, 'w') as fh:
            json.dump(meta, fh)
        with self.assertRaises(install.InstallError):
            install.install(answers(self._tmp.name, ['acme-private'], [pd], vault_path=os.path.join(self._tmp.name, 'v2')),
                            dry_run=True, log=lambda *x: None)
        for path in __import__('glob').glob(os.path.join(ROOT, 'packs', '*', 'jobs', '*', '*')):
            with self.subTest(path=os.path.relpath(path, ROOT)):
                self.assertNotIn('journal/reports/my-', open(path, encoding='utf-8').read())

    def test_the_installer_refuses_a_bad_record(self):
        good = {'skill': 'digest', 'uses': []}
        for bad in ({'Bad Id': good}, {'x': dict(good, skill='../x')}, {'x': dict(good, time='08:00')}, {'x': dict(good, uses=['nope'])},
                    {'x': dict(good, uses=[['code']])}, {'x': dict(good, extra=1)}, {'x': dict(good, model='gpt')}, {'x': 'digest'},
                    {'morning-prs': good}):
            with self.subTest(bad=bad):
                with self.assertRaises(install.InstallError):
                    install.install(dict(self.a, my_jobs=bad), dry_run=True, log=lambda *x: None)


class CloudReportTests(VaultCase):
    """A report that runs on claude.ai as a cloud routine: rendered from the same prompt, listed for the routine flow, never
    scheduled on this computer. claude.ai connectors (which jobs on this computer cannot use) are its sources."""

    def routines(self):
        return {r['key']: r for r in json.load(open(os.path.join(self.ct, 'routines', 'routines.json')))}

    def test_a_cloud_report_is_a_routine_with_its_connectors(self):
        self.assertEqual(self.cli('add-connection', '--id', 'gmail', '--connector', 'Gmail', '--accept-access').returncode, 0)
        r = self.cli('add-job', '--skill', 'digest', '--runs-on', 'cloud', '--uses', 'gmail', 'code', '--days', 'mon', '--time', '07:00',
                     '--accept-access')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.saved()['my_jobs']['digest'], {'skill': 'digest', 'uses': ['code', 'gmail'], 'runs_on': 'cloud'})
        entry = self.routines()['my--digest']
        self.assertEqual(entry['connectors_required'], {'code': 'github', 'gmail': 'Gmail'})
        self.assertEqual((entry['days'], entry['time'], entry['vault']), ('mon', '07:00', 'write'))
        prompt = open(entry['prompt_file'], encoding='utf-8').read()
        self.assertIn('.claude/skills/digest/SKILL.md', prompt)
        self.assertIn('journal/reports/my-digest-YYYY-MM-DD.md', prompt)
        self.assertIn('git add -- ', prompt, 'a routine on a vault repository commits its note only, then pushes it')
        self.assertNotIn('Run context', prompt, 'no runner on claude.ai writes one')
        self.assertNotIn('{{', prompt)
        self.assertFalse(os.path.exists(os.path.join(self.ct, 'jobs', 'digest')), 'nothing runs it on this computer')
        self.assertFalse(os.path.exists(os.path.join(self.ct, 'schedule', 'launchd', 'com.control-tower.digest.plist')))
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'installer', 'uninstall.py'), '--ct-home', self.ct, '--vault', self.vault,
                            '--launch-agents-dir', self.la, '--no-launchctl'], capture_output=True, text=True)
        self.assertIn('delete on claude.ai', r.stdout)
        self.assertIn('Your report digest', r.stdout)

    def test_a_computer_report_is_unchanged_and_sources_match_where_it_runs(self):
        self.assertEqual(self.cli('add-connection', '--id', 'gmail', '--connector', 'Gmail', '--accept-access').returncode, 0)
        r = self.cli('add-job', '--skill', 'digest', '--uses', 'gmail', '--accept-access')
        self.assertEqual(r.returncode, 2, 'a claude.ai connector cannot be used by a report on this computer')
        self.assertIn('gmail', r.stderr)
        self.assertEqual(self.cli('add-job', '--skill', 'digest', '--accept-access').returncode, 0)
        self.assertNotIn('my--digest', self.routines() if os.path.exists(os.path.join(self.ct, 'routines', 'routines.json')) else {})
        self.assertTrue(os.path.isfile(os.path.join(self.ct, 'jobs', 'digest', 'prompt.md')))
        self.mail_connection()
        r = self.cli('add-job', '--skill', 'digest', '--id', 'cloudy', '--runs-on', 'cloud', '--uses', 'mail', '--accept-access')
        self.assertEqual(r.returncode, 2, "a routine on claude.ai cannot reach this computer's MCP servers")

    def test_a_stopped_or_removed_cloud_report_leaves_no_routine(self):
        self.assertEqual(self.cli('add-job', '--skill', 'digest', '--runs-on', 'cloud', '--accept-access').returncode, 0)
        self.assertIn('my--digest', self.routines())
        r = self.cli('set', '--job', 'digest', '--enabled', 'false')
        self.assertEqual(r.returncode, 0)
        self.assertIn('still runs on claude.ai', r.stdout, 'the routine is the user\'s: they pause it there')
        self.assertNotIn('my--digest', self.routines(), 'a report turned off is not offered as a routine')
        self.assertEqual(self.cli('set', '--job', 'digest', '--enabled', 'true', '--accept-access').returncode, 0)
        r = self.cli('remove-job', '--id', 'digest')
        self.assertEqual(r.returncode, 0)
        self.assertIn('still runs on claude.ai', r.stdout)
        self.assertNotIn('my--digest', self.routines())
        self.assertFalse(os.path.exists(os.path.join(self.ct, 'routines', 'my--digest.prompt.md')))

    def test_refused_records(self):
        r = self.cli('add-connection', '--id', 'g', '--connector', 'Gmail', '--read-tools', 'mcp__g__get', '--accept-access')
        self.assertEqual(r.returncode, 2, "a connector's tools are chosen on claude.ai")
        for bad in ({'g': {'connector': 'Gmail', 'read_tools': ['x']}}, {'g': {'connector': 'Gm<ail>'}}, {'g': {'connector': ''}},
                    {'g': {'connector': 'Gmail', 'server': 's'}}):
            with self.subTest(bad=bad):
                with self.assertRaises(install.InstallError):
                    install.install(dict(self.a, connections=bad), dry_run=True, log=lambda *x: None)
        for bad in ({'skill': 'digest', 'runs_on': 'moon'}, {'skill': 'digest', 'runs_on': 'cloud', 'model': 'opus'}):
            with self.subTest(bad=bad):
                with self.assertRaises(install.InstallError):
                    install.install(dict(self.a, my_jobs={'digest': bad}), dry_run=True, log=lambda *x: None)
        from test_private_packs import private_pack
        pd = private_pack(os.path.join(self._tmp.name, 'outside'), pid='my')
        with self.assertRaises(install.InstallError):
            install.install(answers(self._tmp.name, ['my'], [pd], vault_path=os.path.join(self._tmp.name, 'v2')), dry_run=True,
                            log=lambda *x: None)


if __name__ == '__main__':
    unittest.main()
