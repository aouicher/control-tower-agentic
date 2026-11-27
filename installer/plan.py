#!/usr/bin/env python3
"""Install plan rules shared by install.py and doctor.py. Standard library only (Python 3.9+).

One place for:
  * packs: public ones in <repo>/packs, private ones listed in answers["pack_dirs"], fully checked when resolved;
  * ids: pack, job and routine ids end up in file paths;
  * the core policy: which core files a private pack replaces or excludes (segment-aware patterns);
  * the files a pack may never ship into a vault (derived from the guard's protected paths);
  * the permissions an unattended job may never be granted, whether a pack or the user asks (permission_problem), and the
    plain-language summary the user consents to (describe_rules).
"""
import fnmatch
import hashlib
import json
import os
import importlib.util
import re
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _load_guard():
    """scheduler/guard.py is copied standalone to the runtime; it is the single source of the protected paths. Loaded by file so that importing plan does not change sys.path."""
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


_REQUIRED = object()


def jload(path, default=_REQUIRED):
    """A JSON file; with `default`, that value when the file does not exist."""
    if default is not _REQUIRED and not os.path.isfile(path):
        return default
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


# Folders a sandboxed command may also write to: a tool's own folder under a per-user log or cache root, never the root itself.
SANDBOX_WRITABLE = ('~/Library/Logs/', '~/Library/Caches/', '~/.cache/', '~/.local/state/')
WRITABLE = re.compile(r'^(~/Library/Logs|~/Library/Caches|~/\.cache|~/\.local/state)(/[A-Za-z0-9_-][A-Za-z0-9._-]*)+/?\Z')


def valid_host(host):
    """One exact public host name: no wildcard, no IP address, no local-only name (.local, .localhost, .internal)."""
    return (isinstance(host, str) and len(host) <= 253 and bool(HOST.fullmatch(host)) and all(len(x) <= 63 for x in host.split('.'))
            and not host.lower().endswith(('.local', '.localhost', '.internal')))


def job_meta_problem(meta):
    """The optional sandbox fields of a job.json: `network` (web hosts its commands reach) and `sandbox_allow_write`."""
    net, writable = meta.get('network', []), meta.get('sandbox_allow_write', [])
    if not isinstance(net, list) or not all(valid_host(h) for h in net):
        return '"network" must be a list of host names, for example ["api.github.com"]'
    if not isinstance(writable, list) or not all(isinstance(w, str) and WRITABLE.match(w) and '..' not in w.split('/') for w in writable):
        return f'"sandbox_allow_write" may only list a tool\'s own folder under {", ".join(SANDBOX_WRITABLE)}'
    return None


# Hosts and write folders of known command-line tools (measured with the real CLI, docs/design/runtime-facts.md), merged
# with the developer's own answers (`commands`), so a granted command can reach what it needs inside the sandbox.
COMMAND_KEYS = {'network', 'allow_write'}


def known_commands(repo=REPO):
    return jload(os.path.join(repo, 'adapters', 'commands.json'))


def command_problem(name, entry):
    """Why one `commands` answer is refused: `{name: {"network": [hosts], "allow_write": [per-user log or cache folders]}}`."""
    if not COMMAND_NAME.match(str(name)):
        return f'"commands": "{name}" is not a command name'
    if not isinstance(entry, dict) or set(entry) - COMMAND_KEYS:
        return f'"commands" "{name}" may only hold {sorted(COMMAND_KEYS)}'
    why = permission_problem(f'Bash({name}:*)')
    if why:
        return f'"{name}" can never be allowed: {why}'
    own = [w for w in entry.get('allow_write', []) if not (isinstance(w, str) and w.rstrip('/').rsplit('/', 1)[-1] == name
                                                           and w.rstrip('/').rsplit('/', 1)[0] + '/' in SANDBOX_WRITABLE)]
    if own:  # a command writes only in its own folder: ~/.cache/<name>, never another tool's (a code cache) or a deeper one
        return f'"commands" "{name}" may write only in its own folder, for example ~/.cache/{name}'
    return job_meta_problem({'network': entry.get('network', []), 'sandbox_allow_write': entry.get('allow_write', [])})


