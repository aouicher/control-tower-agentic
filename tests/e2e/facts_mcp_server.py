#!/usr/bin/env python3
"""A tiny stdio MCP server for the runtime-facts checks (tests/e2e/smoke_real_claude.py --facts). It touches nothing.

Two tools: `get_fact` (a read) answers FACT_VALUE, or the variable FACT_FROM_ENV when the server was started with one, so a
check can tell whether the call really ran and what its environment held; `create_fact` (an action) answers CREATED. Newline-delimited JSON-RPC on stdin/stdout, standard library only.
"""
import json
import os
import sys

FACT_VALUE = 'fact-value-7f3a'
TOOLS = [
    {'name': 'get_fact', 'description': 'Read the test fact.', 'inputSchema': {'type': 'object', 'properties': {}}},
    {'name': 'create_fact', 'description': 'Create a test fact (does nothing).', 'inputSchema': {'type': 'object', 'properties': {}}},
]


def answer(req):
    """The JSON-RPC response to one request, or None for a notification."""
    method, rid = req.get('method'), req.get('id')
    if rid is None:
        return None
    if method == 'initialize':
        version = (req.get('params') or {}).get('protocolVersion', '2025-06-18')
        result = {'protocolVersion': version, 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'facts', 'version': '1'}}
    elif method == 'tools/list':
        result = {'tools': TOOLS}
    elif method == 'tools/call':
        name = (req.get('params') or {}).get('name')
        text = {'get_fact': os.environ.get('FACT_FROM_ENV') or FACT_VALUE, 'create_fact': 'CREATED'}.get(name)
        if text is None:
            return {'jsonrpc': '2.0', 'id': rid, 'error': {'code': -32602, 'message': f'unknown tool {name}'}}
        result = {'content': [{'type': 'text', 'text': text}]}
    elif method == 'ping':
        result = {}
    else:
        return {'jsonrpc': '2.0', 'id': rid, 'error': {'code': -32601, 'message': f'unknown method {method}'}}
    return {'jsonrpc': '2.0', 'id': rid, 'result': result}


def main():
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except ValueError:
            continue
        resp = answer(req) if isinstance(req, dict) else None
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
