#!/usr/bin/env python3
"""Opt-in smoke test with the REAL Claude Code CLI (costs a few cents, uses your signed-in account).

It installs the developer pack into a temporary folder, swaps one job's prompt for a short probe, runs it through the real
runner with Haiku, and checks what the CLI actually allowed: the report written in the vault, the protected areas untouched.
This is the only test that exercises Claude Code's own permission rules; the fake claude cannot.

    CT_REAL_CLAUDE=1 python3 tests/e2e/smoke_real_claude.py

With --facts it instead checks the Claude Code behaviours the kit relies on (docs/design/runtime-facts.md), each in a
temporary folder with Haiku, and prints PASS, FAIL or UNKNOWN per fact. It exits non-zero unless every fact passes.

    CT_REAL_CLAUDE=1 python3 tests/e2e/smoke_real_claude.py --facts [--save-init tests/e2e/fixtures/init_message.json]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'installer'))
import install  # noqa: E402
import plan  # noqa: E402

PROBE = """You are a test probe. Never ask questions. Do exactly these steps, then stop:
0. Read the file .claude/adapters/code.md with the Read tool and note its first heading.
1. With the Write tool, write the file journal/reports/smoke.md containing two lines: smoke ok, then the heading you read in step 0 (or UNREADABLE if step 0 was refused)
2. Write the file .claude/settings.json containing {}
3. Write the file ../outside.md containing x
Reply with one line per step: the step number and whether it succeeded or was refused."""


def smoke():
    with tempfile.TemporaryDirectory() as tmp:
        vault, ct = os.path.join(tmp, "smoke vault's"), os.path.join(tmp, 'ct')
        answers = {'owner_name': 'Smoke', 'owner_handle': 'smoke', 'timezone': 'UTC', 'vault_path': vault, 'ct_home': ct,
                   'packs': ['developer'], 'tools': {'code': 'github'}, 'scheduler': 'none'}
        install.install(answers, log=lambda *a: None)
        jd = os.path.join(ct, 'jobs', 'morning-prs')
        open(os.path.join(jd, 'prompt.md'), 'w').write(PROBE)
        job = json.load(open(os.path.join(jd, 'job.json')))
        job.update(model='haiku', timeout=300)
        json.dump(job, open(os.path.join(jd, 'job.json'), 'w'))
        settings_before = open(os.path.join(vault, '.claude', 'settings.json')).read() if os.path.exists(os.path.join(vault, '.claude', 'settings.json')) else None
        r = subprocess.run([sys.executable, os.path.join(ct, 'bin', 'run_job.py'), '--job', 'morning-prs', '--ct-home', ct], capture_output=True, text=True)
        log = open(os.path.join(ct, 'logs', 'morning-prs.log')).read() if os.path.exists(os.path.join(ct, 'logs', 'morning-prs.log')) else r.stderr
        # the probe must copy the adapter note's real first heading: proof it read the file, not a guess
        heading = next((l.lstrip('#').strip() for l in open(os.path.join(vault, '.claude', 'adapters', 'code.md'), encoding='utf-8')
                        if l.startswith('#')), '')
        checks = [
            ('the job ran (rc=0)', r.returncode == 0),
            ('report written inside the vault', os.path.isfile(os.path.join(vault, 'journal', 'reports', 'smoke.md'))),
            ('the job could read its adapter note', heading and os.path.isfile(os.path.join(vault, 'journal', 'reports', 'smoke.md'))
             and heading in open(os.path.join(vault, 'journal', 'reports', 'smoke.md')).read()),
            ('.claude/settings.json untouched', (open(os.path.join(vault, '.claude', 'settings.json')).read() if os.path.exists(os.path.join(vault, '.claude', 'settings.json')) else None) == settings_before),
            ('nothing written outside the vault', not os.path.exists(os.path.join(tmp, 'outside.md'))),
        ]
        for name, ok in checks:
            print(('  ok   ' if ok else '  FAIL ') + name)
        print('\n--- job log ---\n' + log[-1200:])
        return 0 if all(ok for _, ok in checks) else 1


# ----------------------------------------------------------------------------- runtime facts
FACTS_SERVER = os.path.join(ROOT, 'tests', 'e2e', 'facts_mcp_server.py')
COST = []  # USD per claude run
FACT_VALUE = 'fact-value-7f3a'  # what the server's get_fact answers: seen in a tool result only if the call really ran
SAY_OK = 'Reply with the single word OK.'
F3_PROMPT = ('Call the tool mcp__facts__get_fact once, then the tool mcp__facts__create_fact once, even if one is refused. '
             'Then reply DONE.')
F6_PROMPT = 'Use the Skill tool to run the skill f6probe, and follow its instructions exactly. Then reply DONE.'
F6_SKILL = """---
name: f6probe
description: Test probe for the runtime facts.
allowed-tools: Bash(echo f6:*)
---
Use the Bash tool once to run exactly this command, unchanged: echo f6 > f6.txt
"""


def run_prompt(command):
    return (f'Use the Bash tool once to run exactly this command, unchanged: {command}\n'
            'Then reply with its complete output, verbatim, including any error text.')


def messages(text):
    out = []
    for line in text.splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if isinstance(m, dict):
            out.append(m)
    return out


def init_of(msgs):
    return next((m for m in msgs if m.get('type') == 'system' and m.get('subtype') == 'init'), {})


def result_of(msgs):
    return next((m for m in reversed(msgs) if m.get('type') == 'result'), {})


def denied(msgs):
    return {str(d.get('tool_name')) for d in result_of(msgs).get('permission_denials') or [] if isinstance(d, dict)}


def tool_output(msgs):
    """Every tool result the model saw, as one text (stream-json `user` messages)."""
    parts = []
    for m in msgs:
        content = (m.get('message') or {}).get('content') if m.get('type') == 'user' else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get('type') == 'tool_result':
                inner = block.get('content')
                parts += [inner] if isinstance(inner, str) else [str(b.get('text', '')) for b in inner or [] if isinstance(b, dict)]
    return '\n'.join(parts)


def denied_commands(msgs):
    return [str((d.get('tool_input') or {}).get('command', '')) for d in result_of(msgs).get('permission_denials') or []
            if isinstance(d, dict) and d.get('tool_name') == 'Bash' and isinstance(d.get('tool_input'), dict)]


def blocked_hosts(text):
    """Hosts the sandbox refused, from the `<sandbox_violations>` block Claude Code appends to a command's output."""
    return sorted({h.lower() for h in re.findall(r'deny network-outbound ([A-Za-z0-9.-]+):\d+', text)})


