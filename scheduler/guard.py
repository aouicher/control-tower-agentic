#!/usr/bin/env python3
"""PreToolUse guard for unattended jobs (Claude Code hook).

Reads the hook event as JSON on stdin and exits with code 2 (block) when the call would
 * run a dangerous or outward-facing shell command,
 * read secrets,
 * write outside the vault, or inside the vault areas that jobs must not touch
   (.obsidian/, _system/templates/, CLAUDE.md).
Exit code 0 lets the call through. Standard library only.

Usage in a hook:  python3 guard.py --vault /path/to/vault
"""
import argparse
import json
import os
import re
import sys

BASH_RULES = [
    (r'\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR]', 'recursive delete'),
    (r'\bgit\s+(push|reset\s+--hard|clean|checkout\s+(-f|--force)|branch\s+-D|rebase|commit|merge)\b', 'git write operation'),
    (r'\bsudo\b', 'sudo'),
    (r'\b(curl|wget)\b[^|;&]*\|\s*(ba|z)?sh\b', 'pipe from the network to a shell'),
    (r'\bchmod\s+(-R\s+)?[0-7]*7[0-7]{2}\b', 'permissive chmod'),
    (r'\bdd\s+if=', 'raw disk write'),
    (r'\bmkfs\b', 'filesystem creation'),
    (r':\(\)\s*\{', 'fork bomb'),
    (r'\b(printenv|env)\s*($|[|;&>])', 'environment dump'),
    (r'(^|[\s/])\.env(\.[\w-]+)?\b', 'reads an .env file'),
    (r'\.ssh\b|id_(rsa|ed25519)|\.aws/credentials|\.netrc|\.npmrc|\.git-credentials|security\s+find-', 'reads credentials'),
    (r'\bgh\s+(pr|issue)\s+(create|merge|close|reopen|comment|edit|review|ready)\b', 'GitHub write (pull request or issue)'),
    (r'\bgh\s+(repo|release|workflow|secret|variable)\s+(create|delete|edit|run|set|remove)\b', 'GitHub write (repository)'),
    (r'\bgh\s+api\b.*(\s-X\b|--method|\s-f\s|\s-F\s|--field|--raw-field|--input)', 'GitHub API write'),
    (r'\baws\b.*\b(delete|terminate|put|create|update|modify|attach|detach|run-instances|stop|start-instances|invoke)\b[-\w]*', 'cloud write operation'),
    (r'\baws\s+s3(api)?\s+(rm|rb|mv|sync|cp|put-|delete-)', 'cloud storage write'),
    (r'\b(kubectl|helm)\s+(delete|apply|create|replace|patch|scale|rollout|install|upgrade|uninstall)\b', 'cluster write operation'),
    (r'\bterraform\s+(apply|destroy|import|state\s+rm)\b', 'infrastructure change'),
    (r'\bdocker\s+(rm|rmi|kill|system\s+prune|volume\s+rm)\b', 'container destruction'),
    (r'\b(mysql|psql|sqlite3)\b.*\b(drop|delete|truncate|update|insert|alter)\b', 'database write'),
]
READ_SECRET = re.compile(r'(^|/)(\.env(\.[\w-]+)?|\.netrc|\.npmrc|\.git-credentials|id_rsa|id_ed25519|credentials)$'
                         r'|/\.(ssh|aws|gnupg|kube|docker|config/gh|config/gcloud|claude)(/|$)', re.I)
# Areas that an unattended job must never modify. `.claude` and `.control-tower` matter most: the vault's Claude settings are loaded by
# the job runner, so a job able to edit them could widen its own permissions or hooks for the next run.
PROTECTED = ('.obsidian', '_system/templates', '_system/dashboards', '.claude', '.control-tower', '.control-tower-backup')
PROTECTED_FILES = ('claude.md', 'claude.local.md', '.mcp.json')
WRITE_TOOLS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}


def real(path):
    return os.path.realpath(os.path.expanduser(path))


def inside(path, root):
    path, root = real(path), real(root)
    return path == root or path.startswith(root + os.sep)


def check(event, vault):
    """Return a human-readable reason when the call must be blocked, else None."""
    tool = event.get('tool_name', '')
    inp = event.get('tool_input') or {}
    if tool == 'Bash':
        cmd = str(inp.get('command', ''))
        for rx, reason in BASH_RULES:
            if re.search(rx, cmd, re.I):
                return f'{reason}: {cmd[:120]}'
        return None
    if tool in ('Glob', 'Grep'):
        # path-like patterns can point anywhere even when `path` is absent or inside the vault
        pat = inp.get('pattern') if tool == 'Glob' else inp.get('glob')
        if pat and (str(pat).startswith(('/', '~')) or '..' in str(pat).replace('\\', '/').split('/')):
            return f'pattern escapes the vault: {pat}'
        if not inp.get('path') and event.get('cwd') and not inside(event['cwd'], vault):
            return f'search starts outside the vault: {event["cwd"]}'  # no path means the working directory
    path = inp.get('file_path') or inp.get('notebook_path') or inp.get('path')
    if not path:
        return None
    if tool in WRITE_TOOLS:
        if not inside(path, vault):
            return f'write outside the vault: {path}'
        rel = os.path.relpath(real(path), real(vault)).replace(os.sep, '/').lower()  # case-insensitive: macOS and Windows file systems
        if rel in PROTECTED_FILES or any(rel == p or rel.startswith(p + '/') for p in PROTECTED):
            return f'jobs must not modify {rel}'
    if tool in ('Read', 'Grep', 'Glob') and not inside(path, vault):
        return f'jobs may only read inside the vault: {path}'  # blocks ~/.ssh, ~/.aws, ~/.claude, /etc... in one rule
    if tool in WRITE_TOOLS or tool in ('Read', 'Grep', 'Glob'):
        if READ_SECRET.search(real(path)):
            return f'secret file: {path}'
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    args = ap.parse_args()
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)  # not a hook event: do not block
    reason = check(event, args.vault)
    if reason:
        print(f'BLOCKED by control-tower guard: {reason}', file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == '__main__':
    main()
