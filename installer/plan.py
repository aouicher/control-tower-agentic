#!/usr/bin/env python3
"""Install plan rules shared by install.py and doctor.py. Standard library only (Python 3.9+).

One place for:
  * packs: public ones in <repo>/packs, private ones listed in answers["pack_dirs"], fully checked when resolved;
  * ids: pack, job and routine ids end up in file paths;
  * the core policy: which core files a private pack replaces or excludes (segment-aware patterns);
  * the files a pack may never ship into a vault (derived from the guard's protected paths);
  * the permissions an unattended job may be granted: an ALLOW-list, because a pack is often written by someone else than the
    person installing it. Commands the user trusts (a company CLI) are declared in the answers, never by the pack.
"""
import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'scheduler'))
import guard as guard_rules  # noqa: E402  (standalone file copied to the runtime: the single source of protected paths)

ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,62}$')
# Under the guard's protected paths, packs may only ship skills, rules, templates, dashboards and (private packs) CLAUDE.md.
PACK_SHIPPABLE = ('.claude/skills', '.claude/rules', '_system/templates', '_system/dashboards', 'claude.md')


class InstallError(Exception):
    pass


def jload(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def expand(path):
    return os.path.abspath(os.path.expanduser(path))


def vault_files(base):
    """Vault paths a source folder installs: '/'-separated, '.tmpl' stripped. The one walk used by every check."""
    out = []
    for root, _, files in os.walk(base):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), base).replace(os.sep, '/')
            out.append(rel[:-5] if rel.endswith('.tmpl') else rel)
    return out


def core_files(repo=REPO):
    return vault_files(os.path.join(repo, 'core', 'vault'))


# ----------------------------------------------------------------------------- paths
def _segs_match(segs, pats):
    if not pats:
        return not segs
    if pats[0] == '**':
        return any(_segs_match(segs[i:], pats[1:]) for i in range(len(segs) + 1))
    return bool(segs) and fnmatch.fnmatchcase(segs[0], pats[0]) and _segs_match(segs[1:], pats[1:])


def path_match(rel, pattern, ignore_case=False):
    """Segment-aware glob: `*` never crosses '/', `**` spans folders, a pattern naming a folder covers what is inside it,
    `.` segments are ignored and `..` never matches. `ignore_case` for checks that protect files on macOS and Windows."""
    if ignore_case:
        rel, pattern = rel.casefold(), pattern.casefold()
    segs = [s for s in rel.replace(os.sep, '/').split('/') if s and s != '.']
    pats = [p for p in pattern.replace(os.sep, '/').split('/') if p and p != '.']
    if not pats or '..' in pats:
        return False
    return any(_segs_match(segs[:k], pats) for k in range(1, len(segs) + 1))


def forbidden_pack_file(rel):
    """True for a vault path no pack may ship: anything the guard protects, except the shippable kinds above."""
    protected = list(guard_rules.PROTECTED) + list(guard_rules.PROTECTED_FILES)
    return any(path_match(rel, p, ignore_case=True) for p in protected) and \
        not any(path_match(rel, p, ignore_case=True) for p in PACK_SHIPPABLE)


# ----------------------------------------------------------------------------- packs
@dataclass(frozen=True)
class Pack:
    id: str
    dir: str
    manifest: dict
    private: bool


def list_packs(repo=REPO):
    base = os.path.join(repo, 'packs')
    return sorted(d for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, 'pack.json'))) if os.path.isdir(base) else []


def check_id(kind, value):
    if not ID_RE.match(str(value)):
        raise InstallError(f'{kind} id "{value}" is not allowed: use lowercase letters, digits and "-" (it becomes a file name)')
    return value


def check_pack(pk):
    """Everything about one pack that can be checked before writing: ids, job ids, shipped files, symlinks, core policy shape."""
    for j in pk.manifest.get('jobs', []):
        check_id(f'job (pack {pk.id})', j)
        jp = os.path.join(pk.dir, 'jobs', j, 'job.json')
        if not os.path.isfile(jp):
            raise InstallError(f'pack "{pk.id}": jobs/{j}/job.json is missing')
        if jload(jp).get('id', j) != j:
            raise InstallError(f'pack "{pk.id}": jobs/{j}/job.json has another id: it must equal the folder name')
    for r in pk.manifest.get('routines', []):
        check_id(f'routine (pack {pk.id})', r)
    for sub in ('vault', 'jobs', 'routines'):  # a symlink would copy a file from anywhere on disk into the vault or the runtime
        for root, dirs, files in os.walk(os.path.join(pk.dir, sub)):
            for n in dirs + files:
                if os.path.islink(os.path.join(root, n)):
                    raise InstallError(f'pack "{pk.id}": {os.path.relpath(os.path.join(root, n), pk.dir)} is a symlink: packs may not contain symlinks')
    for rel in vault_files(os.path.join(pk.dir, 'vault')):
        if forbidden_pack_file(rel):
            raise InstallError(f'pack "{pk.id}" may not ship {rel}: installer state, git, editor, Obsidian and Claude settings are off limits')
    rep, exc = list(pk.manifest.get('replaces') or []), list(pk.manifest.get('excludes') or [])
    if (rep or exc) and not pk.private:
        raise InstallError(f'pack "{pk.id}": only private packs (answers["pack_dirs"]) may replace or exclude core files')
    for p in rep + exc:
        if p.startswith('/') or '..' in p.replace(os.sep, '/').split('/'):
            raise InstallError(f'pack "{pk.id}": pattern "{p}" must be a vault path such as _system/templates/daily.md')
    shipped = vault_files(os.path.join(pk.dir, 'vault'))
    for p in rep:
        if not any(path_match(rel, p) for rel in shipped):
            raise InstallError(f'pack "{pk.id}" replaces "{p}" but ships no such file under vault/: add it, or use excludes')