def server_names(init):
    return {str(s.get('name')) for s in init.get('mcp_servers') or [] if isinstance(s, dict)}


def f1_verdict(project_init, user_init):
    """User-scope servers are the ones a run in an empty folder sees only when user settings load (not plugins or claude.ai)."""
    user = {n for n in server_names(user_init) if not n.startswith(('plugin:', 'claude.ai '))}
    if not user:
        return None, 'no user-scope MCP server on this account to observe'
    seen = user & server_names(project_init)
    return seen == user, f'{len(seen)} of {len(user)} user-scope servers visible with --setting-sources project'


def connector_tool(*inits):
    """A read tool of a claude.ai connector seen in these init messages (Context7 first: it returns public documentation)."""
    tools = [t for i in inits for t in i.get('tools') or [] if t.startswith('mcp__claude_ai_') and t.count('__') == 2]
    reads = [t for t in tools if not set(plan.name_words(t.split('__')[2])) & plan.ACTION_WORDS]
    return next((t for t in reads if 'Context7' in t), reads[0] if reads else None)


def sanitize_init(init, keep=('facts', 'claude.ai Gmail')):
    """The init message reduced to what tests need: no session, path or account data, only the test server and one connector."""
    prefixes = tuple('mcp__' + re.sub(r'[^A-Za-z0-9_-]', '_', k) + '__' for k in keep)
    return {'type': 'system', 'subtype': 'init', 'claude_code_version': init.get('claude_code_version'),
            'permissionMode': init.get('permissionMode'),
            'mcp_servers': [s for s in init.get('mcp_servers') or [] if s.get('name') in keep],
            'tools': list(dict.fromkeys(t for t in init.get('tools') or [] if not t.startswith('mcp__') or t.startswith(prefixes)))}


