"""Connections to tools the kit does not know (`connections` in the answers): an MCP server of the vault or a command, with
the read tools reports may use, all through installer/configure.py. Temporary folders and a fake claude only."""
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
ENTRY = {'type': 'http', 'url': 'https://mcp.example.com/mcp'}


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.a = answers(self._tmp.name, ['developer'], tools={'code': 'github'})
        install.install(self.a, log=lambda *x: None)
        self.vault, self.ct = self.a['vault_path'], self.a['ct_home']

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, *args, env=None):
        return subprocess.run([sys.executable, CONFIGURE] + list(args) + ['--vault', self.vault], capture_output=True, text=True,
                              env=env)

    def saved(self):
        return json.load(open(os.path.join(self.vault, '.control-tower', 'answers.json')))

    def declare(self, **servers):
        with open(os.path.join(self.vault, '.mcp.json'), 'w') as fh:
            json.dump({'mcpServers': servers}, fh)

    def probed(self, server, tools, status='connected'):
        with open(os.path.join(self.ct, 'probe.json'), 'w') as fh:
            json.dump({'servers': [{'name': server, 'status': status}], 'tools': tools, 'connectors': 0}, fh)

    def add(self, *args):
        return self.cli('add-connection', *args, '--accept-access')

    def test_an_mcp_connection_keeps_only_read_tools_the_probe_saw(self):
        self.declare(mailbox=ENTRY)
        self.probed('mailbox', ['mcp__mailbox__search_threads', 'mcp__mailbox__get_thread', 'mcp__mailbox__send_message'])
        r = self.add('--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox__search_threads', 'mcp__mailbox__get_thread')
        self.assertEqual(r.returncode, 0, r.stderr)
        saved = self.saved()
        self.assertEqual(saved['connections'], {'mail': {'server': 'mailbox',
                                                         'read_tools': ['mcp__mailbox__get_thread', 'mcp__mailbox__search_threads']}})
        self.assertIn('mailbox', saved['fingerprints'])
        jobs = os.path.join(self.ct, 'jobs')
        for job in os.listdir(jobs):  # reports use a connection only once it is assigned to them
            self.assertEqual(json.load(open(os.path.join(jobs, job, 'mcp.json')))['mcpServers'], {}, job)
        show = json.loads(self.cli('show').stdout)
        self.assertEqual(show['connections'], saved['connections'])
        import doctor
        self.assertFalse([i for i in doctor.check(self.vault, self.ct, 'python3').items if i['check'] == 'vault file .mcp.json'],
                         'a server used by a connection is neither unused nor changed')
        choices = json.loads(subprocess.run([sys.executable, CONFIGURE, 'choices', '--vault', self.vault, '--kind', 'connections'],
                                            capture_output=True, text=True).stdout)
        self.assertIn('mail', choices['items'])

    def test_refused_mcp_connections(self):
        self.declare(mailbox=ENTRY, other=ENTRY)
        seen = ['mcp__mailbox__search_threads', 'mcp__mailbox__send_message', 'mcp__other__search']
        self.probed('mailbox', seen)
        cases = {
            'an action tool': ['--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox__send_message'],
            'a wildcard': ['--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox__*'],
            'a whole server': ['--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox'],
            'another server': ['--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__other__search'],
            'a tool the probe did not see': ['--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox__list_labels'],
            'a bad id': ['--id', 'My Mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox__search_threads'],
            'a bad server id': ['--id', 'mail', '--server', '../mailbox', '--read-tools', 'mcp__mailbox__search_threads'],
            'a server the probe did not see': ['--id', 'mail', '--server', 'other', '--read-tools', 'mcp__other__search'],
            'no read tool': ['--id', 'mail', '--server', 'mailbox', '--read-tools'],
        }
        before = open(os.path.join(self.vault, '.control-tower', 'answers.json')).read()
        for why, args in cases.items():
            with self.subTest(why):
                r = self.add(*args)
                self.assertEqual(r.returncode, 2, f'{why}: {r.stdout}')
        self.declare(other=ENTRY)
        self.assertEqual(self.add('--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox__search_threads').returncode, 2,
                         'a server that is not in the vault')
        self.assertEqual(open(os.path.join(self.vault, '.control-tower', 'answers.json')).read(), before)

    def test_a_known_tool_s_server_is_not_a_connection(self):
        self.declare(atlassian=ENTRY)
        self.probed('atlassian', ['mcp__atlassian__search'])
        self.assertEqual(self.cli('connect', '--capability', 'tracker', '--tool', 'jira', '--server', 'atlassian', '--accept-access').returncode, 0)
        r = self.add('--id', 'jira2', '--server', 'atlassian', '--read-tools', 'mcp__atlassian__search')
        self.assertEqual(r.returncode, 2)
        self.assertIn('"atlassian" is connected twice', r.stderr)
        self.declare(atlassian=ENTRY, mailbox=ENTRY)
        self.probed('mailbox', ['mcp__mailbox__search_threads'])
        self.assertEqual(self.add('--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox__search_threads').returncode, 0)
        r = self.cli('connect', '--capability', 'tracker', '--tool', 'jira', '--server', 'mailbox', '--accept-access')
        self.assertEqual(r.returncode, 2)
        self.assertIn('"mailbox" is connected twice', r.stderr)

    def test_a_new_server_needs_consent(self):
        self.declare(mailbox=ENTRY)
        self.probed('mailbox', ['mcp__mailbox__search_threads'])
        args = ['add-connection', '--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox__search_threads']
        self.assertIn(['jobs that call it', 'mcp server', 'mailbox'], json.loads(self.cli(*args, '--dry-run').stdout)['new_access'])
        self.assertEqual(self.cli(*args).returncode, 2)

    def test_a_command_connection_needs_its_network_answer_first(self):
        args = ['--id', 'notes-cli', '--command', 'notecli', '--read-tools', 'Bash(notecli list:*)']
        r = self.add(*args)
        self.assertEqual(r.returncode, 2)
        self.assertIn('add-command', r.stderr)
        self.assertEqual(self.cli('add-command', '--command', 'notecli', '--no-network').returncode, 0)
        self.assertEqual(self.add(*args).returncode, 0)
        self.assertEqual(self.saved()['connections']['notes-cli'], {'command': 'notecli', 'read_tools': ['Bash(notecli list:*)']})
        r = self.cli('remove-command', '--command', 'notecli')
        self.assertEqual(r.returncode, 2, 'its network answer goes only with the connection')
        self.assertIn('notes-cli', r.stderr)
        for bad in (['--id', 'x', '--command', 'notecli', '--read-tools', 'Bash(other list:*)'],
                    ['--id', 'x', '--command', 'curl', '--read-tools', 'Bash(curl example.com)'],
                    ['--id', 'x', '--command', 'notecli', '--read-tools', 'Bash(notecli list; rm -rf ~)'],
                    ['--id', 'x', '--command', 'gh', '--read-tools', 'Bash(gh:*)'],
                    ['--id', 'x', '--command', 'gh', '--read-tools', 'Bash(gh issue create:*)'],
                    ['--id', 'x', '--command', 'gh', '--read-tools', 'Bash(gh api:*)'],
                    ['--id', 'x', '--command', 'gh', '--read-tools', 'Bash(TOKEN=abc gh pr list:*)'],
                    ['--id', 'x', '--command', 'gh', '--read-tools', 'Bash(gh pr list --repo acme/x:*)'],
                    ['--id', 'x', '--command', 'notecli', '--read-tools', 'Bash(notecli send-message:*)'],
                    ['--id', 'x', '--command', 'gh', '--read-tools', 'Bash(gh pr:*)'],
                    ['--id', 'x', '--command', 'gh', '--read-tools', 'Bash(gh repo clone:*)'],
                    ['--id', 'x', '--command', 'gh', '--read-tools', 'Bash(gh workflow run:*)'],
                    ['--id', 'x', '--command', 'gh', '--read-tools', 'Bash(gh release download:*)'],
                    ['--id', 'x', '--command', 'notecli', '--read-tools', 'Bash(notecli list start:*)']):
            with self.subTest(bad=bad):
                self.assertEqual(self.add(*bad).returncode, 2)
        self.assertEqual(self.add('--id', 'gh-read', '--command', 'gh', '--read-tools', 'Bash(gh pr list:*)').returncode, 0,
                         'a known command has its addresses already')
        self.assertEqual(self.cli('remove-command', '--command', 'gh').returncode, 0, 'nothing recorded for gh: nothing to remove')
        slack = ['--id', 'slack', '--command', 'slackcli', '--read-tools', 'Bash(slackcli conversations unread:*)']
        self.assertEqual(self.add(*slack).returncode, 2, "a known command whose address depends on the company needs it first")
        self.cli('add-command', '--command', 'slackcli', '--allow-write', '~/Library/Logs/slackcli', '--accept-access')
        self.assertEqual(self.add(*slack).returncode, 2, 'a write folder is not an answer about its web addresses')
        self.assertEqual(self.cli('add-command', '--command', 'slackcli', '--host', 'acme.slack.com', '--accept-access').returncode, 0)
        self.assertEqual(self.add(*slack).returncode, 0)

    def test_a_connection_server_is_never_started_by_pack_reports(self):
        # a connection named like an adapter's server: the pack jobs that call that name do not get it
        self.declare(github=ENTRY)
        self.probed('github', ['mcp__github__search_issues'])
        self.assertEqual(self.add('--id', 'github', '--server', 'github', '--read-tools', 'mcp__github__search_issues').returncode, 0)
        self.assertEqual(self.cli('grant', '--job', 'morning-prs', '--rule', 'mcp__github__search_issues', '--accept-access').returncode, 0)
        self.assertEqual(json.load(open(os.path.join(self.ct, 'jobs', 'morning-prs', 'mcp.json')))['mcpServers'], {})

    def test_remove_a_connection(self):
        self.declare(mailbox=ENTRY)
        self.probed('mailbox', ['mcp__mailbox__search_threads'])
        self.add('--id', 'mail', '--server', 'mailbox', '--read-tools', 'mcp__mailbox__search_threads')
        self.assertEqual(self.cli('remove-connection', '--id', 'mail').returncode, 0)
        saved = self.saved()
        self.assertNotIn('mail', saved.get('connections', {}))
        self.assertNotIn('mailbox', saved.get('fingerprints', {}))
        self.assertEqual(self.cli('remove-connection', '--id', 'mail').returncode, 0, 'nothing to remove')

    def test_the_installer_refuses_a_bad_connection_record(self):
        for bad in ({'Bad Id': {'server': 's', 'read_tools': ['mcp__s__get']}},
                    {'x': {'server': 's', 'read_tools': ['mcp__s__delete_all']}},
                    {'x': {'server': 's', 'read_tools': ['mcp__t__get']}},
                    {'x': {'server': 's', 'command': 'c', 'read_tools': ['mcp__s__get']}},
                    {'x': {'command': 'c', 'read_tools': ['Bash(d list:*)']}},
                    {'x': {'server': 's', 'read_tools': []}},
                    {'code': {'server': 's', 'read_tools': ['mcp__s__get']}},
                    {'x': ['mcp__s__get']}):
            with self.subTest(bad=bad):
                with self.assertRaises(install.InstallError):
                    install.install(dict(self.a, connections=bad), dry_run=True, log=lambda *x: None)


