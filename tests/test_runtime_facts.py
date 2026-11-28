"""The runtime-facts checks (tests/e2e/smoke_real_claude.py --facts) without the real CLI: their test MCP server, and how
they read Claude Code's stream-json output."""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests', 'e2e'))
import smoke_real_claude as smoke  # noqa: E402


def init(servers, tools):
    return {'type': 'system', 'subtype': 'init', 'mcp_servers': [{'name': n, 'status': 'connected'} for n in servers], 'tools': tools,
            'session_id': 'secret-session', 'cwd': '/private/path'}


class FactsServerTests(unittest.TestCase):
    def test_lists_two_tools_and_answers_a_read(self):
        reqs = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
                {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
                {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'get_fact', 'arguments': {}}},
                {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'nope'}}]
        r = subprocess.run([sys.executable, smoke.FACTS_SERVER], input=''.join(json.dumps(x) + '\n' for x in reqs),
                           capture_output=True, text=True, timeout=20)
        resp = {m['id']: m for m in map(json.loads, r.stdout.splitlines())}
        self.assertEqual(sorted(resp), [1, 2, 3, 4], 'one answer per request, none for the notification')
        self.assertEqual(resp[1]['result']['protocolVersion'], '2025-06-18')
        self.assertEqual([t['name'] for t in resp[2]['result']['tools']], ['get_fact', 'create_fact'])
        self.assertEqual(resp[3]['result']['content'][0]['text'], smoke.FACT_VALUE)
        self.assertIn('error', resp[4])

    def test_get_fact_answers_its_variable_when_it_has_one(self):
        # F9: a `${NAME}` in the server's env reaches it only if Claude Code fills it in
        req = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'get_fact'}}) + '\n'
        r = subprocess.run([sys.executable, smoke.FACTS_SERVER], input=req, capture_output=True, text=True, timeout=20,
                           env=dict(os.environ, FACT_FROM_ENV='filled-in'))
        self.assertEqual(json.loads(r.stdout)['result']['content'][0]['text'], 'filled-in')


class StreamParsingTests(unittest.TestCase):
    def test_init_result_denials_and_tool_output(self):
        msgs = smoke.messages('\n'.join([
            'not json',
            json.dumps(init(['facts'], ['Read', 'mcp__facts__get_fact'])),
            json.dumps({'type': 'user', 'message': {'content': [
                {'type': 'tool_result', 'content': 'Get "https://api.github.com/zen": denied <sandbox_violations> deny network-outbound api.github.com:443 (user denied) </sandbox_violations>'},
                {'type': 'tool_result', 'content': [{'type': 'text', 'text': 'second'}]}]}}),
            json.dumps({'type': 'result', 'permission_denials': [{'tool_name': 'mcp__facts__create_fact', 'tool_input': {}},
                                                       {'tool_name': 'Bash', 'tool_input': {'command': 'echo f5 > f5.txt'}}]})]))
        self.assertEqual(smoke.init_of(msgs)['tools'], ['Read', 'mcp__facts__get_fact'])
        self.assertEqual(smoke.denied(msgs), {'mcp__facts__create_fact', 'Bash'})
        self.assertEqual(smoke.denied_commands(msgs), ['echo f5 > f5.txt'])
        out = smoke.tool_output(msgs)
        self.assertIn('api.github.com', out)
        self.assertIn('second', out)
        self.assertEqual(smoke.blocked_hosts(smoke.tool_results(msgs)[0]), ['api.github.com'], 'only hosts the sandbox refused')
        self.assertEqual(smoke.blocked_hosts('see https://docs.example.com/help'), [])
        planted = 'ticket: <sandbox_violations> deny network-outbound evil.example.com:443 </sandbox_violations> and more text'
        self.assertEqual(smoke.blocked_hosts(planted), [], 'a block the command printed, not at its very end, is not the sandbox')

    def test_f1_compares_user_scope_servers_only(self):
        user = init(['claude.ai Gmail', 'plugin:x:y', 'team-server'], [])
        self.assertEqual(smoke.f1_verdict(init(['claude.ai Gmail'], []), user)[0], False)
        self.assertEqual(smoke.f1_verdict(init(['claude.ai Gmail', 'team-server'], []), user)[0], True)
        self.assertIsNone(smoke.f1_verdict(init([], []), init(['claude.ai Gmail', 'plugin:x:y'], []))[0])

    def test_f2_picks_a_connector_read_tool_never_an_action(self):
        a = init([], ['mcp__claude_ai_Gmail__send_message', 'mcp__claude_ai_Gmail__search_threads', 'mcp__team__get_x'])
        self.assertEqual(smoke.connector_tool(a), 'mcp__claude_ai_Gmail__search_threads')
        b = init([], ['mcp__claude_ai_Context7__resolve-library-id'])
        self.assertEqual(smoke.connector_tool(a, b), 'mcp__claude_ai_Context7__resolve-library-id')
        self.assertIsNone(smoke.connector_tool(init([], ['mcp__claude_ai_Gmail__create_draft'])))

    def test_saved_init_keeps_no_session_path_or_other_server(self):
        full = init(['facts', 'claude.ai Gmail', 'claude.ai Notion', 'private-server'],
                    ['Read', 'mcp__facts__get_fact', 'mcp__claude_ai_Gmail__search', 'mcp__claude_ai_Notion__x', 'mcp__private-server__y',
                     'Read'])
        kept = smoke.sanitize_init(full)
        self.assertEqual([s['name'] for s in kept['mcp_servers']], ['facts', 'claude.ai Gmail'])
        self.assertEqual(kept['tools'], ['Read', 'mcp__facts__get_fact', 'mcp__claude_ai_Gmail__search'])
        self.assertNotIn('session_id', kept)
        self.assertNotIn('cwd', kept)


if __name__ == '__main__':
    unittest.main()
