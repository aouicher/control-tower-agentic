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
# Areas that an unattended job must never modify. `.claude` and `.control-tower` matter most: the vault's Claude settings are loaded by
# the job runner, so a job able to edit them could widen its own permissions or hooks for the next run.
# `.git` matters as much: a hook or `core.fsmonitor` written there would run as the user at the next git command.
# The single source of these lists: installer/plan.py imports them (job deny rules, files a pack may never ship).
PROTECTED = ('.obsidian', '_system/templates', '_system/dashboards', '.claude', '.control-tower', '.control-tower-backup', '.git', '.github', '.vscode')
PROTECTED_FILES_CASED = ('CLAUDE.md', 'CLAUDE.local.md', '.mcp.json')
PROTECTED_FILES = tuple(f.lower() for f in PROTECTED_FILES_CASED)  # compared lowercase: macOS and Windows file systems
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

# ----------------------------------------------------------------------------- job commands (one table, two uses)
# The installer only lets a pack grant these commands (installer/plan.py reads this table), and the guard below checks the
# ACTUAL arguments of every Bash call at run time: a permission such as `Bash(sort:*)` is a prefix, so the installer cannot see
# `sort -o ~/.zshrc` coming. For every command: path arguments must stay inside the vault, output redirection only to /dev/null.
#   subcommands: the first word(s) allowed after the command (installer check)
#   long / short: options refused at run time (`--output` also refuses `--output=x`; short ones also inside clusters like `-uo`)
#   no_global_options: no option between the command and its subcommand (`git -c core.pager=sh log`)
#   max_operands / value_options: commands whose extra operand is an OUTPUT file (`uniq in out`)
JOB_COMMANDS = {
    'date': {},  # checked by date_reason
    'ls': {},
    'wc': {'long': ('--files0-from',)},
    'sort': {'long': ('--output', '--compress-program', '--temporary-directory', '--files0-from'), 'short': 'oT'},
    'uniq': {'max_operands': 1, 'value_options': ('-f', '-s', '-w')},
    'cut': {},
    'tr': {},
    'column': {},
    'jq': {'long': ('--rawfile', '--slurpfile', '--from-file', '--args', '--jsonargs'), 'short': 'fL'},
    'git': {'subcommands': {'log', 'show', 'diff', 'status', 'rev-parse', 'shortlog', 'blame', 'ls-files'},
            'no_global_options': True,
            'long': ('--output', '--ext-diff', '--no-index', '--exec', '--exec-path', '--upload-pack', '--receive-pack', '--textconv')},
    'gh': {'subcommands': {'pr list', 'pr view', 'pr checks', 'pr diff', 'issue list', 'issue view', 'release list', 'release view',
                           'run list', 'run view', 'repo view', 'api'},
           'long': ('--method', '--field', '--raw-field', '--input', '--hostname'), 'short': 'XfF', 'no_operand': ('graphql',)},
}
UNSAFE_ENV = re.compile(r'^(PATH|HOME|SHELL|ENV|BASH_ENV|PAGER|EDITOR|VISUAL|PYTHON\w*|NODE\w*|PERL\w*|RUBY\w*|GIT_\w*|LD_\w*|'
                        r'DYLD_\w*|GH_\w*|SSH_\w*|\w*PROXY\w*)$', re.I)
SEPARATORS = {';', '&&', '||', '|', '&', '(', ')', '$(', '`', ';;', '|&'}
REDIRECTS = {'>', '>>', '>|', '&>', '<', '<<', '<<<', '<>'}


def path_like(arg):
    return arg.startswith(('/', '~')) or '..' in arg.replace('\\', '/').split('/')


