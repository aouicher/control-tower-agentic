#!/usr/bin/env python3
"""Stand-in for the `claude` CLI used by the end-to-end tests. Never calls any network or model.

It behaves like `claude -p ... --settings <file>`: it loads the job's settings, replays a few hostile tool calls through
the PreToolUse hook that the settings declare (they must be blocked), writes one allowed report into the vault, and prints
the JSON shape the runner expects. Records its arguments in $FAKE_CLAUDE_LOG.
"""
import json
import os
import subprocess
import sys
from datetime import date

args = sys.argv[1:]
settings = args[args.index('--settings') + 1]
mode = args[args.index('--permission-mode') + 1]
log = os.environ.get('FAKE_CLAUDE_LOG')
if log:
    with open(log, 'a') as fh:
        fh.write(json.dumps({'cwd': os.getcwd(), 'mode': mode, 'settings': settings, 'model': args[args.index('--model') + 1]}) + '\n')
st = json.load(open(settings))
# the real CLI reads Edit(/x) as relative to the settings file and Edit(//x) as absolute: the vault rule must be absolute
vault_rules = [r for r in st['permissions']['allow'] if r.startswith('Edit(//')]
if not any(os.path.realpath(r[6:-4]) == os.path.realpath(os.getcwd()) for r in vault_rules if r.endswith('/**)')):
    print(json.dumps({'is_error': True, 'result': f'no absolute Edit rule for the vault in {st["permissions"]["allow"]}'}))
    sys.exit(1)
hook = st['hooks']['PreToolUse'][0]['hooks'][0]['command']
cwd = os.getcwd()
hostile = [
    {'tool_name': 'Bash', 'tool_input': {'command': 'git push origin main'}},
    {'tool_name': 'Bash', 'tool_input': {'command': 'cat ~/.aws/credentials'}},
    {'tool_name': 'Edit', 'tool_input': {'file_path': os.path.join(cwd, '.claude', 'settings.json')}},
    {'tool_name': 'Write', 'tool_input': {'file_path': '/tmp/outside.md'}},
    {'tool_name': 'Read', 'tool_input': {'file_path': os.path.expanduser('~/.ssh/id_rsa')}},
    {'tool_name': 'Glob', 'tool_input': {'pattern': '**/.env*'}, 'cwd': cwd},
]
for ev in hostile:
    ev.setdefault('cwd', cwd)
    rc = subprocess.run(hook, shell=True, input=json.dumps(ev), text=True, capture_output=True).returncode
    if rc != 2:
        print(json.dumps({'is_error': True, 'result': f'guard did not block {ev}'}))
        sys.exit(1)
ok = subprocess.run(hook, shell=True, input=json.dumps({'tool_name': 'Write', 'tool_input': {'file_path': os.path.join(cwd, 'journal', 'reports', 'e2e.md')}, 'cwd': cwd}),
                    text=True, capture_output=True).returncode
if ok != 0:
    print(json.dumps({'is_error': True, 'result': 'guard blocked a legitimate vault write'}))
    sys.exit(1)
os.makedirs(os.path.join(cwd, 'journal', 'reports'), exist_ok=True)
with open(os.path.join(cwd, 'journal', 'reports', f'e2e-{date.today()}.md'), 'w') as fh:
    fh.write('---\ntitle: "e2e"\ntype: report\n---\n\n# e2e\n')
# a command no rule allows: the real CLI refuses it in dontAsk mode and lists it in permission_denials
print(json.dumps({'is_error': False, 'result': 'e2e ok', 'total_cost_usd': 0, 'num_turns': 1,
                  'permission_denials': [{'tool_name': 'Bash', 'tool_use_id': 'e2e', 'tool_input': {'command': 'acme-cli tickets list --mine'}}]}))
