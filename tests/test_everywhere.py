"""/control-tower in every Claude session (`"everywhere": true`): a personal skill that sends any session to the vault's own
/control-tower, written only after the user's yes, never over a personal skill of the user's, and removed by the uninstaller.
Temporary folders only: CLAUDE_CONFIG_DIR points Claude Code's personal folder at a temporary one."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
import install  # noqa: E402

CONFIGURE = os.path.join(ROOT, 'installer', 'configure.py')
UNINSTALL = os.path.join(ROOT, 'installer', 'uninstall.py')


class EverywhereTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = self._tmp.name
        self.config = os.path.join(t, 'claude-config')
        self._env = os.environ.get('CLAUDE_CONFIG_DIR')
        os.environ['CLAUDE_CONFIG_DIR'] = self.config
        self.skill = os.path.join(self.config, 'skills', 'control-tower', 'SKILL.md')
        self.a = {'owner_name': 'Sam Rivera', 'owner_handle': 'sam', 'timezone': 'UTC', 'vault_path': os.path.join(t, 'vault'),
                  'ct_home': os.path.join(t, 'ct'), 'packs': ['marketing'], 'tools': {}, 'scheduler': 'none'}

    def tearDown(self):
        if self._env is None:
            os.environ.pop('CLAUDE_CONFIG_DIR', None)
        else:
            os.environ['CLAUDE_CONFIG_DIR'] = self._env
        self._tmp.cleanup()

    def read(self):
        with open(self.skill, encoding='utf-8') as fh:
            return fh.read()

    def test_only_after_a_yes(self):
        install.install(self.a, log=lambda *x: None)
        self.assertFalse(os.path.exists(self.skill), 'an answers file without "everywhere" writes nothing outside the vault')
        report = install.install(dict(self.a, everywhere=True), log=lambda *x: None)
        text = self.read()
        self.assertIn('name: control-tower', text)
        self.assertIn('## Check my setup', text, 'the hub\'s text, from the kit: a synced vault is never followed in every session')
        self.assertIn(f'"this vault" is `{self.a["vault_path"]}`', text)
        self.assertIn(f'the runtime folder (`ct_home`) is `{self.a["ct_home"]}`: use these, never the ones in the vault\'s manifest', text)
        self.assertIn('another control tower vault', text, 'in another vault\'s session, that vault\'s own /control-tower')
        self.assertIn('/mcp', text, 'signing in to a tool needs a session on the vault')
        self.assertNotIn('hello control tower", or asks', text, 'it starts only when asked for by name')
        self.assertEqual(report['everywhere'], self.skill)
        install.install(dict(self.a, everywhere=False), log=lambda *x: None)
        self.assertFalse(os.path.exists(self.skill), 'turned off: the shortcut goes')

    def test_never_over_a_skill_of_the_user_s(self):
        os.makedirs(os.path.dirname(self.skill))
        with open(self.skill, 'w') as fh:
            fh.write('---\nname: control-tower\n---\nMy own.\n')
        report = install.install(dict(self.a, everywhere=True), log=lambda *x: None)
        self.assertEqual(self.read(), '---\nname: control-tower\n---\nMy own.\n')
        self.assertTrue(any('a personal skill of yours' in w and 'kept' in w for w in report['warnings']), report['warnings'])
        doctor = subprocess.run([sys.executable, os.path.join(ROOT, 'installer', 'doctor.py'), '--vault', self.a['vault_path'], '--ct-home',
                                 self.a['ct_home']], capture_output=True, text=True, env=dict(os.environ)).stdout
        self.assertIn('[warn] /control-tower everywhere', doctor)
        install.install(dict(self.a, everywhere=False), log=lambda *x: None)
        self.assertTrue(os.path.exists(self.skill), 'and never removed')

    def test_an_edited_copy_or_another_install_s_is_never_replaced(self):
        install.install(dict(self.a, everywhere=True), log=lambda *x: None)
        with open(self.skill, 'a') as fh:
            fh.write('\nMy note.\n')
        report = install.install(dict(self.a, everywhere=True), log=lambda *x: None)
        self.assertIn('My note.', self.read())
        self.assertTrue(any('your edited copy' in w for w in report['warnings']), report['warnings'])
        install.install(dict(self.a, everywhere=False), log=lambda *x: None)
        self.assertTrue(os.path.exists(self.skill), 'an edited copy is the user\'s')
        other = dict(self.a, vault_path=os.path.join(self._tmp.name, 'vault2'), ct_home=os.path.join(self._tmp.name, 'ct2'), everywhere=True)
        report = install.install(other, log=lambda *x: None)
        self.assertTrue(any('your edited copy' in w or 'another control tower install' in w for w in report['warnings']), report['warnings'])
        self.assertIn('My note.', self.read())

    def test_removed_where_it_was_written(self):
        install.install(dict(self.a, everywhere=True), log=lambda *x: None)
        os.environ['CLAUDE_CONFIG_DIR'] = os.path.join(self._tmp.name, 'elsewhere')
        install.install(dict(self.a, everywhere=False), log=lambda *x: None)
        self.assertFalse(os.path.exists(self.skill), 'the path recorded at install, not the one of today')
        os.environ['CLAUDE_CONFIG_DIR'] = self.config
        install.install(dict(self.a, everywhere=True), log=lambda *x: None)
        os.environ['CLAUDE_CONFIG_DIR'] = os.path.join(self._tmp.name, 'elsewhere')
        install.install(dict(self.a, everywhere=True), log=lambda *x: None)
        self.assertFalse(os.path.exists(self.skill), 'Claude\'s folder moved: one shortcut, at the new place')
        self.assertTrue(os.path.exists(os.path.join(self._tmp.name, 'elsewhere', 'skills', 'control-tower', 'SKILL.md')))

    def test_set_through_configure_and_removed_by_the_uninstaller(self):
        install.install(self.a, log=lambda *x: None)
        r = subprocess.run([sys.executable, CONFIGURE, 'set', '--vault', self.a['vault_path'], '--everywhere', 'on'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(self.skill))
        cmd = [sys.executable, UNINSTALL, '--ct-home', self.a['ct_home'], '--vault', self.a['vault_path'], '--launch-agents-dir',
               os.path.join(self._tmp.name, 'la'), '--no-launchctl']
        self.assertIn(f'would remove-file: {self.skill}', subprocess.run(cmd, capture_output=True, text=True).stdout)
        r = subprocess.run(cmd + ['--yes'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.skill))

    def test_validated(self):
        for bad in ({'everywhere': 'yes'}, {'vault_path': self.a['vault_path'] + '`x'}, {'ct_home': self.a['ct_home'] + '-->x'},
                    {'vault_path': self.a['vault_path'] + '\tx'}):
            with self.subTest(bad), self.assertRaises(install.InstallError):
                install.install(dict(self.a, **bad), dry_run=True, log=lambda *x: None)


if __name__ == '__main__':
    unittest.main()
