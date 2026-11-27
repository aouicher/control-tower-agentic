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
import importlib.util
import re
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _load_guard():
    """scheduler/guard.py is copied standalone to the runtime; it is the single source of the protected paths and of the
    commands a job may run. Loaded by file so that importing plan does not change sys.path."""
    spec = importlib.util.spec_from_file_location('ct_guard', os.path.join(REPO, 'scheduler', 'guard.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard_rules = _load_guard()

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
    if not os.path.isdir(base):
        return out
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


NESTED_FORBIDDEN = {'.git', '.claude', '.obsidian', '.control-tower', '.mcp.json', '.github', '.vscode'}


def forbidden_pack_file(rel):
    """True for a vault path no pack may ship: anything the guard protects (except the shippable kinds above), and git, Claude
    or editor folders nested anywhere (`.claude/skills/x/.git/hooks/...`)."""
    protected = list(guard_rules.PROTECTED) + list(guard_rules.PROTECTED_FILES)
    if any(path_match(rel, p, ignore_case=True) for p in protected) and \
            not any(path_match(rel, p, ignore_case=True) for p in PACK_SHIPPABLE):
        return True
    return any(seg.casefold() in NESTED_FORBIDDEN for seg in rel.replace(os.sep, '/').split('/')[1:])


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


def check_pack(pk, trust=None):
    """Everything about one pack that can be checked before writing: ids, job ids, folders and symlinks, shipped files,
    core policy shape, and the tools its skills ask for."""
    root = os.path.realpath(pk.dir)
    def contained(path, what):
        if os.path.islink(path) or not (os.path.realpath(path) + os.sep).startswith(root + os.sep):
            raise InstallError(f'pack "{pk.id}": {what} must be a real folder or file inside the pack, not a symlink or a path outside')
    for sub in ('vault', 'jobs', 'routines'):  # a symlink would copy a file from anywhere on disk into the vault or the runtime
        top = os.path.join(pk.dir, sub)
        if os.path.lexists(top):
            contained(top, sub + '/')
        for base, dirs, files in os.walk(top):
            for n in dirs + files:
                if os.path.islink(os.path.join(base, n)):
                    raise InstallError(f'pack "{pk.id}": {os.path.relpath(os.path.join(base, n), pk.dir)} is a symlink: packs may not contain symlinks')
    if pk.manifest.get('vocabulary'):
        contained(os.path.join(pk.dir, pk.manifest['vocabulary']), 'vocabulary')
    for j in pk.manifest.get('jobs', []):
        check_id(f'job (pack {pk.id})', j)
        jp = os.path.join(pk.dir, 'jobs', j, 'job.json')
        if not os.path.isfile(jp) or not os.path.isfile(os.path.join(pk.dir, 'jobs', j, 'prompt.md.tmpl')):
            raise InstallError(f'pack "{pk.id}": jobs/{j} needs job.json and prompt.md.tmpl')
        if jload(jp).get('id', j) != j:
            raise InstallError(f'pack "{pk.id}": jobs/{j}/job.json has another id: it must equal the folder name')
    for r in pk.manifest.get('routines', []):
        check_id(f'routine (pack {pk.id})', r)
    shipped = vault_files(os.path.join(pk.dir, 'vault'))
    for rel in shipped:
        if forbidden_pack_file(rel):
            raise InstallError(f'pack "{pk.id}" may not ship {rel}: installer state, git, editor, Obsidian and Claude settings are off limits')
        if rel.casefold() == 'claude.md' and not pk.private:
            raise InstallError(f'pack "{pk.id}": only private packs may ship CLAUDE.md (public packs add rules in .claude/rules/)')
        if rel.casefold().endswith('.md'):  # raw text here; the rendered text is checked again by the installer (check_rendered)
            src = os.path.join(pk.dir, 'vault', rel)
            with open(src if os.path.isfile(src) else src + '.tmpl', encoding='utf-8', errors='replace') as fh:
                if TOOLS_KEY_ANYWHERE.search(fh.read()):
                    raise InstallError(f'pack "{pk.id}": {rel} mentions allowed-tools: pack files may not grant tools (use job permissions)')
    rep, exc = list(pk.manifest.get('replaces') or []), list(pk.manifest.get('excludes') or [])
    if (rep or exc) and not pk.private:
        raise InstallError(f'pack "{pk.id}": only private packs (answers["pack_dirs"]) may replace or exclude core files')
    for p in rep + exc:
        if p.startswith('/') or '..' in p.replace(os.sep, '/').split('/'):
            raise InstallError(f'pack "{pk.id}": pattern "{p}" must be a vault path such as _system/templates/daily.md')
    for p in rep:
        if not any(path_match(rel, p) for rel in shipped):
            raise InstallError(f'pack "{pk.id}" replaces "{p}" but ships no such file under vault/: add it, or use excludes')


# Skills may not grant themselves tools: `allowed-tools` would widen what a job can do while the skill runs. No YAML parsing:
# on the RENDERED file, a skill frontmatter may only use the keys below, one plain `key: value` per line (block lists only for
# none of them), and no file may mention allowed-tools in any spelling.
TOOLS_KEY_ANYWHERE = re.compile(r'allowed[\W_]{0,3}tools', re.I)
SKILL_KEYS = {'name', 'description', 'argument-hint', 'license', 'version'}


def rendered_text_problem(rel, text):
    """Why a rendered pack file may not be installed, or None."""
    text = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    if TOOLS_KEY_ANYWHERE.search(text):
        return 'mentions allowed-tools: pack files may not grant tools (use job permissions)'
    if not rel.casefold().endswith('skill.md'):
        return None
    m = re.match(r'---\n(.*?)\n---[ \t]*(\n|$)', text, re.S)
    if not m:
        return 'a skill needs a closed frontmatter (---) with name and description'
    for line in m.group(1).split('\n'):
        km = re.match(r'^([a-z][a-z-]*):[ \t](.*)$', line)
        if not km or km.group(1) not in SKILL_KEYS or '\\' in line:
            return f'skill frontmatter line not allowed: "{line[:60]}" (keys: {", ".join(sorted(SKILL_KEYS))}, one per line)'
    return None


def check_rendered(pk, render_text):
    """The same rules on the text that will actually be written, after {{ct.*}} tokens are filled in."""
    base = os.path.join(pk.dir, 'vault')
    for rel in vault_files(base):
        if not rel.casefold().endswith('.md'):
            continue
        src = os.path.join(base, rel)
        with open(src if os.path.isfile(src) else src + '.tmpl', encoding='utf-8', errors='replace') as fh:
            problem = rendered_text_problem(rel, render_text(fh.read(), rel))
        if problem:
            raise InstallError(f'pack "{pk.id}": {rel}: {problem}')


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
    trust = Trust.from_answers(answers or {})
    for pk in packs.values():
        check_pack(pk, trust)
    return packs


# ----------------------------------------------------------------------------- vault settings
# Unattended jobs run in the vault and load its project settings. Only these keys, with these values, cannot widen what a job
# does; anything else (allow rules, hooks, env, additionalDirectories, apiKeyHelper, enabled MCP servers...) is reported.
HARMLESS_SETTINGS = {'enabledMcpjsonServers': [], 'enableAllProjectMcpServers': False, '$schema': None}


def risky_settings(path):
    """Keys of a vault settings file that could widen unattended jobs ([] when harmless). Unreadable counts as risky."""
    try:
        data = jload(path)
    except (OSError, ValueError):
        return ['(unreadable)']
    if not isinstance(data, dict):
        return ['(not an object)']
    return sorted(k for k, v in data.items() if k not in HARMLESS_SETTINGS or (HARMLESS_SETTINGS[k] is not None and v != HARMLESS_SETTINGS[k]))


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
# Read/Grep/Glob to the vault, blocks secrets and checks the ACTUAL arguments of every Bash call against guard.JOB_COMMANDS. Here,
# a rule may only name an allowed tool or command: anything not listed is refused.
SAFE_TOOLS = {'Read', 'Grep', 'Glob', 'TodoWrite', 'Skill'}
SHELL_CHARS = re.compile(r'[;&|`$<>(){}\[\]\\\n\r"\']')
COMMAND_NAME = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
ENV_PREFIX = re.compile(r'^([A-Z_][A-Z0-9_]*)=(\S*)$')
MCP_TOOL = re.compile(r'^mcp__([A-Za-z0-9_.-]+?)__([A-Za-z0-9.-]+(?:_[A-Za-z0-9.-]+)*)$')
TRUST_PATTERNS = {'trusted_commands': COMMAND_NAME, 'trusted_env': re.compile(r'^[A-Z_][A-Z0-9_]*$'),
                  'trusted_mcp_tools': re.compile(r'^mcp__[A-Za-z0-9_.-]+$'), 'trusted_domains': re.compile(r'^[A-Za-z0-9.-]+$')}


@dataclass(frozen=True)
class Trust:
    """What the user (never a pack) trusts unattended jobs to use, from the answers: a company CLI, the variables it needs,
    exact MCP tools, web domains."""
    commands: tuple = ()
    env: tuple = ()
    mcp_tools: tuple = ()
    domains: tuple = ()

    @classmethod
    def from_answers(cls, answers, extra_mcp_tools=()):
        get = lambda k: tuple(answers.get(k) or ())
        return cls(get('trusted_commands'), get('trusted_env'), get('trusted_mcp_tools') + tuple(extra_mcp_tools), get('trusted_domains'))

    @staticmethod
    def problems(answers):
        out = []
        for key, rx in TRUST_PATTERNS.items():
            val = answers.get(key) or []
            if not isinstance(val, list) or not all(isinstance(x, str) and rx.match(x) for x in val):
                out.append(f'answers: "{key}" must be a list of plain names, for example ["twg"]')
        return out


def permission_problem(rule, trust=None):
    """Why `rule` may not be granted to an unattended job, or None."""
    trust = trust or Trust()
    rule = str(rule).strip()
    if '{{' in rule:
        return 'unrendered template token in a permission'
    if rule in SAFE_TOOLS or re.fullmatch(r'Read\([^()]+\)', rule):
        return None
    if rule.startswith('mcp__'):
        if not MCP_TOOL.match(rule) or '__' in rule.split('__', 2)[2]:
            return 'MCP permissions must name one tool (mcp__<server>__<tool>), never a whole server or a wildcard'
        return None if rule in trust.mcp_tools else 'MCP tool not trusted: list this exact tool in the answers under "trusted_mcp_tools"'
    m = re.fullmatch(r'WebFetch\(domain:([A-Za-z0-9.-]+)\)', rule)
    if m:  # a fetch can carry vault text in its URL: only domains the user trusts
        return None if m.group(1).lower() in [d.lower() for d in trust.domains] else \
            f'domain {m.group(1)} is not trusted: list it in the answers under "trusted_domains"'
    if re.match(r'(Edit|Write|MultiEdit|NotebookEdit)\b', rule):
        return 'jobs get write access to the vault from the installer; packs may not grant Edit or Write'
    m = re.fullmatch(r'Bash\((.+)\)', rule, re.S)
    if not m:
        return 'not an allowed job permission (allowed: Read, Grep, Glob, Bash(<allowed command> ...), trusted MCP tools and domains)'
    body = m.group(1).strip()
    if SHELL_CHARS.search(body):
        return 'Bash permissions may not contain shell operators, quotes or substitutions'
    tokens = (body[:-2] if body.endswith(':*') else body).split()
    while tokens and ENV_PREFIX.match(tokens[0]):
        name = ENV_PREFIX.match(tokens[0]).group(1)
        if name not in trust.env or guard_rules.UNSAFE_ENV.match(name):
            return f'environment variable {name} in a permission: declare it in the answers under "trusted_env" (never PATH, PAGER, GIT_*, LD_*...)'
        tokens.pop(0)
    if not tokens or not COMMAND_NAME.match(tokens[0]):
        return 'Bash permissions must start with a plain lowercase command name (no path, no quotes, no wildcard)'
    cmd, rest = tokens[0], tokens[1:]
    if cmd in trust.commands:
        return None
    rule_def = guard_rules.JOB_COMMANDS.get(cmd)
    if rule_def is None:
        return f'"{cmd}" is not an allowed job command; if you trust this tool, list it in the answers under "trusted_commands"'
    allowed = rule_def.get('subcommands')
    if allowed and ' '.join(rest[:1]) not in allowed and ' '.join(rest[:2]) not in allowed:
        return f'only these {cmd} subcommands are allowed: {", ".join(sorted(allowed))}'
    return None  # its arguments are checked at run time by the guard


def check_permissions(where, rules, trust=None):
    problems = [f'{where}: "{r}": {p}' for r in rules for p in [permission_problem(r, trust)] if p]
    if problems:
        raise InstallError('\n'.join(problems))
