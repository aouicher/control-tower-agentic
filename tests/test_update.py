"""Updating the kit from the vault (`configure.py update`): a copy of the kit in git with a local origin, a vault installed
from it, and the update checked and applied through the kit's own configure.py. The update moves the kit's folder to the
commit the user was shown, then hands over to the new kit's `configure.py refresh`, an ordinary change (new access needs a
yes). Temporary folders only; the schedule is written for launchd in a temporary folder and never loaded."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
from plan import kit_commit  # noqa: E402

GIT = ['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com', '-c', 'commit.gpgsign=false']


def git(repo, *args):
    r = subprocess.run(GIT + ['-C', repo] + list(args), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def kit_files():
    """The kit's files, relative to ROOT: the ones git tracks, or, in a copy without git (the test container, whose
    .dockerignore leaves .git out), every file but what that .dockerignore leaves out."""
    r = subprocess.run(['git', '-C', ROOT, 'ls-files'], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return [rel for rel in r.stdout.split('\n') if rel]
    out = []
    for dp, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__') and os.path.relpath(os.path.join(dp, d), ROOT) != os.path.join('tests', '.work')]
        out += [os.path.relpath(os.path.join(dp, f), ROOT) for f in files if not f.endswith('.local') and not f.startswith('.env')]
    return out


def kit_repo(dest):
    """A git repository at `dest` with one commit of the kit's files."""
    os.makedirs(dest, exist_ok=True)
    for rel in kit_files():
        if os.path.isfile(os.path.join(ROOT, rel)):
            os.makedirs(os.path.dirname(os.path.join(dest, rel)), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, rel), os.path.join(dest, rel))
    git(dest, 'init', '-q', '-b', 'main')
    git(dest, 'add', '-A')
    git(dest, 'commit', '-q', '-m', 'kit')