def command_needs(repo, answers, allow):
    """(hosts, write folders, macOS certificate flag) for the commands of these rules: the table plus the answers."""
    table, mine = known_commands(repo), answers.get('commands') or {}
    hosts, writable, weaker = [], [], False
    for rule in allow:
        parts = bash_parts(rule)
        if not parts:
            continue
        known, own = table.get(parts[1], {}), mine.get(parts[1], {})
        hosts += known.get('network', []) + own.get('network', [])
        writable += known.get('allow_write', []) + own.get('allow_write', [])
        weaker = weaker or bool(known.get('weaker_network_isolation'))
    return sorted(set(hosts)), sorted(set(writable)), weaker


DAYS = {'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6, 'sun': 0}
DAY_ALIASES = {'weekdays': 'mon-fri', 'weekends': 'sat-sun', 'daily': 'mon-sun', 'every day': 'mon-sun', '*': 'mon-sun'}


def parse_days(spec):
    """'mon-fri', 'mon,wed', 'weekdays', 'daily' -> cron weekday numbers (0 = Sunday). Raises ValueError with a readable message."""
    spec = DAY_ALIASES.get(spec.lower().strip(), spec.lower().strip())
    out = []
    def day(x):
        x = x.strip()[:3]
        if x not in DAYS:
            raise ValueError(f'unknown day "{x}" in "{spec}" (use mon, tue, wed, thu, fri, sat, sun, ranges like mon-fri, or weekdays)')
        return DAYS[x]
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            i, j = day(a), day(b)
            order = [1, 2, 3, 4, 5, 6, 0]
            ia, ib = order.index(i), order.index(j)
            out += order[ia:ib + 1] if ia <= ib else order[ia:] + order[:ib + 1]
        else:
            out.append(day(part))
    return sorted(set(out), key=lambda d: (d + 6) % 7)


def needs_host(answers, command, table):
    """True when nothing says which web addresses a command reaches: no host in the table, and no `network` answer ("it
    needs no web address" is recorded as an empty list)."""
    return not table.get(command, {}).get('network') and 'network' not in ((answers.get('commands') or {}).get(command) or {})


def check_pack(pk):
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
    if pk.id == MY_PACK:
        raise InstallError(f'pack id "{MY_PACK}" is kept for your own reports: choose another')
    for j in pk.manifest.get('jobs', []):
        check_id(f'job (pack {pk.id})', j)
        jp = os.path.join(pk.dir, 'jobs', j, 'job.json')
        if not os.path.isfile(jp) or not os.path.isfile(os.path.join(pk.dir, 'jobs', j, 'prompt.md.tmpl')):
            raise InstallError(f'pack "{pk.id}": jobs/{j} needs job.json and prompt.md.tmpl')
        meta = jload(jp)
        if meta.get('id', j) != j:
            raise InstallError(f'pack "{pk.id}": jobs/{j}/job.json has another id: it must equal the folder name')
        problem = job_meta_problem(meta)
        if problem:
            raise InstallError(f'pack "{pk.id}": jobs/{j}/job.json: {problem}')
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
    for pk in packs.values():
        check_pack(pk)
    return packs


def vault_settings_findings(vault):
    """(file, level, text) for the vault's Claude settings that could widen jobs: the runner refuses every job while
    .claude/settings.json does (jobs load it); .claude/settings.local.json only reaches the user's own sessions."""
    out = []
    for rel, level, effect in (('.claude/settings.json', 'FAIL', 'jobs load it, so none runs until it is empty; whoever added these '
                                'settings moves them to their user settings'),
                               ('.claude/settings.local.json', 'warn', 'keep it for your own sessions only')):
        keys = guard_rules.risky_settings(os.path.join(expand(vault), rel))
        if keys:
            out.append((rel, level, f'sets {", ".join(keys)}: {effect}'))
    return out


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
# Secure by default: a job may use only what its rules allow (`dontAsk` refuses the rest), and the person installing consents to
# those rules by answering a question (never by editing a file). Some rules can never be granted, whoever asks: they would let
# an unattended job run any code, write anywhere, or act on the user's behalf. scheduler/guard.py adds the run-time limits.
SAFE_TOOLS = {'Read', 'Grep', 'Glob', 'TodoWrite'}
SHELL_CHARS = re.compile(r'[;&|`$<>(){}\[\]\\\n\r"\']')
COMMAND_NAME = re.compile(r'^[a-z0-9][a-z0-9._-]{0,31}$')
MAX_RULE = 120  # with at most two variables, a rule stays one short line: it cannot carry a message to the person reading it
ENV_PREFIX = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)=(\S*)$')
SUBCOMMAND = re.compile(r'^[a-z][a-z-]{0,19}$')  # a subcommand word, not an argument (no digit, path, option or value)
MAX_SUBCOMMANDS = 3  # `twg jira workitem query`: enough for real tools, too short to carry a message to the reader
SERVER_CHARS = '[A-Za-z0-9_.-]'  # an MCP server name, as in mcp__<server>__<tool>
SERVER_NAME = re.compile(f'^{SERVER_CHARS}{{1,64}}$')
MCP_TOOL = re.compile(f'^mcp__({SERVER_CHARS}+?)__([A-Za-z0-9.-]+(?:_[A-Za-z0-9.-]+)*)$')
HOST = re.compile(r'^([A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]([A-Za-z0-9-]*[A-Za-z0-9])?$')  # a name, never an IP address
# shells, interpreters, wrappers that run another command, and tools that copy files or talk to the network by themselves
NEVER_COMMANDS = {'sh', 'bash', 'zsh', 'fish', 'dash', 'ksh', 'python', 'node', 'perl', 'ruby', 'php', 'osascript', 'curl', 'wget',
                  'nc', 'ncat', 'ssh', 'scp', 'sftp', 'rsync', 'cp', 'mv', 'rm', 'dd', 'tee', 'chmod', 'chown', 'sudo', 'su', 'env',
                  'xargs', 'eval', 'exec', 'command', 'source', 'timeout', 'nohup', 'nice', 'find', 'awk', 'sed', 'npx'}