def claude(cwd, prompt, settings=None, sources='project', turns=6, mcp=None):
    cmd = ['claude', '-p', prompt, '--model', 'haiku', '--max-turns', str(turns), '--permission-mode', 'dontAsk',
           '--setting-sources', sources, '--output-format', 'stream-json', '--verbose']
    if mcp is not None:  # what the job runner passes: only these servers start
        cmd += ['--mcp-config', json.dumps({'mcpServers': mcp}), '--strict-mcp-config']
    if settings is not None:
        path = os.path.join(os.path.dirname(cwd), f'settings-{len(os.listdir(os.path.dirname(cwd)))}.json')
        with open(path, 'w') as fh:
            json.dump(settings, fh)
        cmd += ['--settings', path]
    r = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    msgs = messages(r.stdout)
    COST.append(float(result_of(msgs).get('total_cost_usd') or 0))
    return msgs


def facts(save_init=None):
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        empty, vault = os.path.join(tmp, 'empty'), os.path.join(tmp, 'vault')
        os.makedirs(empty)
        os.makedirs(os.path.join(vault, '.claude', 'skills', 'f6probe'))
        with open(os.path.join(vault, '.mcp.json'), 'w') as fh:
            json.dump({'mcpServers': {'facts': {'command': sys.executable, 'args': [FACTS_SERVER]}}}, fh)
        with open(os.path.join(vault, '.claude', 'settings.local.json'), 'w') as fh:  # what "don't ask again" writes
            json.dump({'permissions': {'allow': ['mcp__facts__get_fact']}}, fh)
        with open(os.path.join(vault, '.claude', 'skills', 'f6probe', 'SKILL.md'), 'w') as fh:
            fh.write(F6_SKILL)
        job = lambda allow, **extra: dict({'permissions': {'allow': allow}, 'enabledMcpjsonServers': ['facts']}, **extra)
        box = lambda **extra: dict({'enabled': True, 'failIfUnavailable': True, 'allowUnsandboxedCommands': False,
                                    'network': {'allowedDomains': []}}, **extra)

        # claude.ai connectors load asynchronously: the init message may come before them, so look a few times
        for _ in range(3):
            project = init_of(claude(empty, SAY_OK, turns=1))
            if connector_tool(project):
                break
        user = init_of(claude(empty, SAY_OK, sources='user,project', turns=1))
        out.append(('F1', *f1_verdict(project, user)))
        tool = connector_tool(project, user)
        if tool:
            r2 = claude(empty, f'Call the tool {tool} once, with minimal arguments (for a library name use react). Then reply DONE.',
                        {'permissions': {'allow': [tool]}})
            ran = tool not in denied(r2) and bool(tool_output(r2).strip())
            out.append(('F2', False if tool in denied(r2) else True if ran else None,
                        f'{tool} with its exact allow rule ' + ('is REFUSED under dontAsk' if tool in denied(r2) else
                                                                'runs' if ran else 'was not called') + ' (launchd part: manual)'))
        else:
            out.append(('F2', None, 'no claude.ai connector in the init messages (they load asynchronously): run again'))

        r1b = claude(vault, 'Call the tool mcp__facts__get_fact, then reply with exactly what it returned.', job(['mcp__facts__get_fact']))
        out.append(('F1b', True if FACT_VALUE in tool_output(r1b) else False if denied(r1b) else None,
                    "an allowed tool of a server in the vault's .mcp.json, enabled by the job settings, "
                    + ('runs in the job' if FACT_VALUE in tool_output(r1b) else 'did not run')))
        call = 'Call the tool mcp__facts__get_fact, then reply with exactly what it returned.'
        r1c = claude(empty, call, {'permissions': {'allow': ['mcp__facts__get_fact']}},
                     mcp={'facts': {'command': sys.executable, 'args': [FACTS_SERVER]}})
        hidden = 'facts' not in server_names(init_of(claude(vault, SAY_OK, job([]), turns=1, mcp={})))
        out.append(('F1c', (FACT_VALUE in tool_output(r1c)) and hidden,
                    'a server given with --mcp-config --strict-mcp-config ' + ('runs' if FACT_VALUE in tool_output(r1c) else 'does NOT run')
                    + "; with an empty one, the vault's enabled .mcp.json server " + ('is not started' if hidden else 'STILL starts')))
        init1b = init_of(r1b)
        listed = 'facts' in server_names(init1b) and 'mcp__facts__create_fact' in (init1b.get('tools') or [])
        out.append(('F7', listed, 'the init message ' + ('lists' if listed else 'does NOT list') + " the .mcp.json server and its tools "
                    f'({len(project.get("mcp_servers") or [])} servers in an empty folder: claude.ai connectors only when they loaded first)'))

        r3 = claude(vault, F3_PROMPT, job(['Read']))
        refused, seen = denied(r3), tool_output(r3)
        out.append(('F3', ('mcp__facts__create_fact' in refused) or (None if not refused else False),
                    f'permission_denials names: {sorted(refused) or "none"}'))
        out.append(('F4', (False if FACT_VALUE in seen else True if 'mcp__facts__get_fact' in refused else None),
                    'with --setting-sources project, a rule in .claude/settings.local.json '
                    + ('REACHED the job' if FACT_VALUE in seen else 'did not reach the job')))
        if save_init:
            with open(save_init, 'w') as fh:
                json.dump(sanitize_init(dict(init1b, mcp_servers=(init1b.get('mcp_servers') or []) + (project.get('mcp_servers') or []),
                                             tools=(init1b.get('tools') or []) + (project.get('tools') or []))), fh, indent=1)

        for fact, allow, prompt, target in (('F5', ['Bash(echo f5:*)'], run_prompt('echo f5 > f5.txt'), 'f5.txt'),
                                            ('F6', ['Skill'], F6_PROMPT, 'f6.txt')):
            r = claude(vault, prompt, job(allow))
            ran, refused = os.path.exists(os.path.join(vault, target)), any(target in c for c in denied_commands(r))
            what = 'Bash(echo f5:*) covers "echo f5 > f5.txt"' if fact == 'F5' else "a skill's allowed-tools grants Bash"
            out.append((fact, False if ran else True if refused else None,
                        ('YES: ' if ran else 'no: ' if refused else 'not attempted: ') + what + ' under dontAsk'))

        r8 = tool_output(claude(vault, run_prompt('gh api /zen'), job(['Bash(gh api:*)'], sandbox=box(enableWeakerNetworkIsolation=True))))
        out.append(('F8', 'api.github.com' in blocked_hosts(r8) or (None if not r8 else False),
                    'blocked host in the sandboxed command output: ' + (r8.strip().replace('\n', ' ')[:200] or 'no output')))
        out.append(('hosts:gh', bool(blocked_hosts(r8)) or None, ', '.join(blocked_hosts(r8)) or 'none blocked'))
        tries = {'twg': ('TWG_AGENT_DEFAULTS=1 twg jira workitem query --jql "created >= -1d"',
                         ['Bash(TWG_AGENT_DEFAULTS=1 twg jira workitem query:*)', 'Bash(twg jira workitem query:*)'], {}),
                 'slackcli': ('slackcli conversations unread', ['Bash(slackcli conversations unread:*)'],
                              {'filesystem': {'allowWrite': ['~/Library/Logs/slackcli']}})}
        for name, (command, allow, extra) in tries.items():
            if shutil.which(name):
                text = tool_output(claude(vault, run_prompt(command), job(allow, sandbox=box(**extra))))
                out.append((f'hosts:{name}', bool(blocked_hosts(text)) or None, ', '.join(blocked_hosts(text)) or 'none blocked: ' + text.strip()[:160]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--facts', action='store_true')
    ap.add_argument('--save-init', help='with --facts: write the reduced init message (a fixture for probe tests)')
    args = ap.parse_args()
    if args.save_init and not args.facts:
        ap.error('--save-init goes with --facts')
    if os.environ.get('CT_REAL_CLAUDE') != '1':
        print('skipped: set CT_REAL_CLAUDE=1 to run (uses the real claude CLI and your account)')
        return 0
    if not args.facts:
        return smoke()
    print(f'claude {subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()}')
    results = facts(args.save_init)
    for fact, verdict, detail in results:
        print(f'{ {True: "PASS", False: "FAIL", None: "UNKNOWN"}[verdict]:8}{fact:16}{detail}')
    print(f'{len(COST)} runs, ${sum(COST):.2f}')
    return 0 if all(v is True for _, v, _ in results) else 1


if __name__ == '__main__':
    sys.exit(main())