class UpdateTests(unittest.TestCase):
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
        self.origin, self.kit = os.path.join(t, 'origin'), os.path.join(t, 'kit')
        for repo in (self.origin, self.kit):
            subprocess.run(GIT + ['clone', '-q', self.seed if repo == self.origin else self.origin, repo], check=True, capture_output=True)
        self.la = os.path.join(t, 'LaunchAgents')
        self.vault, self.ct = os.path.join(t, 'vault'), os.path.join(t, 'ct')
        self.answers = os.path.join(t, 'answers.json')
        with open(self.answers, 'w') as fh:
            json.dump({'owner_name': 'Sam Rivera', 'owner_handle': 'sam', 'timezone': 'UTC', 'vault_path': self.vault,
                       'ct_home': self.ct, 'packs': ['developer'], 'tools': {'code': 'github'}, 'scheduler': 'launchd',
                       'claude_bin': os.path.join(t, 'bin', 'claude')}, fh)

    def tearDown(self):
        self._tmp.cleanup()

    def install(self, *extra):
        r = subprocess.run([sys.executable, os.path.join(self.kit, 'installer', 'install.py'), '--answers', self.answers,
                            '--launch-agents-dir', self.la, '--no-launchctl'] + list(extra), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def commit(self, rel, edit, message):
        path = os.path.join(self.origin, rel)
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(edit(text))
        git(self.origin, 'add', '-A')
        git(self.origin, 'commit', '-q', '-m', message)

    def upstream(self):
        """Two new commits on the kit's origin: a CHANGELOG entry, then a change to a core skill."""
        self.commit('CHANGELOG.md', lambda t: t.replace('## Unreleased\n\n', '## Unreleased\n\n- Reports read faster.\n', 1), 'docs')
        self.commit(os.path.join('core', 'vault', '.claude', 'skills', 'today', 'SKILL.md'), lambda t: t + '\nNew line from the kit.\n', 'feat')

    def update(self, *args):
        r = subprocess.run([sys.executable, os.path.join(self.kit, 'installer', 'configure.py'), 'update', '--vault', self.vault,
                            '--launch-agents-dir', self.la, '--no-launchctl'] + list(args), capture_output=True, text=True)
        return r, (json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip().startswith('{') else None)

    def check(self):
        r, out = self.update()
        self.assertEqual(r.returncode, 0, r.stderr)
        return out

    def test_check_reports_how_far_behind_and_what_changed(self):
        self.install()
        self.upstream()
        out = self.check()
        self.assertEqual((out['behind'], out['local_changes'], out['changes'], out['pending']), (2, [], ['Reports read faster.'], False))
        self.assertEqual(out['to'], git(self.origin, 'rev-parse', 'HEAD'))
        self.assertEqual(git(self.kit, 'rev-list', '--count', 'HEAD..origin/main'), '2', 'checking moves nothing')
        self.assertEqual(kit_commit(self.kit), git(self.kit, 'rev-parse', 'HEAD'))
        self.assertIsNone(kit_commit(os.path.join(self.kit, 'installer')), 'a folder inside a checkout never answers for it')
        spaced = os.path.join(self._tmp.name, 'My Projects', 'kit')
        subprocess.run(GIT + ['clone', '-q', self.origin, spaced], check=True, capture_output=True)
        self.assertEqual(kit_commit(spaced), git(spaced, 'rev-parse', 'HEAD'))

    def test_a_developer_s_changes_are_never_discarded(self):
        self.install()
        self.upstream()
        with open(os.path.join(self.kit, 'README.md'), 'a', encoding='utf-8') as fh:
            fh.write('\nA developer was here.\n')
        out = self.check()
        self.assertEqual(out['local_changes'], ['README.md'])
        r, _ = self.update('--apply', '--to', out['to'])
        self.assertEqual(r.returncode, 2)
        with open(os.path.join(self.kit, 'README.md'), encoding='utf-8') as fh:
            self.assertIn('A developer was here.', fh.read())
        git(self.kit, 'checkout', '--', 'README.md')
        git(self.kit, 'commit', '-q', '--allow-empty', '-m', 'a local commit')
        self.assertIn('local commits', ' '.join(self.check()['local_changes']))
        self.assertEqual(self.update('--apply', '--to', out['to'])[0].returncode, 2)

    def test_apply_moves_to_the_commit_shown_and_refreshes_the_vault(self):
        self.install()
        today = os.path.join(self.vault, '.claude', 'skills', 'today', 'SKILL.md')
        with open(today, 'a', encoding='utf-8') as fh:
            fh.write('\nMy own line.\n')
        self.upstream()
        shown = self.check()['to']
        self.commit('README.md', lambda t: t + '\nLater.\n', 'after the user looked')
        r, out = self.update('--apply', '--to', shown)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(self.kit, 'rev-parse', 'HEAD'), shown, 'only what the user was shown')
        self.assertEqual(out['moved'], 2)
        self.assertIn('.claude/skills/today/SKILL.md', out['kept'], 'the user edited it: the new version waits in the updates folder')
        with open(today, encoding='utf-8') as fh:
            self.assertIn('My own line.', fh.read())
        with open(os.path.join(self.ct, 'install.json')) as fh:
            self.assertEqual(json.load(fh)['claude_bin'], os.path.join(self._tmp.name, 'bin', 'claude'), 'the runtime keeps its claude')
        out = self.check()
        self.assertEqual((out['behind'], out['pending']), (1, False))

    def test_new_access_from_the_kit_waits_for_a_yes(self):
        self.install()
        self.commit(os.path.join('packs', 'developer', 'pack.json'), lambda t: t.replace('"jobs": ["morning-prs", "weekly-wrap"]',
                                                                                     '"jobs": ["morning-prs", "weekly-wrap", "new-job"]'), 'pack')
        job = os.path.join(self.origin, 'packs', 'developer', 'jobs')
        shutil.copytree(os.path.join(job, 'weekly-wrap'), os.path.join(job, 'new-job'))
        self.commit(os.path.join('packs', 'developer', 'jobs', 'new-job', 'job.json'), lambda t: t.replace('"weekly-wrap"', '"new-job"'), 'job')
        to = self.check()['to']
        r, _ = self.update('--apply', '--to', to)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn('new-job', r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.ct, 'jobs', 'new-job')), 'nothing installed before the yes')
        self.assertEqual(git(self.kit, 'rev-parse', 'HEAD'), git(self.origin, 'rev-parse', 'HEAD~2'), 'all or nothing: the kit went back')
        out = self.check()
        self.assertEqual((out['behind'], out['pending']), (2, False))
        git(self.kit, 'merge', '-q', '--ff-only', to)  # a developer moves the kit without installing it: pending
        self.assertTrue(self.check()['pending'])
        r = subprocess.run([sys.executable, os.path.join(self.kit, 'installer', 'configure.py'), 'set', '--vault', self.vault, '--job',
                            'morning-prs', '--time', '09:00', '--launch-agents-dir', self.la, '--no-launchctl'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, 'any other change applies the moved kit, so its new access needs the same yes')
        self.assertIn('new-job', r.stderr)
        r, _ = self.update('--apply', '--to', to, '--accept-access')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isdir(os.path.join(self.ct, 'jobs', 'new-job')))
        self.assertEqual(self.check()['pending'], False)

    def test_a_refresh_that_wrote_keeps_the_kit_on_its_new_version(self):
        self.install()
        self.commit(os.path.join('installer', 'configure.py'), lambda t: t.replace("if __name__ == '__main__':\n    sys.exit(main())",
                                                                                   "if __name__ == '__main__':\n    sys.exit(3 if 'refresh' in sys.argv else main())"), 'a refresh that ends with 3')
        to = self.check()['to']
        self.assertEqual(self.update('--apply', '--to', to)[0].returncode, 3)
        self.assertEqual(git(self.kit, 'rev-parse', 'HEAD'), to, 'saved, only the schedule failed: the kit stays with what it wrote')
        self.assertTrue(self.check()['pending'])

    def test_the_schedule_is_reloaded_only_when_it_was_loaded(self):
        plist = os.path.join(self.la, 'com.control-tower.morning-prs.plist')
        self.install()
        self.upstream()
        self.assertEqual(self.update('--apply', '--to', self.check()['to'])[0].returncode, 0)
        self.assertFalse(os.path.exists(plist), 'never loaded before: not loaded by an update')
        self.install('--apply-schedule')
        self.commit('README.md', lambda t: t + '\nMore.\n', 'more')
        self.assertEqual(self.update('--apply', '--to', self.check()['to'])[0].returncode, 0)
        self.assertTrue(os.path.exists(plist), 'loaded before: loaded again')

    def test_a_changed_routine_prompt_is_named(self):
        self.install()
        self.commit(os.path.join('packs', 'developer', 'routines', 'daily-note.md'), lambda t: t + '\nOne more step.\n', 'routine')
        r, out = self.update('--apply', '--to', self.check()['to'])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out['routines_changed'], ['developer--daily-note.prompt.md'])

    def test_an_ignored_file_the_update_would_overwrite_stops_it(self):
        self.install()
        with open(os.path.join(self.kit, 'notes.local'), 'w') as fh:  # ignored by the kit's .gitignore
            fh.write('mine')
        with open(os.path.join(self.origin, 'notes.local'), 'w') as fh:
            fh.write('the kit\'s')
        git(self.origin, 'add', '-f', 'notes.local')
        git(self.origin, 'commit', '-q', '-m', 'track it')
        r, _ = self.update('--apply', '--to', self.check()['to'])
        self.assertEqual(r.returncode, 2)
        with open(os.path.join(self.kit, 'notes.local')) as fh:
            self.assertEqual(fh.read(), 'mine')

    def test_a_developer_s_own_update_is_not_pending(self):
        self.install()
        self.upstream()
        git(self.kit, 'pull', '-q', '--ff-only')
        self.install('--update')  # the three-command path of docs/updating.md
        out = self.check()
        self.assertEqual((out['behind'], out['pending']), (0, False))

    def test_nothing_to_update_and_no_dry_run(self):
        self.install()
        self.assertEqual(self.check()['behind'], 0)
        self.assertEqual(self.update('--apply', '--to', 'HEAD', '--dry-run')[0].returncode, 2, 'there is no dry run of a move')
        with open(os.path.join(self.vault, '.control-tower', 'answers.json'), 'w') as fh:
            fh.write('{not json')
        r, _ = self.update()
        self.assertEqual(r.returncode, 2)
        self.assertIn('not valid JSON', r.stderr)


if __name__ == '__main__':
    unittest.main()