# generic file readers: a job reads files with Read, Grep and Glob, which the guard keeps inside the vault; any of these could read
# a file anywhere (GNU `date -f FILE` too). Dates come in the prompt's Run context.
FILE_READERS = {'date', 'ls', 'cat', 'head', 'tail', 'less', 'more', 'grep', 'rg', 'strings', 'od', 'xxd', 'base64', 'tar', 'zip',
                'unzip', 'open', 'egrep', 'fgrep', 'zcat', 'zgrep', 'zless', 'zmore', 'bat', 'nl', 'tac',
                'gdate', 'gls', 'gcat', 'ghead', 'gtail', 'ggrep', 'gtar'}  # GNU coreutils as Homebrew names them
GIT_READ = {'log', 'show', 'diff', 'status', 'rev-parse', 'shortlog', 'blame', 'ls-files', 'describe'}
UNSAFE_ENV = re.compile(r'^(PATH|HOME|SHELL|ENV|BASH_ENV|PAGER|EDITOR|VISUAL|PYTHON\w*|NODE\w*|PERL\w*|RUBY\w*|GIT_\w*|LD_\w*|'
                        r'DYLD_\w*|GH_\w*|SSH_\w*|\w*PROXY\w*)$', re.I)
# an MCP tool whose name says it acts (sends, changes, deletes...) can carry vault text out or change the user's data
ACTION_WORDS = {'send', 'post', 'create', 'update', 'delete', 'remove', 'write', 'edit', 'merge', 'close', 'publish', 'upload',
                'comment', 'reply', 'react', 'transition', 'assign', 'invite', 'share', 'trigger', 'deploy',
                'add', 'set', 'manage', 'move', 'archive', 'respond', 'approve', 'submit', 'call', 'invoke', 'insert', 'upsert',
                'put', 'patch', 'save', 'cancel', 'drop', 'navigate', 'click', 'fill', 'draft', 'destructive', 'sql', 'evaluate', 'type',
                'press', 'kill', 'terminate', 'stop', 'start', 'restart', 'push', 'commit', 'import', 'apply', 'grant', 'revoke',
                'reset', 'purge', 'enable', 'disable', 'rename', 'replace'}
# not 'execute' or 'run': read queries use them (execute_log_insights_query); a tool named run_query is an accepted risk.
# These are also nouns: after a read verb they name what is read (get_commit, list_sql_warehouses, getJiraIssueType...),
# anywhere else they act (execute_sql, git_commit, pod_start, browser_type).
NOUN_ACTIONS = {'commit', 'start', 'draft', 'sql', 'type'}
# A list of action words is never complete: only a tool whose name starts with one of these is offered as recommended.
READ_VERBS = {'get', 'list', 'search', 'describe', 'read', 'fetch', 'query', 'find', 'view', 'show', 'lookup', 'count', 'analyze'}


def name_words(name):
    """`createIssue`, `create_issue`, `create-issue`, `issues.create` -> lowercase words."""
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', name))
    return [w.lower() for w in re.split(r'[\s_.\-]+', name) if w]