class AddServerTests(unittest.TestCase):
    """`add-server` adds an MCP address the user gives to the vault's .mcp.json with Claude Code's own command, never a shell."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.a = answers(self._tmp.name, ['developer'], tools={'code': 'github'})
        install.install(self.a, log=lambda *x: None)
        self.vault = self.a['vault_path']
        self.record = os.path.join(self._tmp.name, 'argv.json')
        fake = os.path.join(self._tmp.name, 'claude')
        with open(fake, 'w') as fh:
            fh.write(f'#!{sys.executable}\nimport json, os, sys\njson.dump({{"argv": sys.argv[1:], "cwd": os.getcwd()}}, open({self.record!r}, "w"))\n')
        os.chmod(fake, 0o755)
        self.env = dict(os.environ, CT_CLAUDE_BIN=fake)

    def tearDown(self):
        self._tmp.cleanup()

    def add(self, name, url):
        return subprocess.run([sys.executable, CONFIGURE, 'add-server', '--vault', self.vault, '--name', name, '--url', url],
                              capture_output=True, text=True, env=self.env)

    def test_an_https_address_is_added_at_project_scope(self):
        r = self.add('company-docs', 'https://mcp.example.com/v1/mcp')
        self.assertEqual(r.returncode, 0, r.stderr)
        call = json.load(open(self.record))
        self.assertEqual(call['argv'], ['mcp', 'add', '--scope', 'project', '--transport', 'http', 'company-docs',
                                        'https://mcp.example.com/v1/mcp'])
        self.assertEqual(os.path.realpath(call['cwd']), os.path.realpath(self.vault))
        for url in ('https://mcp.sentry.dev/mcp/acme/web-app', 'https://mcp.atlassian.com/v2/mcp', 'https://calendarmcp.googleapis.com/mcp/v1'):
            with self.subTest(url=url):
                self.assertEqual(self.add('ok-' + str(len(url)), url).returncode, 0, 'an address with short words only')

    def test_refused_addresses_and_names(self):
        with open(os.path.join(self.vault, '.mcp.json'), 'w') as fh:
            json.dump({'mcpServers': {'taken': ENTRY}}, fh)
        for name, url in (('docs', 'http://mcp.example.com/mcp'), ('docs', 'https://mcp.example.com/mcp?key=abc'),
                          ('docs', 'https://user:pw@mcp.example.com/mcp'), ('docs', 'https://10.0.0.1/mcp'),
                          ('docs', "https://mcp.example.com/'; rm -rf ~"), ('docs', 'https://mcp.example.com/a b'),
                          ('docs', 'https://localhost/mcp'), ('bad name', 'https://mcp.example.com/mcp'), ('--scope', 'https://mcp.example.com/mcp'),
                          ('taken', 'https://mcp.example.com/mcp'), ('docs', 'https://[abc/x'), ('Docs', 'https://mcp.example.com/mcp'),
                          ('docs', 'https://mcp.zapier.com/api/mcp/s/ZmFrZS1zZWNyZXQtdG9rZW4/mcp'),
                          ('docs', 'https://eu2.make.com/mcp/api/v1/u/0f8e4567-e89b-42d3-a456-4266ab17cd00/sse'),
                          ('docs', 'https://mcp.example.com/mcp;apikey=sk-live-123'), ('docs', 'https://mcp.example.com/k/a1b2c3d4e5f6a7b8'),
                          ('docs', 'https://mcp.example.com/%73ecret'), ('docs', 'https://mcp.example.com/abcdefghijKLMNOPqrstuvwx/mcp'),
                          ('docs', 'https://k7f9q2m4x8z1p3v6.mcp.example.com/mcp'), ('docs', 'https://mcp.example.com:abc/mcp')):
            with self.subTest(name=name, url=url):
                self.assertEqual(self.add(name, url).returncode, 2)
        self.assertFalse(os.path.exists(self.record), 'claude was never called')


if __name__ == '__main__':
    unittest.main()
