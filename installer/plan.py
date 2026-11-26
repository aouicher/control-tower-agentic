#!/usr/bin/env python3
"""Install plan rules shared by install.py and doctor.py. Standard library only (Python 3.9+).

One place for:
  * packs: public ones in <repo>/packs, private ones listed in answers["pack_dirs"];
  * ids: pack, job and routine ids end up in file paths, so they are checked;
  * the core policy: which core files a private pack replaces or excludes (segment-aware patterns);
  * the files a pack may never ship into a vault;
  * the permissions a job may be granted (a private pack is written by someone else than the person installing it).
"""
import fnmatch
import json
import os
import re
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,62}$')
# vault paths no pack may ship: installer state, git internals, Obsidian config, Claude settings
FORBIDDEN_PACK_FILES = ('.control-tower', '.git', '.obsidian', '.claude/settings.json', '.claude/settings.local.json', '.mcp.json',
                        'CLAUDE.local.md')


class InstallError(Exception):
    pass


def jload(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def expand(path):
    return os.path.abspath(os.path.expanduser(path))


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


def resolve_packs(repo, answers=None):
    """{pack id: Pack}. Private means listed in answers["pack_dirs"]: decided by origin, not by path, so a symlink committed
    under packs/ stays public. Raises InstallError on a bad entry."""
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
        for j in pk.manifest.get('jobs', []):
            check_id(f'job (pack {pk.id})', j)
        for r in pk.manifest.get('routines', []):
            check_id(f'routine (pack {pk.id})', r)
    return packs


def pack_vault_files(pack):
    """Vault paths a pack installs ('.tmpl' stripped), '/'-separated."""
    base = os.path.join(pack.dir, 'vault')
    out = []
    for root, _, files in os.walk(base):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), base).replace(os.sep, '/')
            out.append(rel[:-5] if rel.endswith('.tmpl') else rel)
    return out


def check_pack_files(pack):
    for rel in pack_vault_files(pack):
        if any(path_match(rel, p) for p in FORBIDDEN_PACK_FILES):
            raise InstallError(f'pack "{pack.id}" may not ship {rel}: installer state, git, Obsidian and Claude settings are off limits')


# ----------------------------------------------------------------------------- core policy
def _segs_match(segs, pats):
    if not pats:
        return not segs
    if pats[0] == '**':
        return any(_segs_match(segs[i:], pats[1:]) for i in range(len(segs) + 1))
    return bool(segs) and fnmatch.fnmatchcase(segs[0], pats[0]) and _segs_match(segs[1:], pats[1:])


def path_match(rel, pattern):
    """Segment-aware glob: `*` never crosses '/', `**` spans folders, and a pattern naming a folder covers what is inside it.
    `*.base` is a root file; `_system/dashboards/*.base` or `**/*.base` reach further."""
    segs = [s for s in rel.replace(os.sep, '/').split('/') if s and s != '.']
    pats = [p for p in pattern.strip('/').split('/') if p]
    if not pats or '..' in pats:
        return False
    return any(_segs_match(segs[:k], pats) for k in range(1, len(segs) + 1))


class CorePolicy:
    """Core files a private pack replaces (it ships its own) or excludes (not installed at all)."""

    def __init__(self, replaces=(), excludes=()):
        self.replaces, self.excludes = list(replaces), list(excludes)

    @classmethod
    def from_packs(cls, packs):
        replaces, excludes = [], []
        for pk in packs:
            rep, exc = list(pk.manifest.get('replaces') or []), list(pk.manifest.get('excludes') or [])
            if (rep or exc) and not pk.private:
                raise InstallError(f'pack "{pk.id}": only private packs (answers["pack_dirs"]) may replace or exclude core files')
            for p in rep + exc:
                if p.startswith('/') or '..' in p.split('/'):
                    raise InstallError(f'pack "{pk.id}": pattern "{p}" must be a vault path such as _system/templates/daily.md')
            shipped = pack_vault_files(pk)
            for p in rep:
                if not any(path_match(rel, p) for rel in shipped):
                    raise InstallError(f'pack "{pk.id}" replaces "{p}" but ships no such file under vault/: add it, or use excludes')
            replaces += rep
            excludes += exc
        return cls(replaces, excludes)

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