def bash_parts(rule):
    """`Bash(A=1 twg jira x:*)` -> (['A=1'], 'twg', ['jira', 'x']), or None when the rule is not a Bash rule with a body."""
    m = re.fullmatch(r'Bash\((.+)\)', str(rule).strip(), re.S)
    if not m:
        return None
    body = m.group(1).strip()
    tokens = (body[:-2] if body.endswith(':*') else body).split()
    env = []
    while tokens and ENV_PREFIX.match(tokens[0]):
        env.append(tokens.pop(0))
    return env, (tokens[0] if tokens else ''), tokens[1:]


def permission_problem(rule):
    """Why `rule` may never be granted to an unattended job (by a pack or by the user), or None when it is acceptable."""
    rule = str(rule).strip()
    if re.search(r'[^\x20-\x7e]', rule):  # a non-breaking or other unusual space would hide the real command from every check
        return 'a rule may only contain plain printable characters'
    if len(rule) > MAX_RULE:
        return f'a rule is at most {MAX_RULE} characters long'
    if '{{' in rule:
        return 'unrendered template token in a permission'
    if rule in SAFE_TOOLS or re.fullmatch(r'Read\([^()]+\)', rule):
        return None
    if re.match(r'Skill\b', rule):
        return 'a skill can bring its own tools; a job reads the skill file with Read and follows it'
    if re.match(r'(Edit|Write|MultiEdit|NotebookEdit)\b', rule):
        return 'jobs write only inside the vault, and the installer grants that itself'
    if rule.startswith('WebSearch'):
        return 'a web search can send your notes to any site'
    if rule.startswith('WebFetch'):
        m = re.fullmatch(r'WebFetch\(domain:([^()\s]+)\)', rule)
        return None if m and valid_host(m.group(1)) else 'web access is granted one site at a time (WebFetch(domain:host))'
    if rule.startswith('mcp__'):
        m = MCP_TOOL.match(rule)
        if not m or '__' in rule.split('__', 2)[2]:
            return 'MCP access is granted one tool at a time (mcp__<server>__<tool>), never a whole server or a wildcard'
        words = name_words(m.group(2))
        acts = sorted(set(words) & ACTION_WORDS - (NOUN_ACTIONS if words[:1] and words[0] in READ_VERBS else set()))
        return f'this tool acts on your behalf ({", ".join(acts)}): jobs only read' if acts else None
    if rule in ('Bash', 'Bash()') or not rule.startswith('Bash('):
        return 'not a job permission (jobs may use Read, Grep, Glob, one command, one MCP tool or one web site)'
    if not rule.endswith(')') or SHELL_CHARS.search(rule[5:-1]):
        return 'a command rule may not contain shell operators, quotes or substitutions'
    env, cmd, rest = bash_parts(rule)
    if len(env) > 2:
        return 'at most two variables before a command'
    for e in env:
        name = ENV_PREFIX.match(e).group(1)
        if UNSAFE_ENV.match(name):
            return f'the variable {name} can change which program runs'
    if not COMMAND_NAME.match(cmd):
        return 'a command rule must start with a plain command name (no path, no wildcard)'
    if cmd in FILE_READERS:
        return 'jobs read files with Read, Grep and Glob, which stay in the vault; dates are in the Run context'
    if cmd in NEVER_COMMANDS or re.sub(r'[0-9.]+$', '', cmd) in NEVER_COMMANDS:
        return f'"{cmd}" can run any code, copy files or reach the network by itself'
    if cmd == 'git' and (not rest or rest[0] not in GIT_READ):
        return f'jobs may only read git history ({", ".join(sorted(GIT_READ))})'
    return None


def check_permissions(where, rules):
    problems = [f'{where}: "{r}": {p}' for r in rules for p in [permission_problem(r)] if p]
    if problems:
        raise InstallError('\n'.join(problems))


def job_capabilities(meta):
    """(required, optional) capabilities of a job. A plain list means every capability is required."""
    caps = meta.get('capabilities', [])
    if isinstance(caps, dict):
        return list(caps.get('required', [])), list(caps.get('optional', []))
    return list(caps), []


def job_adapters(repo, answers, meta):
    """{capability: (tool, manifest)} for the job's capabilities whose tool is chosen."""
    tools = answers.get('tools') or {}
    return {c: (tools[c], jload(os.path.join(repo, 'adapters', c, tools[c] + '.json')))
            for c in sum(job_capabilities(meta), []) if tools.get(c, 'none') != 'none'}