def resolve_packs(repo, answers=None):
    """{pack id: Pack}, every pack checked. Private means listed in answers["pack_dirs"]: decided by origin, not by path,
    so a symlink committed under packs/ stays public."""
    packs = {}
    for pid in list_packs(repo):
        d = os.path.join(repo, 'packs', pid)
        packs[pid] = Pack(check_id('pack', pid), d, jload(os.path.join(d, 'pack.json')), False)
    for raw in (answers or {}).get('pack_dirs') or []:
        d = expand(raw)
        mp = os.path.join(d, 'pack.json')
        if not os.path.isfile(mp):
            raise InstallError(f'answers: pack_dirs entry {raw} has no pack.json')
        manifest = jload(mp)
        pid = check_id('pack', manifest.get('id') or os.path.basename(d))
        if pid in packs:
            raise InstallError(f'answers: private pack "{pid}" ({raw}) has the same id as another pack: rename it in its pack.json')
        packs[pid] = Pack(pid, d, manifest, True)
    for pk in packs.values():
        check_pack(pk)
    return packs


# ----------------------------------------------------------------------------- core policy
class CorePolicy:
    """Core files a private pack replaces (it ships its own) or excludes (not installed at all)."""

    def __init__(self, replaces=(), excludes=()):
        self.replaces, self.excludes = list(replaces), list(excludes)

    @classmethod
    def from_packs(cls, packs):
        return cls([p for pk in packs for p in pk.manifest.get('replaces') or []],
                   [p for pk in packs for p in pk.manifest.get('excludes') or []])

    @classmethod
    def from_json(cls, data):
        data = data or {}
        return cls(data.get('replaces') or [], data.get('excludes') or [])

    def to_json(self):
        return {'replaces': self.replaces, 'excludes': self.excludes}

    def __bool__(self):
        return bool(self.replaces or self.excludes)

    def skips(self, rel):
        """The core copy of `rel` is not installed (the pack's version is, or nothing)."""
        return any(path_match(rel, p) for p in self.replaces + self.excludes)

    def excluded(self, rel):
        """`rel` is not in the vault at all."""
        return any(path_match(rel, p) for p in self.excludes)


# ----------------------------------------------------------------------------- job permissions
# What an unattended job may be granted, as an ALLOW-list. The installer grants the vault write itself; scheduler/guard.py confines
# Read/Grep/Glob to the vault and blocks secrets, so `Read(<path>)` here is not a way out. Anything not listed is refused.
SAFE_TOOLS = {'Read', 'Grep', 'Glob', 'TodoWrite', 'Skill'}
# Text tools for data a job already has (pipes such as `gh api ... | jq | sort | uniq -c`). No cat/head: files go through Read.
READ_COMMANDS = {'date', 'ls', 'wc', 'sort', 'uniq', 'jq', 'cut', 'tr', 'column'}
# Commands with read-only subcommands: the first word(s) after the command must be one of these.
READ_SUBCOMMANDS = {
    'git': {'log', 'show', 'diff', 'status', 'rev-parse', 'shortlog', 'blame', 'ls-files'},
    'gh': {'pr list', 'pr view', 'pr checks', 'pr diff', 'issue list', 'issue view', 'release list', 'release view', 'run list',
           'run view', 'repo view', 'api'},
}
# Options that make an allowed command write a file, run code or send data.
DANGEROUS_OPTIONS = re.compile(r'(^|\s)(-o|-c|-X|-f|-F|--output\S*|--ext-diff|--exec\S*|--upload-pack\S*|--config\S*|--method\S*|'
                               r'--field\S*|--raw-field\S*|--input\S*|--rawfile|--slurpfile|--from-file\S*)(?=\s|$|:)')
