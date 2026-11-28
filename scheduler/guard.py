#!/usr/bin/env python3
"""PreToolUse guard for unattended jobs (Claude Code hook).

Reads the hook event as JSON on stdin and exits with code 2 (block) when the call would
 * run a dangerous or outward-facing shell command,
 * read secrets,
 * write outside the vault, or inside the vault areas that jobs must not touch
   (.obsidian/, _system/templates/, CLAUDE.md).
Exit code 0 lets the call through. Standard library only.

Which commands and tools a job may use at all is decided by its permission rules (settings.json, `dontAsk` mode: anything
not allowed is refused). The guard is the second line: it refuses what no rule should ever let through.

Usage in a hook:  python3 guard.py --vault /path/to/vault
"""
import argparse
import fnmatch
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
# Areas that an unattended job must never modify. `.claude` and `.control-tower` matter most: the vault's Claude settings are loaded by
# the job runner, so a job able to edit them could widen its own permissions or hooks for the next run.
# `.git` matters as much: a hook or `core.fsmonitor` written there would run as the user at the next git command.
# The single source of these lists: installer/plan.py imports them (job deny rules, files a pack may never ship).
PROTECTED = ('.obsidian', '_system/templates', '_system/dashboards', '.claude', '.control-tower', '.control-tower-backup', '.git', '.github', '.vscode')
PROTECTED_FILES_CASED = ('CLAUDE.md', 'CLAUDE.local.md', '.mcp.json')
PROTECTED_FILES = tuple(f.lower() for f in PROTECTED_FILES_CASED)  # compared lowercase: macOS and Windows file systems
WRITE_TOOLS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}

# Jobs may not create git, Claude, editor or Obsidian files anywhere in the vault (a nested .git/config runs code at the next
# git command; a nested CLAUDE.md becomes instructions for later jobs).
NESTED_PROTECTED = {'.git', '.claude', '.obsidian', '.vscode', '.github', '.control-tower', '.control-tower-backup'}
NESTED_PROTECTED_FILES = {'claude.md', 'claude.local.md', '.mcp.json'}


def real(path):
    return os.path.realpath(os.path.expanduser(path))


def inside(path, root):
    path, root = real(path), real(root)
    return path == root or path.startswith(root + os.sep)

# ----------------------------------------------------------------------------- path policy (one place)
# Inside the vault, jobs must READ their own instructions: skills, adapter notes, pack rules. The rest of `.claude` (settings,
# local files) stays unreadable, and nothing under `.claude` is writable (PROTECTED above).
VAULT_READABLE = ('.claude/skills', '.claude/adapters', '.claude/rules')
# One list of secret names, judged per path segment (case-insensitive). `.config/gh` and `.config/gcloud` are two-segment names.
SECRET_NAMES = ('.env', '.env.local', '.env.production', '.netrc', '.npmrc', '.git-credentials', 'id_rsa', 'id_ed25519',
                'credentials', '.ssh', '.aws', '.gnupg', '.kube', '.docker', '.claude')
SECRET_SEGMENT = re.compile(r'^(\.env.*|\.netrc|\.npmrc|\.git-credentials|id_rsa.*|id_ed25519.*|credentials.*'
                            r'|\.ssh|\.aws|\.gnupg|\.kube|\.docker|\.claude)$', re.I)
SECRET_PAIRS = (('.config', 'gh'), ('.config', 'gcloud'))
GLOB_META = re.compile(r'[{}\[\]\\]')  # brace, bracket and backslash syntax can rebuild an escaping path: refused outright


def vault_rel(path, vault):
    """The ONLY way to get a vault-relative path: symlinks resolved, '/'-separated, lowercase. None when outside the vault."""
    p, v = real(path), real(vault)
    if p == v:
        return ''
    if not p.startswith(v + os.sep):
        return None
    return os.path.relpath(p, v).replace(os.sep, '/').lower()


def secret_segment(seg, wildcard=False):
    """A path segment that is, or (as a glob) could match, a secret name. Pure `*` / `**` are allowed."""
    if SECRET_SEGMENT.match(seg):
        return True
    if wildcard and re.search(r'[*?]', seg) and not re.fullmatch(r'\*+', seg):
        return any(re.match(fnmatch.translate(seg), n, re.I) for n in SECRET_NAMES)
    return False


def secret_in(segs):
    return any(secret_segment(x) for x in segs) or any(tuple(segs[i:i + 2]) == pair for pair in SECRET_PAIRS for i in range(len(segs)))