def mcp_server(rule):
    """The server of an mcp__<server>__<tool> rule, or None for any other rule."""
    m = MCP_TOOL.match(str(rule))
    return m.group(1) if m else None


def on_server(rules, server):
    """MCP rules moved to the server name a job sees (recorded by configure.py connect); other rules unchanged."""
    return [f'mcp__{server}__{MCP_TOOL.match(r).group(2)}' if server and mcp_server(r) else r for r in rules]


def vault_servers(vault):
    """{name: entry} of the vault's .mcp.json; ValueError when the file is not valid JSON."""
    servers = jload(os.path.join(expand(vault), '.mcp.json'), {}).get('mcpServers') or {}
    if not isinstance(servers, dict):
        raise ValueError('"mcpServers" is not an object')
    return servers


def fingerprint(entry):
    """A hash of what a server entry runs."""
    return hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()


def recorded_servers(answers):
    """The MCP servers connected with configure.py: a known tool's (`servers`) or a connection's."""
    conns = answers.get('connections') or {}
    return set((answers.get('servers') or {}).values()) | {c['server'] for c in conns.values() if isinstance(c, dict) and 'server' in c}


def approved_servers(vault, answers, recorded):
    """{name: entry} of these connected servers whose .mcp.json entry is unchanged since they were connected."""
    prints = answers.get('fingerprints') or {}
    try:
        declared = vault_servers(vault) if recorded else {}
    except ValueError:
        return {}  # nothing starts from a file that cannot be read; the doctor says why
    return {s: declared[s] for s in sorted(recorded) if s in declared and prints.get(s) == fingerprint(declared[s])}


def connection_problem(cid, entry):
    """Why one `connections` answer is refused: {id: {"server": s} or {"command": c}, plus "read_tools": [its read rules]}, or
    {id: {"connector": "<claude.ai connector name>"}}, whose tools are chosen on claude.ai (only cloud reports use it)."""
    if not ID_RE.match(str(cid)):
        return f'"connections": "{cid}" is not an id (lowercase letters, digits and -)'
    keys = set(entry) if isinstance(entry, dict) else set()
    if keys not in ({'server', 'read_tools'}, {'command', 'read_tools'}, {'connector'}):
        return f'"connections" "{cid}" holds a "server" or a "command" and its "read_tools", or a claude.ai "connector" name'
    if keys == {'connector'}:
        return None if CONNECTOR_NAME.match(str(entry['connector'])) else f'"connections" "{cid}": "{entry["connector"]}" is not a connector name'
    rules, source = entry.get('read_tools'), entry.get('server') or entry.get('command')
    if not isinstance(rules, list) or not rules:
        return f'"connections" "{cid}": "read_tools" lists at least one tool'
    for r in rules:
        why = permission_problem(r) or (command_read_problem(r, source) if 'command' in entry
                                        else None if mcp_server(r) == source else f'not a tool of {source}')
        if why:
            return f'"connections" "{cid}": "{r}": {why}'
    return None


COMMAND_READS = READ_VERBS | {'status', 'diff', 'log', 'unread', 'history', 'info'}


def command_read_problem(rule, command):
    """Why a connection's command rule is not a read: the command, then 1 to MAX_SUBCOMMANDS subcommand words ending in a
    read (`gh pr list`; a group such as `gh pr` covers its actions too), no variable, and no action word before it."""
    env, cmd, words = bash_parts(rule) or ([], None, [])
    if cmd != command:
        return f'not a command of {command}'
    names = [x for w in words for x in name_words(w)]
    if env or not 0 < len(words) <= MAX_SUBCOMMANDS or not all(SUBCOMMAND.match(w) for w in words) or names[-1] not in COMMAND_READS:
        return f'a read rule is {command}, then 1 to {MAX_SUBCOMMANDS} subcommand words ending in a read: Bash({command} list:*)'
    acts = set(names[:-1]) & (ACTION_WORDS | {'api'}) - NOUN_ACTIONS
    return f'{", ".join(sorted(acts))} acts: jobs only read' if acts else None