SHELL_CHARS = re.compile(r'[;&|`$<>(){}\[\]\\\n\r]')
COMMAND_NAME = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
ENV_PREFIX = re.compile(r'^([A-Z_][A-Z0-9_]*)=(\S*)$')
UNSAFE_ENV = re.compile(r'^(PATH|HOME|SHELL|ENV|BASH_ENV|PAGER|EDITOR|VISUAL|PYTHON\w*|NODE\w*|PERL\w*|RUBY\w*|GIT_\w*|LD_\w*|DYLD_\w*|'
                        r'GH_\w*|SSH_\w*|\w*PROXY\w*)$', re.I)
MCP_TOOL = re.compile(r'^mcp__([A-Za-z0-9_.-]+?)__([A-Za-z0-9_.-]+)$')
# MCP tool names that act rather than read; refused even on a trusted server
MCP_WRITE_VERB = re.compile(r'(^|[_-])(send|post|create|update|delete|remove|write|edit|merge|close|publish|upload|set|add|'
                            r'transition|comment|reply|react|move|archive|assign|invite|share|trigger|deploy)([_-]|$)', re.I)


def permission_problem(rule, trusted_commands=(), trusted_env=(), trusted_mcp_servers=(), trusted_domains=()):
    """Why `rule` may not be granted to an unattended job, or None. The trusted_* lists come from the user's answers (a company
    CLI such as `twg`, the variables it needs, the MCP servers and web domains a job may read), never from a pack."""
    rule = str(rule).strip()
    if '{{' in rule:
        return 'unrendered template token in a permission'
    if rule in SAFE_TOOLS:
        return None
    if rule.startswith('mcp__'):
        m = MCP_TOOL.match(rule)
        if not m:
            return 'MCP permissions must name one tool (mcp__<server>__<tool>), never a whole server or a wildcard'
        if m.group(1) not in trusted_mcp_servers:
            return f'MCP server "{m.group(1)}" is not trusted: list it in the answers under "trusted_mcp_servers"'
        if MCP_WRITE_VERB.search(m.group(2)):
            return f'"{m.group(2)}" looks like a tool that acts (send, create, update...): unattended jobs only read'
        return None
    if re.fullmatch(r'Read\([^()]+\)', rule):
        return None
    m = re.fullmatch(r'WebFetch\(domain:([A-Za-z0-9.-]+)\)', rule)
    if m:  # a fetch can carry vault text in its URL: only domains the user trusts
        return None if m.group(1).lower() in [d.lower() for d in trusted_domains] else \
            f'domain {m.group(1)} is not trusted: list it in the answers under "trusted_domains"'
    if re.match(r'(Edit|Write|MultiEdit|NotebookEdit)\b', rule):
        return 'jobs get write access to the vault from the installer; packs may not grant Edit or Write'
    m = re.fullmatch(r'Bash\((.+)\)', rule, re.S)
    if not m:
        return 'not an allowed job permission (allowed: Read, Grep, Glob, exact mcp__ tools, Bash(<read command> ...), WebFetch(domain:...))'
    body = m.group(1).strip()
    if SHELL_CHARS.search(body) or '"' in body or "'" in body:
        return 'Bash permissions may not contain shell operators, quotes or substitutions'
    body = body[:-2] if body.endswith(':*') else body
    tokens = body.split()
    while tokens and ENV_PREFIX.match(tokens[0]):
        name = ENV_PREFIX.match(tokens[0]).group(1)
        if name not in trusted_env or UNSAFE_ENV.match(name):
            return f'environment variable {name} in a permission: declare it in the answers under "trusted_env" (never PATH, PAGER, GIT_*, LD_*...)'
        tokens.pop(0)
    if not tokens or not COMMAND_NAME.match(tokens[0]):
        return 'Bash permissions must start with a plain lowercase command name (no path, no quotes, no wildcard)'
    cmd, rest = tokens[0], tokens[1:]
    if DANGEROUS_OPTIONS.search(' ' + ' '.join(rest)):
        return 'options that write files, run code or send data are not allowed (-o, -c, --output, --exec, --method, -f/-F...)'
    if cmd in READ_COMMANDS or cmd in trusted_commands:
        return None
    if cmd in READ_SUBCOMMANDS:
        allowed = READ_SUBCOMMANDS[cmd]
        if ' '.join(rest[:1]) in allowed or ' '.join(rest[:2]) in allowed:
            return None
        return f'only read-only {cmd} subcommands are allowed: {", ".join(sorted(allowed))}'
    return f'"{cmd}" is not an allowed read command; if you trust this tool, list it in the answers under "trusted_commands"'


def check_permissions(where, rules, **trust):
    problems = [f'{where}: "{r}": {p}' for r in rules for p in [permission_problem(r, **trust)] if p]
    if problems:
        raise InstallError('\n'.join(problems))
