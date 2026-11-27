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
        data = self.saved()
        data['job_permissions'] = {job: ['Bash(twg jira:*)'], 'morning-prs': ['Bash(twg jira:*)']}
        json.dump(data, open(self.path, 'w'))
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


if __name__ == '__main__':
    unittest.main()
