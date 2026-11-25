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
import fnmatch
import json
import os
import re
import shlex
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
    (r'\.ssh\b|id_(rsa|ed25519)|\.aws/credentials|\.netrc|\.npmrc|\.git-credentials|security\s+find-|\.config/gh\b|\.claude/|\.docker/config|\.kube/config|\.config/gcloud', 'reads credentials'),
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
# `.git` matters as much: a hook or `core.fsmonitor` written there would run as the user at the next git command.
PROTECTED = ('.obsidian', '_system/templates', '_system/dashboards', '.claude', '.control-tower', '.control-tower-backup', '.git', '.github', '.vscode')
PROTECTED_FILES = ('claude.md', 'claude.local.md', '.mcp.json')
# `date` is allowed to every job, so its arguments are allow-listed after shell tokenising: display formats and date
# arithmetic only. GNU `date -f FILE` / `-r FILE` would print a file's content or metadata, in any flag spelling.
DATE_FLAGS = re.compile(r'^(-u|--utc|-j|-R|-I\w*|--iso-8601(=\w+)?|--rfc-3339=\w+|-v[+-]?\w+|--date=.*)$')


def date_reason(cmd):
    """Refuse any `date` call whose arguments are not display formats or date arithmetic. Conservative on purpose."""
    if not re.search(r'\bdate\b', cmd):
        return None
    if re.search(r'[$`<>#\n\r]', cmd):  # substitution, redirection, comments, several lines: nothing a job needs around date
        return 'date combined with substitution, redirection, a comment or several lines'
    if re.search(r'\bdate\b[^|;&]*\s(-\w*[fr]\w*|--file|--reference)', re.sub(r'[\\\'"]', '', cmd)):  # fail-safe, quotes removed
        return 'date reading a file'
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ''
        tokens = list(lex)
    except ValueError:
        return 'cannot parse a command that calls date'
    seps = {';', '&&', '||', '|', '&', '(', ')', '$(', '`', ';;', '|&'}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok != 'date' and os.path.basename(tok) != 'date' and re.search(r'\bdate\b', tok):
            return 'date inside a quoted or nested command'  # sh -c "date ...", `date ...`, $(date...) glued to text
        if tok == 'date' or os.path.basename(tok) == 'date':
            i += 1
            while i < len(tokens) and tokens[i] not in seps:
                arg = tokens[i]
                if arg in ('-d', '--date'):
                    if i + 1 >= len(tokens) or tokens[i + 1] in seps or tokens[i + 1].startswith('-'):
                        return 'date -d needs a date expression'
                    i += 2
                    continue
                if not (arg.startswith('+') or DATE_FLAGS.match(arg)):
                    return f'date is limited to formats and date arithmetic, refused argument "{arg}"'
                i += 1
            continue
        i += 1
    return None


WRITE_TOOLS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}


def real(path):
    return os.path.realpath(os.path.expanduser(path))


def inside(path, root):
    path, root = real(path), real(root)
    return path == root or path.startswith(root + os.sep)

SECRET_NAMES = ('.env', '.env.local', '.env.production', '.netrc', '.npmrc', '.git-credentials', 'id_rsa', 'id_ed25519', 'credentials', '.ssh', '.aws', '.gnupg', '.kube', '.docker', '.claude')
GLOB_META = re.compile(r'[{}\[\]\\]')
SECRET_SEGMENT = re.compile(r'^(\.env.*|\.netrc|\.npmrc|\.git-credentials|id_rsa.*|id_ed25519.*|credentials.*|\.ssh|\.aws|\.gnupg|\.kube|\.docker|\.claude)$', re.I)


def search_scope_reason(tool, inp, event, vault):
    """Glob and Grep: the search root (path, else the hook's cwd) and the static prefix of the glob must stay inside the vault.

    Patterns are not judged by their text alone: brace, bracket and backslash syntax can rebuild a path that escapes, so they are refused
    outright. Fails closed when no search root can be worked out.
    """
    pat = inp.get('pattern') if tool == 'Glob' else inp.get('glob')
    base = inp.get('path') or event.get('cwd')
    if not base:
        return 'search root unknown: refusing to search'
    if not inside(base, vault):
        return f'search starts outside the vault: {base}'
    if not pat:
        return None
    pat = str(pat)
    if GLOB_META.search(pat):
        return f'glob syntax not allowed in jobs ({{ }} [ ] \\): {pat}'
    if pat.startswith('~'):
        return f'pattern escapes the vault: {pat}'
    segments = [x for x in pat.replace('\\', '/').split('/') if x]
    if any(x == '..' for x in segments):
        return f'pattern escapes the vault: {pat}'
    static = []
    for x in segments:
        if re.search(r'[*?]', x):
            break
        static.append(x)
    target = '/' + '/'.join(static) if pat.startswith('/') else os.path.join(base, *static)
    if not inside(target, vault):
        return f'pattern escapes the vault: {pat}'
    for x in segments:
        # a wildcard segment is refused when it could match a secret name (".*", "*env*", ".e*" ...), not only when it spells one
        if SECRET_SEGMENT.match(x) or (re.search(r'[*?]', x) and not re.fullmatch(r'\*+', x) and any(re.match(fnmatch.translate(x), n, re.I) for n in SECRET_NAMES)):
            return f'pattern targets a secret file: {pat}'
    return None


def check(event, vault):
    """Return a human-readable reason when the call must be blocked, else None."""
    tool = event.get('tool_name', '')
    inp = event.get('tool_input') or {}
    if tool == 'Bash':
        cmd = str(inp.get('command', ''))
        for rx, reason in BASH_RULES:
            if re.search(rx, cmd, re.I):
                return f'{reason}: {cmd[:120]}'
        reason = date_reason(cmd)
        if reason:
            return f'{reason}: {cmd[:120]}'
        return None
    if tool in ('Glob', 'Grep'):
        reason = search_scope_reason(tool, inp, event, vault)
        if reason:
            return reason
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
        reason = check(event, args.vault)
    except Exception as exc:  # fail closed: an event the guard cannot read is refused (exit 1 would let it through)
        print(f'BLOCKED by control-tower guard: cannot check this call ({type(exc).__name__})', file=sys.stderr)
        sys.exit(2)
    if reason:
        print(f'BLOCKED by control-tower guard: {reason}', file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == '__main__':
    main()