def core_files(repo=REPO):
    base = os.path.join(repo, 'core', 'vault')
    out = []
    for root, _, files in os.walk(base):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), base).replace(os.sep, '/')
            out.append(rel[:-5] if rel.endswith('.tmpl') else rel)
    return out


# ----------------------------------------------------------------------------- job permissions
# A job's allow list may only add READ access to tools: the installer grants the vault write itself, and the guard plus
# `dontAsk` refuse the rest. Shells, interpreters and file or network commands would get around both.
SAFE_BARE = {'Read', 'Grep', 'Glob', 'TodoWrite', 'Skill'}
FORBIDDEN_COMMANDS = {
    'sh', 'bash', 'zsh', 'fish', 'dash', 'ksh', 'python', 'python3', 'node', 'deno', 'bun', 'perl', 'ruby', 'php', 'lua', 'env',
    'xargs', 'eval', 'exec', 'source', 'sudo', 'su', 'doas', 'curl', 'wget', 'nc', 'ncat', 'socat', 'ssh', 'scp', 'sftp', 'rsync',
    'cp', 'mv', 'rm', 'rmdir', 'mkdir', 'touch', 'tee', 'dd', 'chmod', 'chown', 'ln', 'install', 'osascript', 'open', 'npm', 'npx',
    'pnpm', 'yarn', 'pip', 'pip3', 'pipx', 'brew', 'apt', 'apt-get', 'docker', 'kubectl', 'helm', 'terraform', 'aws', 'gcloud', 'az',
    'make', 'crontab', 'launchctl', 'security', 'find', 'sed', 'awk', 'vi', 'vim', 'nano'}
READ_ONLY_SUBCOMMANDS = {'git': {'log', 'show', 'diff', 'status', 'rev-parse', 'shortlog', 'blame', 'ls-files'}}
MCP_TOOL = re.compile(r'^mcp__[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+$')


def permission_problem(rule):
    """Why `rule` may not be granted to an unattended job, or None."""
    rule = str(rule).strip()
    if rule in SAFE_BARE:
        return None
    if rule.startswith('mcp__'):
        return None if MCP_TOOL.match(rule) else 'MCP permissions must name one tool (mcp__<server>__<tool>), never a whole server or a wildcard'
    if re.fullmatch(r'Read\([^)]+\)', rule):
        return None
    if re.fullmatch(r'WebFetch\(domain:[A-Za-z0-9.-]+\)', rule):
        return None
    if re.match(r'(Edit|Write|MultiEdit|NotebookEdit)\b', rule):
        return 'jobs get write access to the vault from the installer; packs may not grant Edit or Write'
    m = re.fullmatch(r'Bash\((.+)\)', rule)
    if not m:
        return 'not an allowed job permission (allowed: Read, Grep, Glob, exact mcp__ tools, Bash(<read command> ...), WebFetch(domain:...))'
    body = m.group(1).strip()
    body = body[:-2] if body.endswith(':*') else body
    tokens = body.split()
    while tokens and re.fullmatch(r'[A-Z_][A-Z0-9_]*=\S*', tokens[0]):
        tokens.pop(0)  # VAR=value prefixes
    if not tokens or re.search(r'[*?\[\]{}$`|;&<>()\\]', tokens[0]):
        return 'Bash permissions must start with a fixed command name'
    cmd = os.path.basename(tokens[0])
    if cmd in FORBIDDEN_COMMANDS:
        return f'"{cmd}" can run code, write files or reach the network: not allowed in an unattended job'
    if cmd in READ_ONLY_SUBCOMMANDS and (len(tokens) < 2 or tokens[1] not in READ_ONLY_SUBCOMMANDS[cmd]):
        return f'only read-only {cmd} subcommands are allowed: {", ".join(sorted(READ_ONLY_SUBCOMMANDS[cmd]))}'
    if re.search(r'[;&|`$<>]', body):
        return 'Bash permissions may not contain shell operators'
    return None


def check_permissions(where, rules):
    problems = [f'{where}: "{r}": {p}' for r in rules for p in [permission_problem(r)] if p]
    if problems:
        raise InstallError('\n'.join(problems))