def server_answer_problems(answers, capabilities):
    """What is wrong with the answers' record of connected MCP servers and connections (configure.py writes it)."""
    servers, prints, added = answers.get('servers') or {}, answers.get('fingerprints') or {}, answers.get('connections_added') or []
    conns, out = answers.get('connections') or {}, []
    if not isinstance(servers, dict) or not all(c in capabilities and SERVER_NAME.match(str(s)) for c, s in servers.items()):
        out.append('"servers" maps a capability to the MCP server name jobs see, for example {"tracker": "atlassian"}')
    if not isinstance(prints, dict) or not all(SERVER_NAME.match(str(s)) and re.fullmatch(r'[0-9a-f]{64}', str(h)) for s, h in prints.items()):
        out.append('"fingerprints" maps a connected MCP server to the hash of its .mcp.json entry')
    if not isinstance(added, list) or not all(SERVER_NAME.match(str(s)) for s in added):
        out.append('"connections_added" is a list of MCP server names')
    if not isinstance(conns, dict):
        return out + ['"connections" maps an id to {"server" or "command", "read_tools"} or {"connector"}']
    out += [f'"connections": "{c}" is the name of a capability: choose another id' for c in conns if c in capabilities]
    owned = list(servers.values() if isinstance(servers, dict) else [])
    owned += [c['server'] for c in conns.values() if isinstance(c, dict) and 'server' in c]
    out += [f'"{s}" is connected twice: one MCP server serves one tool or connection' for s in sorted({s for s in owned if owned.count(s) > 1})]
    return out + [p for cid, e in conns.items() for p in [connection_problem(cid, e)] if p]


def mcp_file_findings(vault, answers):
    """(level, text) about the vault's .mcp.json: unreadable, connected servers changed since, servers nobody connected."""
    recorded = recorded_servers(answers)
    try:
        declared = vault_servers(vault)
    except ValueError as exc:
        return [('FAIL' if recorded else 'warn', f'cannot be read ({exc}): reports start none of its servers')]
    out, changed, unused = [], sorted(recorded - set(approved_servers(vault, answers, recorded))), sorted(set(declared) - recorded)
    if changed:
        out.append(('FAIL', f'{", ".join(changed)} changed since connected (or is gone): reports do not use the new version; '
                            'connect it again in /control-tower, which shows what it now runs'))
    if unused:
        out.append(('warn', f'servers no report is connected to: {", ".join(unused)}; jobs do not start them, review what they run'))
    return out


DATE_COMMAND = re.compile(r'`date( [^`]*)?`')
MY_JOB_KEYS = {'skill', 'uses', 'model', 'runs_on'}  # when it runs is in `jobs`, as for every job
MY_REPORTS = 'journal/reports/my-'  # where the user's reports write: core/jobs/skill-job/prompt.md.tmpl
MY_PACK = 'my'  # the user's cloud reports are the routines `my--<id>`: no pack may take this id


def my_report_name(jid):
    """A report of the user's own, as named in its job, its routine and every message about it."""
    return f'Your report {jid}'
DEFAULT_SCHEDULE = {'days': 'mon-fri', 'time': '08:00'}  # a report of the user's own with no `jobs.<id>` time
CONNECTOR_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$')  # a claude.ai connector, as claude.ai shows it


def job_schedule(default, cfg):
    """A job's days and time: its default, with the answers' `jobs.<id>` days and time over it."""
    return {**default, **{k: v for k, v in (cfg or {}).items() if k in ('days', 'time')}}


def skill_problem(vault, skill):
    """Why a skill of the vault cannot run as a scheduled report, or None: the same closed frontmatter as pack skills, no
    allowed-tools, and a `date` command only after saying to use the Run context."""
    if not ID_RE.match(str(skill)):
        return f'"{skill}" is not a skill name (lowercase letters, digits and -)'
    rel = f'.claude/skills/{skill}/SKILL.md'
    path = os.path.join(expand(vault), rel)
    if not os.path.isfile(path):
        return f'no skill {skill} in this vault ({rel})'
    with open(path, encoding='utf-8', errors='replace') as fh:
        text = fh.read()
    m = DATE_COMMAND.search(text)
    if m and 'run context' not in text[:m.start()].lower():
        return 'it runs `date`: it must first say "if there is a Run context, use it"'
    return rendered_text_problem(rel, text)