def segment_reason(seg, vault):
    """One simple command (no separators): its environment prefix, command name and arguments."""
    while seg and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', seg[0]):
        if UNSAFE_ENV.match(seg[0].split('=', 1)[0]):
            return f'environment variable {seg[0].split("=", 1)[0]} can change what a command runs'
        seg = seg[1:]
    if not seg:
        return None
    cmd, args = seg[0], seg[1:]
    if '/' in cmd:
        return f'commands are called by name, not by path: {cmd}'
    rule = JOB_COMMANDS.get(cmd, {})
    i = 0
    if rule.get('no_global_options') and args and args[0].startswith('-'):
        return f'{cmd}: no option before the subcommand ({args[0]})'
    operands = []
    while i < len(args):
        a = args[i]
        if a in REDIRECTS:
            target = args[i + 1] if i + 1 < len(args) else ''
            if a.startswith('<'):
                if path_like(target) and not inside(os.path.join(vault, os.path.expanduser(target)), vault):
                    return f'reads outside the vault: {target}'
            elif target != '/dev/null':
                return 'output redirection: jobs write files with the Edit tool, inside the vault'
            i += 2
            continue
        if a.startswith('--'):
            name = a.split('=', 1)[0]
            if any(name == o or name.startswith(o) for o in rule.get('long', ())):
                return f'{cmd} {name}: writes a file, runs code or sends data'
        elif a.startswith('-') and len(a) > 1 and not a[1:].isdigit():
            flags, short = a[1:], rule.get('short', '')
            # `-o x`, `-ofile`, `-XPOST` start with the flag; `-uo` is a cluster of single-letter flags
            if flags[0] in short or (flags.isalpha() and set(flags) & set(short)):
                return f'{cmd} {a}: writes a file, runs code or sends data'
            if a in rule.get('value_options', ()):
                i += 2
                continue
        else:
            if a in rule.get('no_operand', ()):
                return f'{cmd} {a} is not allowed in jobs'
            if path_like(a) and cmd != 'gh' and not inside(os.path.join(vault, os.path.expanduser(a)), vault):
                return f'{cmd}: path outside the vault: {a}'
            operands.append(a)
        i += 1
    if 'max_operands' in rule and len(operands) > rule['max_operands']:
        return f'{cmd}: an extra operand is an output file'
    return None


def command_reason(cmd, vault):
    """Run-time check of every simple command in a Bash call. Fails closed on what it cannot parse."""
    if re.search(r'[`\n\r]|\$\(', cmd):
        return 'command substitution or several lines'
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ''
        tokens = list(lex)
    except ValueError:
        return 'cannot parse this command'
    seg = []
    for tok in tokens + [';']:
        if tok in SEPARATORS:
            reason = segment_reason(seg, vault)
            if reason:
                return reason
            seg = []
        else:
            seg.append(tok)
    return None


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
    if secret_in([x for x in rel.split('/') if x]):
        return f'secret file: {path}'
    return None


def search_reason(tool, inp, event, vault):
    """Glob and Grep. The search root (path, else the hook's cwd) and the static prefix of the glob are real paths: they get the
    read rule. The wildcard tail is only names: each segment gets the secret check. Fails closed when no root is known."""
    base = inp.get('path') or event.get('cwd')
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


def check(event, vault):
    """Return a human-readable reason when the call must be blocked, else None. One rule per tool family."""
    tool = event.get('tool_name', '')
    inp = event.get('tool_input') or {}
    if tool == 'Bash':
        cmd = str(inp.get('command', ''))
        for rx, reason in BASH_RULES:
            if re.search(rx, cmd, re.I):
                return f'{reason}: {cmd[:120]}'
        reason = date_reason(cmd) or command_reason(cmd, vault)
        return f'{reason}: {cmd[:120]}' if reason else None
    if tool in ('Glob', 'Grep'):
        return search_reason(tool, inp, event, vault)
    path = inp.get('file_path') or inp.get('notebook_path') or inp.get('path')
    if not path:
        return None
    if tool in WRITE_TOOLS:
        return write_reason(path, vault)
    if tool == 'Read':
        return read_reason(path, vault)
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
