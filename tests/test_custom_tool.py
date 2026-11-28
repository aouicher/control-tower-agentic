"""A capability served by the user's own connection (`"tools": {"logs": "connection:<id>"}`): the kit's reports that need
it get that connection's read tools and server, and read the vault's own guide to query it. Temporary folders only."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
import install  # noqa: E402
from plan import InstallError, fingerprint  # noqa: E402

CONFIGURE = os.path.join(ROOT, 'installer', 'configure.py')
DOCTOR = os.path.join(ROOT, 'installer', 'doctor.py')
SERVER = {'type': 'http', 'url': 'https://logs.example.com/mcp'}


class CustomToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = self._tmp.name
        self.vault, self.ct = os.path.join(t, 'vault'), os.path.join(t, 'ct')
        os.makedirs(self.vault)
        with open(os.path.join(self.vault, '.mcp.json'), 'w') as fh:
            json.dump({'mcpServers': {'company-logs': SERVER}}, fh)
        self.a = {'owner_name': 'Sam Rivera', 'owner_handle': 'sam', 'timezone': 'UTC', 'vault_path': self.vault, 'ct_home': self.ct,
                  'packs': ['engineering'], 'scheduler': 'none',
                  'tools': {'calendar': 'none', 'tracker': 'none', 'code': 'none', 'errors': 'none', 'quality': 'none',
                            'logs': 'connection:company-logs'},
                  'connections': {'company-logs': {'server': 'company-logs', 'read_tools': ['mcp__company-logs__query_logs']}},
                  'fingerprints': {'company-logs': fingerprint(SERVER)}}

    def tearDown(self):
        self._tmp.cleanup()

    def read(self, *parts):
        with open(os.path.join(*parts), encoding='utf-8') as fh:
            return fh.read()

    def test_the_kit_s_report_uses_the_connection(self):
        report = install.install(self.a, log=lambda *x: None)
        self.assertIn('service-health', [j['id'] for j in report['jobs']], 'the capability has a tool: the report is installed')
        job = os.path.join(self.ct, 'jobs', 'service-health')
        allow = json.loads(self.read(job, 'settings.json'))['permissions']['allow']
        self.assertIn('mcp__company-logs__query_logs', allow)
        self.assertEqual(list(json.loads(self.read(job, 'mcp.json'))['mcpServers']), ['company-logs'], 'its server, as approved')
        note = self.read(self.vault, '.claude', 'adapters', 'logs.md')
        self.assertIn('company-logs', note)
        self.assertIn('.claude/adapters/logs-guide.md', note, 'how to query it is the vault\'s own guide')
        self.assertIn('## Contract', note, 'what the report expects back stays the kit\'s')
        self.assertIn('company-logs', self.read(self.vault, 'library', 'setup-next-steps.md'))

    def test_only_a_connection_this_computer_can_reach(self):
        for conns, why in (({}, 'no connection'), ({'company-logs': {'connector': 'Logs'}}, 'claude.ai connector')):
            with self.subTest(why):
                with self.assertRaises(InstallError) as err:
                    install.install(dict(self.a, connections=conns, fingerprints={}), dry_run=True, log=lambda *x: None)
                self.assertIn('connection:company-logs', str(err.exception))

    def test_a_connection_a_capability_uses_stays_until_the_capability_moves(self):
        install.install(self.a, log=lambda *x: None)
        r = subprocess.run([sys.executable, CONFIGURE, 'remove-connection', '--vault', self.vault, '--id', 'company-logs'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn('give logs another tool first', r.stderr)
        for extra in ({'servers': {'logs': 'other'}}, {'permissions': {'logs': ['mcp__other__read']}}):
            with self.subTest(extra), self.assertRaises(InstallError):  # the connection's rules, never others on top
                install.install(dict(self.a, **extra), dry_run=True, log=lambda *x: None)
        with self.assertRaises(InstallError):  # a connection without read tools gives reports nothing: never a capability's tool
            install.install(dict(self.a, connections={'company-logs': {'server': 'company-logs', 'read_tools': []}}), dry_run=True, log=lambda *x: None)

    def test_a_cloud_routine_never_counts_on_it(self):
        self.assertEqual(install.routine_missing({'connectors_required': ['logs', 'errors']}, {'logs': 'connection:company-logs', 'errors': 'sentry'}),
                         ['logs'], 'a routine on claude.ai cannot reach a connection of this computer')

    def test_set_through_configure_with_consent_and_checked_by_the_doctor(self):
        install.install(dict(self.a, tools=dict(self.a['tools'], logs='none')), log=lambda *x: None)
        cmd = [sys.executable, CONFIGURE, 'set', '--vault', self.vault, '--tool', 'logs=connection:company-logs']
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, 'new access: the user says yes first')
        self.assertIn('query logs (company-logs)', r.stderr)
        r = subprocess.run(cmd + ['--accept-access'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        doctor = subprocess.run([sys.executable, DOCTOR, '--vault', self.vault, '--ct-home', self.ct], capture_output=True, text=True).stdout
        self.assertIn('logs-guide.md', doctor, 'no guide yet: the report would not know how to query it')
        with open(os.path.join(self.vault, '.claude', 'adapters', 'logs-guide.md'), 'w') as fh:
            fh.write('# Querying the company logs\n')
        doctor = subprocess.run([sys.executable, DOCTOR, '--vault', self.vault, '--ct-home', self.ct], capture_output=True, text=True).stdout
        self.assertNotIn('[warn] logs guide', doctor)


if __name__ == '__main__':
    unittest.main()
