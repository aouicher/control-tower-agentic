"""Uninstalling from the vault (`uninstall.py`) in the levels `/control-tower` offers: stop the automatic runs only, or remove
the kit and keep every note; and, on separate answers, the tool connections Claude added for the user and the kit's own
folder. Temporary folders only; the schedule is linked in a temporary folder and never loaded."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import install  # noqa: E402
from plan import fingerprint  # noqa: E402
from test_installer import answers_for  # noqa: E402
from test_update import GIT, git, kit_repo  # noqa: E402


class UninstallLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._seed_tmp = tempfile.TemporaryDirectory()
        cls.seed = os.path.join(cls._seed_tmp.name, 'seed')
        kit_repo(cls.seed)

    @classmethod
    def tearDownClass(cls):
        cls._seed_tmp.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = self._tmp.name
        self.la = os.path.join(t, 'LaunchAgents')
        a = answers_for(t, ['developer'])
        install.install(a, schedule='load', launch_agents_dir=self.la, no_launchctl=True, log=lambda *x: None)
        self.vault, self.ct = a['vault_path'], a['ct_home']
        self.calls, fake = os.path.join(t, 'calls'), os.path.join(t, 'claude')
        with open(fake, 'w') as fh:  # records where it ran and its arguments
            fh.write(f'#!/bin/sh\necho "$(pwd -P) $*" >> {self.calls}\n')
        os.chmod(fake, 0o755)
        self.env = dict(os.environ, CT_CLAUDE_BIN=fake)

    def tearDown(self):
        self._tmp.cleanup()

    def uninstall(self, *args, repo=ROOT, vault=None):
        return subprocess.run([sys.executable, os.path.join(repo, 'installer', 'uninstall.py'), '--ct-home', self.ct, '--vault', vault or self.vault,
                               '--launch-agents-dir', self.la, '--no-launchctl'] + list(args), capture_output=True, text=True, env=self.env)

    def connections(self, added):
        """The vault's servers: `amp` and `changed` as Claude added them, `changed` edited since, `mine` the user's own."""
        servers = {'amp': {'type': 'http', 'url': 'https://mcp.amplitude.com/mcp'}, 'changed': {'command': 'old'}, 'mine': {'command': 'mine'}}
        with open(os.path.join(self.vault, '.mcp.json'), 'w') as fh:
            json.dump({'mcpServers': dict(servers, changed={'command': 'new'})}, fh)
        path = os.path.join(self.vault, '.control-tower', 'answers.json')
        with open(path) as fh:
            data = json.load(fh)
        data.update(connections_added=added, fingerprints={n: fingerprint(e) for n, e in servers.items()})
        with open(path, 'w') as fh:
            json.dump(data, fh)

    def test_stopping_the_automatic_runs_keeps_everything_else(self):
        self.assertTrue(install.own_agents(self.la, os.path.join(self.ct, 'schedule')))
        dry = self.uninstall('--schedule-only')
        self.assertIn('would unload', dry.stdout)
        self.assertNotIn('rmtree', dry.stdout)
        r = self.uninstall('--schedule-only', '--yes')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(install.own_agents(self.la, os.path.join(self.ct, 'schedule')), [])
        self.assertTrue(os.path.isfile(os.path.join(self.ct, 'install.json')), 'the runtime stays')
        self.assertTrue(os.path.isfile(os.path.join(self.vault, 'cockpit.md')), 'the vault stays')
        self.assertEqual(self.uninstall('--schedule-only', '--remove-vault-files').returncode, 2, 'one level at a time')

    def test_only_the_connections_claude_added_and_nobody_changed_are_removed(self):
        self.connections(['amp', 'changed', 'gone'])
        edited, mine = os.path.join(self.vault, 'CLAUDE.md'), os.path.join(self.vault, 'work', 'projects', 'my-note.md')
        with open(edited, 'a', encoding='utf-8') as fh:
            fh.write('\nMy rule.\n')
        with open(mine, 'w', encoding='utf-8') as fh:
            fh.write('# mine\n')
        dry = self.uninstall('--remove-vault-files', '--remove-connections')
        self.assertIn('would remove-connection: amp', dry.stdout)
        self.assertFalse(os.path.exists(self.calls), 'a dry run calls nothing')
        r = self.uninstall('--remove-vault-files', '--remove-connections', '--yes')
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.calls) as fh:
            self.assertEqual(fh.read().splitlines(), [f'{os.path.realpath(self.vault)} mcp remove --scope project -- amp'])
        self.assertIn('keep-connection: changed', r.stdout, 'changed since it was added: the user decides')
        self.assertTrue(os.path.isfile(edited) and os.path.isfile(mine), 'notes the user edited or wrote are never removed')
        self.assertFalse(os.path.exists(self.ct))

    def test_connections_stay_unless_asked_for(self):
        self.connections(['amp'])
        self.assertEqual(self.uninstall('--remove-vault-files', '--yes').returncode, 0)
        self.assertFalse(os.path.exists(self.calls))

    def kit(self, name='kit'):
        kit = os.path.join(self._tmp.name, name)
        subprocess.run(GIT + ['clone', '-q', self.seed, kit], check=True, capture_output=True)
        return kit

    def other_install(self, kit):
        """A second vault installed from `kit` whose automatic runs are loaded (its launchd agent)."""
        home, vault = os.path.join(self._tmp.name, 'ct2'), os.path.join(self._tmp.name, 'vault2')
        os.makedirs(os.path.join(vault, '.control-tower'), exist_ok=True)
        os.makedirs(os.path.join(home, 'schedule', 'launchd'), exist_ok=True)
        for path, data in ((os.path.join(home, 'install.json'), {'vault': vault}), (os.path.join(vault, '.control-tower', 'manifest.json'), {'repo': kit})):
            with open(path, 'w') as fh:
                json.dump(data, fh)
        link = os.path.join(self.la, 'com.control-tower.other.plist')
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(os.path.join(home, 'schedule', 'launchd', 'com.control-tower.other.plist'), link)

    def test_the_kit_folder_goes_only_when_its_origin_holds_everything_in_it(self):
        def write(kit, rel, text='mine'):
            with open(os.path.join(kit, rel), 'a') as fh:
                fh.write(text)
        os.makedirs(self.la, exist_ok=True)
        cases = {
            'an untracked file': lambda kit: write(kit, 'notes.txt'),
            'an ignored file': lambda kit: write(kit, '.denylist.local'),
            'an edited file': lambda kit: write(kit, 'README.md'),
            'a local commit': lambda kit: git(kit, 'commit', '-q', '--allow-empty', '-m', 'mine'),
            'a branch never pushed': lambda kit: (git(kit, 'checkout', '-q', '-b', 'side'), git(kit, 'commit', '-q', '--allow-empty', '-m', 'side'),
                                                  git(kit, 'checkout', '-q', 'main')),
            'a stash': lambda kit: (write(kit, 'README.md'), git(kit, 'stash', '-q')),
            'a worktree inside it': lambda kit: git(kit, 'worktree', 'add', '-q', os.path.join(kit, '.claude', 'worktrees', 'w'), '-b', 'w'),
            'no origin': lambda kit: git(kit, 'remote', 'remove', 'origin'),
            'an origin it cannot reach': lambda kit: git(kit, 'remote', 'set-url', 'origin', 'https://someone:pw-not-shown@127.0.0.1:1/kit.git'),
            'not a checkout': lambda kit: shutil.rmtree(os.path.join(kit, '.git')),
            'a detached HEAD with its own commit': lambda kit: (git(kit, 'checkout', '-q', '--detach'),
                                                                git(kit, 'commit', '-q', '--allow-empty', '-m', 'detached')),
            'a merge in progress': lambda kit: write(os.path.join(kit, '.git'), 'MERGE_HEAD', git(kit, 'rev-parse', 'HEAD')),
            'another vault from it that runs automatically': lambda kit: self.other_install(kit),
            'another runtime whose vault is not there': lambda kit: (self.other_install(kit),
                                                                     shutil.rmtree(os.path.join(self._tmp.name, 'vault2'))),
        }
        for case, make in cases.items():
            with self.subTest(case):
                kit = self.kit(case.replace(' ', '-').replace("'", ''))
                make(kit)
                r = self.uninstall('--remove-vault-files', '--remove-kit', '--yes', repo=kit)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertNotIn('pw-not-shown', r.stdout + r.stderr, 'never a credential from the address')
                self.assertTrue(os.path.isdir(kit) and os.path.isdir(self.ct), 'refused before anything is removed')
                if os.path.lexists(os.path.join(self.la, 'com.control-tower.other.plist')):
                    os.remove(os.path.join(self.la, 'com.control-tower.other.plist'))
        kit = self.kit()
        self.other_install(os.path.join(self._tmp.name, 'another-kit'))  # a vault from another clone of the kit never holds this one
        self.assertEqual(self.uninstall('--schedule-only', '--remove-kit', '--yes', repo=kit).returncode, 2, 'the kit goes with the runtime')
        r = subprocess.run([sys.executable, os.path.join(kit, 'installer', 'uninstall.py'), '--ct-home', self.ct, '--remove-kit', '--yes'],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 2, 'never without the vault, which it must not hold')
        self.assertEqual(self.uninstall('--remove-kit', '--yes', repo=kit, vault=os.path.join(kit, 'tests', '.work', 'vault')).returncode, 2,
                         'a kit that holds the vault')
        self.assertIn(f'would remove-kit: {kit}', self.uninstall('--remove-vault-files', '--remove-kit', repo=kit).stdout)
        r = self.uninstall('--remove-vault-files', '--remove-kit', '--yes', repo=kit)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(kit))
        self.assertTrue(os.path.isdir(self.vault))

    def test_damaged_answers_or_manifest_never_block_the_uninstall(self):
        for name in ('answers.json', 'manifest.json'):
            with open(os.path.join(self.vault, '.control-tower', name), 'w') as fh:
                fh.write('{not json')
        r = self.uninstall('--remove-vault-files', '--remove-connections', '--yes')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('no connection is removed', r.stderr)
        self.assertIn('no vault file is removed', r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.vault, 'cockpit.md')))
        self.assertFalse(os.path.exists(self.calls))

if __name__ == '__main__':
    unittest.main()