def read_reason(path, vault):
    """Read rule, shared by Read, the search root and the static prefix of a glob."""
    rel = vault_rel(path, vault)
    if rel is None:
        return f'jobs may only read inside the vault: {path}'  # blocks ~/.ssh, ~/.aws, ~/.claude, /etc... in one rule
    segs = [x for x in rel.split('/') if x]
    readable = any(rel == d or rel.startswith(d + '/') for d in VAULT_READABLE)
    if secret_in(segs[1:] if readable else segs):  # in a readable folder, `.claude` itself is not the secret
        return f'secret file: {path}'
    return None


def write_reason(path, vault):
    rel = vault_rel(path, vault)
    if rel is None:
        return f'write outside the vault: {path}'
    if rel in PROTECTED_FILES or any(rel == p or rel.startswith(p + '/') for p in PROTECTED):
        return f'jobs must not modify {rel}'
    segs = [x for x in rel.split('/') if x]
    if any(x in NESTED_PROTECTED for x in segs) or (segs and segs[-1] in NESTED_PROTECTED_FILES):
        # a nested .git/config can run code at the next git command; a nested CLAUDE.md becomes instructions for later jobs
        return f'jobs must not create git, Claude, editor or Obsidian files anywhere in the vault: {rel}'
    if secret_in([x for x in rel.split('/') if x]):
        return f'secret file: {path}'
    return None


def search_reason(tool, inp, event, vault):
    """Glob and Grep. The search root (path, else the hook's cwd) and the static prefix of the glob are real paths: they get the
    read rule. The wildcard tail is only names: each segment gets the secret check. Fails closed when no root is known."""
    base = inp.get('path') or event.get('cwd')
    if base and not os.path.isabs(os.path.expanduser(base)):  # relative to the job's directory, not the hook's
        base = os.path.join(event.get('cwd') or vault, base)
    if not base:
        return 'search root unknown: refusing to search'
    reason = read_reason(base, vault)
    if reason:
        return f'search root: {reason}'
    pat = inp.get('pattern') if tool == 'Glob' else inp.get('glob')
    if not pat:
        return None
    pat = str(pat)
    if GLOB_META.search(pat) or pat.startswith('~'):
        return f'glob syntax not allowed in jobs: {pat}'
    segments = [x for x in pat.split('/') if x]
    if '..' in segments:
        return f'pattern escapes the vault: {pat}'
    static = []
    for x in segments:
        if re.search(r'[*?]', x):
            break
        static.append(x)
    # always judged, even when empty: an absolute pattern that starts with a wildcard (`/**/x`) is rooted at `/`, outside the vault
    target = '/' + '/'.join(static) if pat.startswith('/') else os.path.join(base, *static)
    reason = read_reason(target, vault)
    if reason:
        return f'pattern {reason}: {pat}'
    if any(secret_segment(x, wildcard=True) for x in segments[len(static):]):
        return f'pattern targets a secret file: {pat}'
    return None


def own_tool_result(path, event):
    """Claude Code saves a large tool output under ~/.claude/projects/<project>/<session>/tool-results/ and the job then reads it
    back. Only that folder of THIS session is readable (not other sessions, not other projects)."""
    sid, transcript = str(event.get('session_id') or ''), str(event.get('transcript_path') or '')
    projects = real('~/.claude/projects')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,}', sid) or not transcript or not inside(transcript, projects):
        return False
    folder = os.path.join(os.path.dirname(real(transcript)), sid, 'tool-results')
    return inside(path, folder) and not os.path.islink(path)


def check(event, vault):
    """Return a human-readable reason when the call must be blocked, else None. One rule per tool family."""
    tool = event.get('tool_name', '')
    inp = event.get('tool_input') or {}
    if tool == 'Bash':
        cmd = str(inp.get('command', ''))
        for rx, reason in BASH_RULES:
            if re.search(rx, cmd, re.I):
                return f'{reason}: {cmd[:120]}'
        return None
    if tool in ('Glob', 'Grep'):
        if tool == 'Grep' and inp.get('path') and not inp.get('glob') and \
                own_tool_result(os.path.join(event.get('cwd') or vault, os.path.expanduser(str(inp['path']))), event):
            return None  # searching the job's own saved output
        return search_reason(tool, inp, event, vault)
    path = inp.get('file_path') or inp.get('notebook_path') or inp.get('path')
    if path and not os.path.isabs(os.path.expanduser(path)):  # relative to the job's directory, not the hook's
        path = os.path.join(event.get('cwd') or vault, path)
    if not path:
        return None
    if tool in WRITE_TOOLS:
        return write_reason(path, vault)
    if tool == 'Read':
        return None if own_tool_result(path, event) else read_reason(path, vault)
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