def my_job_problems(answers, capabilities):
    """What is wrong with the user's scheduled skills: {id: {"skill", "uses": [known tools' capabilities or connections]}}."""
    mine, conns = answers.get('my_jobs') or {}, answers.get('connections') or {}
    if not isinstance(mine, dict):
        return ['"my_jobs" maps a report id to {"skill", "uses"}']
    out = []
    for jid, cfg in mine.items():
        if not ID_RE.match(str(jid)) or not isinstance(cfg, dict):
            out.append(f'"my_jobs": "{jid}" is not a report id with its {{"skill", "uses"}}')
            continue
        uses = cfg.get('uses', [])
        cloud = cfg.get('runs_on') == 'cloud'  # a routine on claude.ai reaches connectors, a job here the vault's servers and commands
        out += [f'"my_jobs" "{jid}": {m}' for bad, m in (
            (bool(set(cfg) - MY_JOB_KEYS), f'only {sorted(MY_JOB_KEYS)}'),
            (not ID_RE.match(str(cfg.get('skill'))), f'"{cfg.get("skill")}" is not a skill name'),
            (cfg.get('model', 'sonnet') not in ('haiku', 'sonnet', 'opus'), 'model is haiku, sonnet or opus'),
            (cfg.get('runs_on', 'computer') not in ('computer', 'cloud'), 'runs_on is computer or cloud'),
            (cloud and 'model' in cfg, 'a report on claude.ai runs with the routine\'s model, set there'),
            (not isinstance(uses, list) or not all(isinstance(u, str) and (u in capabilities or u in conns) for u in uses),
             '"uses" lists known tools\' capabilities and connection ids')) if bad]
        wrong = [u for u in (uses if isinstance(uses, list) else []) if isinstance(u, str) and isinstance(conns.get(u), dict)
                 and ('connector' in conns[u]) != cloud]
        if wrong:
            out.append(f'"my_jobs" "{jid}": {", ".join(wrong)} cannot be used by a report that runs '
                       + ('on claude.ai: only claude.ai connectors and known tools' if cloud else 'on this computer: claude.ai connectors run only in cloud reports'))
    return out


def eligible_jobs(ids, packs, tools):
    """Jobs whose capabilities all have a chosen tool."""
    jobs = []
    for p in ids:
        for j in packs[p].manifest.get('jobs', []):
            meta = jload(os.path.join(packs[p].dir, 'jobs', j, 'job.json'))  # ids checked by plan.check_pack
            req, opt = job_capabilities(meta)
            missing = [c for c in req if tools.get(c, 'none') == 'none']
            if not missing and not req and opt and not meta.get('vault_only') and all(tools.get(c, 'none') == 'none' for c in opt):
                missing = ['one of ' + ' / '.join(opt)]
            jobs.append({'pack': p, 'id': j, 'meta': meta, 'missing': missing, 'dir': os.path.join(packs[p].dir, 'jobs', j),
                         'tokens': {}, 'servers': set()})
    return jobs


SKILL_JOB = os.path.join(REPO, 'core', 'jobs', 'skill-job')
SKILL_JOB_DATES = 'Take every date and time from the Run context at the top of this prompt: never run `date` or `ls`, and find vault files with Glob.'
SKILL_ROUTINE_DATES = "Take today's date and time in that timezone once, at the start, and find vault files with Glob."
SKILL_ROUTINE_FINISH = (' Then, if the vault is a git repository attached to this routine, stage that file only (`git add -- <its path>`), '
                        'commit it and push it to its default branch; if any other file changed, commit nothing and say so in your final '
                        'answer, as you do if the push fails. On a linked computer it is written in place.')


def my_routines(answers):
    """The user's scheduled skills that run on claude.ai, as cloud routine entries like a pack routine's: the same skill-job
    prompt, the connectors of the known tools and connections it uses."""
    conns, tools, jobs, out = answers.get('connections') or {}, answers.get('tools') or {}, answers.get('jobs') or {}, []
    prompt = None
    for jid, cfg in sorted((answers.get('my_jobs') or {}).items()):
        if cfg.get('runs_on') != 'cloud' or (jobs.get(jid) or {}).get('enabled') is False:
            continue
        if prompt is None:
            with open(os.path.join(SKILL_JOB, 'prompt.md.tmpl'), encoding='utf-8') as fh:
                prompt = fh.read()
        caps = [u for u in cfg.get('uses', []) if u not in conns]
        meta = {'name': my_report_name(jid), **job_schedule(DEFAULT_SCHEDULE, jobs.get(jid)), 'connectors_required': caps, 'vault': 'write'}
        out.append({'pack': MY_PACK, 'id': jid, 'meta': meta, 'prompt': prompt, 'missing': [c for c in caps if tools.get(c, 'none') == 'none'],
                    'connectors': {u: conns[u]['connector'] for u in cfg.get('uses', []) if u in conns},
                    'tokens': {'job_id': jid, 'job_skill': cfg['skill'], 'job_dates': SKILL_ROUTINE_DATES, 'job_finish': SKILL_ROUTINE_FINISH}})
    return out


def my_jobs(answers):
    """The user's scheduled skills that run on this computer, as job entries like a pack job's: the generic skill-job prompt,
    the adapters of the known tools it uses (no tool chosen: the job is off) and the read tools and servers of its connections."""
    conns, tools, out = answers.get('connections') or {}, answers.get('tools') or {}, []
    for jid, cfg in sorted((answers.get('my_jobs') or {}).items()):
        if cfg.get('runs_on') == 'cloud':
            continue
        uses = cfg.get('uses', [])
        caps = [u for u in uses if u not in conns]
        meta = {'id': jid, 'name': my_report_name(jid), 'description': f'Runs the skill {cfg["skill"]}.',
                'schedule': dict(DEFAULT_SCHEDULE), 'model': cfg.get('model', 'sonnet'),
                'capabilities': {'required': caps, 'optional': []}, 'outputs': [f'{MY_REPORTS}{jid}-YYYY-MM-DD.md'],
                'permissions': {'allow': [r for u in uses if u in conns for r in conns[u]['read_tools']], 'deny': []}}
        out.append({'pack': None, 'id': jid, 'meta': meta, 'dir': SKILL_JOB, 'missing': [c for c in caps if tools.get(c, 'none') == 'none'],
                    'tokens': {'job_id': jid, 'job_skill': cfg['skill'], 'job_dates': SKILL_JOB_DATES, 'job_finish': ''},
                    'servers': {conns[u]['server'] for u in uses if 'server' in conns.get(u, {})}})
    return out


def adapter_allow(answers, cap, manifest):
    """The rules one capability gives a job: its adapter's, on the recorded server, plus the answers' `permissions` for it."""
    return on_server(manifest.get('permissions_allow', []), (answers.get('servers') or {}).get(cap)) + list((answers.get('permissions') or {}).get(cap, []))


def unreachable_servers(adapters, answers, allow, approved):
    """(capability, tool) of the job's MCP adapters it cannot call: no read tool allowed on an approved server, counting the
    capability's own rules and the job's MCP rules on a server no other adapter of the job uses."""
    rules = {c: adapter_allow(answers, c, man) for c, (_, man) in adapters.items()}
    out = set()
    for cap, (tool, man) in adapters.items():
        others = {mcp_server(r) for c in adapters if c != cap for r in rules[c]}
        own = {mcp_server(r) for r in rules[cap]} | ({mcp_server(r) for r in allow} - others)
        if man.get('access') == 'mcp' and not own & set(approved):
            out.add((cap, tool))
    return out


def connection_of(rule):
    """What a rule reaches, as shown to the user: the MCP server of a tool, the command of a Bash rule, or the site of a
    WebFetch rule (else None)."""
    key = connection_key(rule)
    return key[1].split(' ')[0] if key else None


def connection_key(rule):
    """What a rule reaches, as compared: ('mcp', server), ('cmd', command and its first subcommand word: `gh pr`, never all of
    `gh`) or ('web', host); None for any other rule. Kinds never match each other."""
    parts, m = bash_parts(rule), re.fullmatch(r'WebFetch\(domain:([^()]+)\)', str(rule))
    if mcp_server(rule):
        return ('mcp', mcp_server(rule))
    if parts and parts[1]:
        return ('cmd', ' '.join([parts[1]] + parts[2][:1]))
    return ('web', m.group(1).lower()) if m else None


def describe_rules(rules, network=()):
    """Plain-language summary of what rules let a job use: {'commands': [...], 'mcp_tools': [...], 'web': [...]}."""
    out = {'commands': [], 'mcp_tools': [], 'web': []}
    def add(key, text):
        if text not in out[key]:
            out[key].append(text)
    for r in rules:
        parts = bash_parts(r)
        if parts:
            env, cmd, rest = parts
            add('commands', ' '.join([cmd] + [w for w in rest if w != '*']))
        elif mcp_server(r):
            server, tool = MCP_TOOL.match(r).groups()
            add('mcp_tools', f'{" ".join(name_words(tool))} ({server})')
        elif re.fullmatch(r'WebFetch\(domain:[^()]+\)', str(r)):
            add('web', str(r)[len('WebFetch(domain:'):-1])
    for host in network:
        add('web', host)
    return out
