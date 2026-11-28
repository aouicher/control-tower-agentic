#!/usr/bin/env python3
"""Control tower installer. Standard library only (Python 3.9+).

Installs the core vault, the chosen packs, the tool adapter notes, the scheduled jobs and (optionally)
the schedule, from an answers file. People who do not use a terminal install through Claude: the install skill
(`/install-control-tower`) asks four questions and writes the answers file.

    python3 installer/install.py --answers answers.json --dry-run     # show what would happen
    python3 installer/install.py --answers answers.json               # install
    python3 installer/install.py --match-tools "Jira, Amplitude" --packs marketing --json   # tool names to adapters

Safety:
  * it never overwrites an existing file; re-running is safe (existing files are kept);
  * it never edits your Claude Code or MCP configuration: the commands to run are written to
    <vault>/library/setup-next-steps.md;
  * it never loads a schedule unless --apply-schedule is given;
  * it seeds .obsidian/ only when the folder does not exist yet.
"""
import argparse
import datetime
import hashlib
import json
import os
import posixpath
import re
import shlex
import pwd
import shutil
import sys
import unicodedata

if sys.version_info < (3, 9):
    sys.exit('control tower needs Python 3.9 or newer (found %s)' % sys.version.split()[0])
import zoneinfo  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render  # noqa: E402
import translate  # noqa: E402
from toolnames import known_tools, match_tools  # noqa: E402
from scheduling import CRON_END, apply, cron_header, cron_line, launchd_plist, local_time, pick_scheduler, shift_days  # noqa: E402
from plan import (ID_RE, MY_PACK, MY_REPORTS, REPO, TOOLS_KEY_ANYWHERE, CorePolicy, InstallError,  # noqa: E402
                  adapter_allow, approved_servers, bash_parts, check_permissions, check_rendered, command_needs, command_problem, describe_rules, expand,
                  eligible_jobs, guard_rules, job_adapters, job_capabilities, job_schedule, jload, kit_commit, known_commands, list_packs, mcp_file_findings, mcp_server, my_job_problems, my_jobs, my_routines,
                  on_server, parse_days, permission_problem, recorded_servers, resolve_packs, server_answer_problems, unreachable_servers, vault_settings_findings,
                  EVERYWHERE_MARK, file_sha256, our_shortcut, remove_shortcut, tool_connection, user_skill_path, vault_files)

VERSION = '0.1.0'
CAPABILITIES = ['calendar', 'tracker', 'code', 'errors', 'quality', 'logs', 'analytics', 'crm']
BASE_ALLOW = ['Read', 'Grep', 'Glob']  # no command: dates come in the prompt's Run context, files are found with Glob
BASE_DENY = ['Agent', 'Skill']  # no sub-agent, and no skill that could bring its own tools: jobs read skill files with Read
PROTECTED_DIRS, PROTECTED_FILES_CASED = guard_rules.PROTECTED, guard_rules.PROTECTED_FILES_CASED  # one source: scheduler/guard.py
GUARD_MATCHER = 'Bash|Read|Edit|Write|MultiEdit|NotebookEdit|Grep|Glob'


def jdump(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write('\n')


def list_tools(capability, repo=REPO):
    d = os.path.join(repo, 'adapters', capability)
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith('.json')) if os.path.isdir(d) else []


# ----------------------------------------------------------------------------- answers
def system_name():
    """The user's full name as the computer knows it (the passwd entry's comment field), or ''."""
    try:
        return pwd.getpwuid(os.getuid()).pw_gecos.split(',')[0].strip()
    except KeyError:
        return ''


def system_timezone():
    """The computer's IANA timezone ($TZ, or the zone /etc/localtime points to), else UTC."""
    for name in (os.environ.get('TZ', '').lstrip(':'), os.path.realpath('/etc/localtime').partition('zoneinfo/')[2]):
        try:
            if name:
                zoneinfo.ZoneInfo(name)
                return name
        except (ValueError, zoneinfo.ZoneInfoNotFoundError):
            continue
    return 'UTC'


OWNER = ('owner_name', 'owner_handle', 'timezone')


def default_answers(detect=True):
    """The answers an answers file may leave out. With `detect`, the name, handle and timezone come from the computer; an
    empty name is asked."""
    name = system_name() if detect else ''
    first = unicodedata.normalize('NFKD', name.split()[0]).encode('ascii', 'ignore').decode().lower() if name.split() else ''
    first = re.sub(r'[^a-z0-9._-]', '', first)  # accents folded to plain letters first
    return {
        'owner_name': name, 'owner_handle': first or 'me', 'timezone': system_timezone() if detect else 'UTC', 'language': render.DEFAULTS['language'],
        'vault_path': '~/control-tower-vault', 'ct_home': '~/.control-tower',
        'packs': [], 'tools': {}, 'jobs': {}, 'scheduler': 'auto', 'claude_bin': 'claude',
    }


def unsafe_in_text(value):
    """Whether a path would change the text it is written into: a backtick, a control character or the end of a comment."""
    return any(ord(c) < 32 or c in '`\x7f' for c in value) or '-->' in value


def vault_path_problems(answers, repo=REPO):
    """Why the vault folder is refused: unattended jobs read the whole vault, so never the root, the home folder or a folder
    above it, nor one that holds the kit or the runtime folder."""
    if not answers.get('vault_path'):
        return []
    vault, home = os.path.realpath(expand(answers['vault_path'])), os.path.realpath(os.path.expanduser('~'))
    held = [p for p in (repo, answers.get('ct_home') or '~/.control-tower') if (os.path.realpath(expand(p)) + os.sep).startswith(vault + os.sep)]
    for key in ('vault_path', 'ct_home'):  # both are written into a personal skill every session loads
        if unsafe_in_text(str(answers.get(key) or '')):
            return [f'answers: "{key}" may not hold a backtick, a control character or "-->"']
    if vault == os.sep or (home + os.sep).startswith(vault + os.sep):
        return [f'answers: the vault cannot be {answers["vault_path"]}: reports would read everything in it. Choose a folder of its own']
    return [f'answers: the vault {answers["vault_path"]} would hold {held[0]}: choose a folder of its own'] if held else []


def language_problems(answers):
    """Why the vault's language is refused: it goes into every job prompt, so it is a name of at most three words in
    letters ("Deutsch", "Norsk bokmal"), never a sentence."""
    lang = answers.get('language')
    words = re.split(r"[ '-]", lang) if isinstance(lang, str) else []
    letters = all(w and unicodedata.category(w[0])[0] == 'L' and all(unicodedata.category(c)[0] in 'LM' for c in w) for w in words)
    if not (1 <= len(words) <= 3 and letters and len(lang) <= 30):  # marks too: Hindi, Thai
        return [f'answers: "language" must be the name of a language in letters, for example "Deutsch" (got {str(lang)[:40]!r})']
    return []


def merged_answers(answers):
    """The answers over the defaults. An owner field left out or empty takes what the computer gives, read only then."""
    a = default_answers(detect=not all(answers.get(k) for k in OWNER))
    a.update({k: v for k, v in answers.items() if not (k in OWNER and v in (None, ''))})
    return a


def validate(answers, repo=REPO):
    errors = []
    for key in OWNER + ('vault_path', 'packs'):
        if not answers.get(key):
            errors.append(f'answers: "{key}" is required')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', str(answers.get('owner_handle', 'x'))):
        errors.append('answers: "owner_handle" may only contain letters, digits, ".", "_" and "-"')
    tz = str(answers.get('timezone', ''))
    try:
        zoneinfo.ZoneInfo(tz)
    except Exception:
        errors.append(f'answers: unknown timezone "{tz}" (use an IANA name such as Europe/Paris)')
    packs = {}
    try:
        packs = resolve_packs(repo, answers)
        available = sorted(packs)
    except InstallError as exc:
        errors.append(str(exc))
        available = list_packs(repo)
    # trusted_* keys of older answers files are ignored: access is now granted per job (job_permissions), by answering questions
    grants = answers.get('job_permissions') or {}
    if not isinstance(grants, dict):
        errors.append('answers: "job_permissions" must be an object, for example {"morning-prs": ["Bash(twg jira:*)"]}')
        grants = {}
    for jid, rules in grants.items():
        if not ID_RE.match(str(jid)) or not isinstance(rules, list) or not all(isinstance(r, str) for r in rules):
            errors.append(f'answers: job_permissions "{jid}" must be a list of rules')
            continue
        errors += [f'answers: job_permissions "{jid}": "{r}": {p}' for r in rules for p in [permission_problem(r)] if p]
    errors += [f'answers: {p}' for p in server_answer_problems(answers, CAPABILITIES) + my_job_problems(answers, CAPABILITIES)]
    commands = answers.get('commands') or {}
    if not isinstance(commands, dict):
        errors.append('answers: "commands" must be an object, for example {"twg": {"network": ["acme.atlassian.net"]}}')
        commands = {}
    errors += [f'answers: {p}' for name, entry in commands.items() for p in [command_problem(name, entry)] if p]
    errors += vault_path_problems(answers, repo) + language_problems(answers)
    if not isinstance(answers.get('everywhere', False), bool):
        errors.append('answers: "everywhere" is true (/control-tower in every Claude session) or false')
    if answers.get('vault_mode', 'full') not in ('full', 'runtime'):
        errors.append('answers: "vault_mode" must be full or runtime')
    elif answers.get('vault_mode') == 'runtime' and answers.get('vault_path') and not os.path.isdir(expand(answers['vault_path'])):
        errors.append(f'answers: vault_mode "runtime" installs only the runtime on an EXISTING vault, and {answers["vault_path"]} does not exist')
    for p in answers.get('packs', []):
        if p not in available:
            errors.append(f'answers: unknown pack "{p}" (available: {", ".join(available)})')
    for cap, tool in (answers.get('tools') or {}).items():
        cid = tool_connection(answers, cap)
        if cap not in CAPABILITIES:
            errors.append(f'answers: unknown capability "{cap}"')
        elif cid is not None:
            conn = (answers.get('connections') or {}).get(cid)
            if not (isinstance(conn, dict) and ('server' in conn or 'command' in conn) and conn.get('read_tools')):
                errors.append(f'answers: "{cap}" uses {tool}, which is not one of your connections to an MCP server or a command of '
                              'this computer with read tools (a claude.ai connector serves only reports on claude.ai)')
            elif (answers.get('servers') or {}).get(cap) or (answers.get('permissions') or {}).get(cap):
                errors.append(f'answers: "{cap}" uses {tool}: its rules are the connection\'s, never "servers" or "permissions" for {cap}')
        elif tool != 'none' and tool not in list_tools(cap, repo):
            errors.append(f'answers: no adapter "{tool}" for capability "{cap}" (available: {", ".join(list_tools(cap, repo))}, none)')
    if answers.get('scheduler', 'auto') not in ('auto', 'launchd', 'cron', 'none'):
        errors.append('answers: "scheduler" must be auto, launchd, cron or none')
    if not isinstance(answers.get('packs', []), list):
        errors.append('answers: "packs" must be a list, for example ["marketing"]')
    if not isinstance(answers.get('tools') or {}, dict):
        errors.append('answers: "tools" must be an object, for example {"calendar": "google-calendar"}')
    jobs = answers.get('jobs') or {}
    if not isinstance(jobs, dict):
        errors.append('answers: "jobs" must be an object, for example {"morning-prs": {"time": "07:15"}}')
        jobs = {}
    for jid, cfg in jobs.items():
        if not isinstance(cfg, dict):
            errors.append(f'answers: job "{jid}" must be an object such as {{"time": "07:15", "days": "mon-fri"}}')
            continue
        t = cfg.get('time')
        if t is not None and not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', str(t)):
            errors.append(f'answers: job "{jid}" time must be HH:MM')
        if cfg.get('days') is not None:
            try:
                parse_days(str(cfg['days']))
            except ValueError as exc:
                errors.append(f'answers: job "{jid}": {exc}')
    if errors:
        raise InstallError('\n'.join(errors))
    return packs


# ----------------------------------------------------------------------------- plan
def vocab_files(repo, ids, packs):
    """Core vocabulary, then each chosen pack's. `packs` is the resolved {id: Pack} from plan.resolve_packs."""
    files = [os.path.join(repo, 'core', 'vocabulary.json')]
    for p in ids:
        if packs[p].manifest.get('vocabulary'):
            files.append(os.path.join(packs[p].dir, packs[p].manifest['vocabulary']))
    return files


def kit_texts(repo, ids, packs):
    """The text of each Markdown file and template of the core and the chosen packs: skills, rules, job prompts, routines."""
    for top in [os.path.join(repo, 'core')] + [packs[p].dir for p in ids]:
        for root, _, names in os.walk(top):
            for n in names:
                if n.endswith(('.md', '.tmpl')):
                    with open(os.path.join(root, n), encoding='utf-8', errors='replace') as fh:
                        yield fh.read()


def static_collisions(repo, ids, packs, policy):
    """Files that two sources would write to the same place (a pack colliding with the core or another pack).
    Core files that a private pack replaces or excludes are not counted."""
    seen, clash = {}, []
    def walk(src, label):
        for rel in vault_files(src):
            if rel.endswith('.gitkeep') or (label == 'core' and policy.skips(rel)):
                continue
            if rel in seen:
                clash.append(f'{rel} ({seen[rel]} and {label})')
            seen[rel] = label
    walk(os.path.join(repo, 'core', 'vault'), 'core')
    for p in ids:
        v = os.path.join(packs[p].dir, 'vault')
        if os.path.isdir(v):
            walk(v, 'pack ' + p)
    return clash


def read_routine(path):
    """Split a routine file into its frontmatter (dict) and the prompt (text under '## Prompt')."""
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    m = re.match(r'---\n(.*?)\n---\n', text, re.S)
    if not m or '\n## Prompt\n' not in text:
        raise InstallError(f'{path}: a routine needs a frontmatter and a "## Prompt" section')
    meta = {}
    for line in m.group(1).split('\n'):
        k, _, v = line.partition(':')
        v = v.strip()
        if v.startswith('[') and v.endswith(']'):
            v = [x.strip() for x in v[1:-1].split(',') if x.strip()]
        elif len(v) >= 2 and v[0] == v[-1] == '"':
            v = v[1:-1]
        meta[k.strip()] = v
    return meta, text.split('\n## Prompt\n', 1)[1].strip() + '\n'


def routine_missing(meta, tools):
    """The required connectors of a cloud routine that have no kit tool: none chosen, or the user's own connection, which only
    this computer reaches."""
    return [c for c in meta.get('connectors_required', []) if tools.get(c, 'none') == 'none' or tool_connection({'tools': tools}, c)]


def eligible_routines(ids, packs, tools):
    """Cloud routines of the chosen packs; a routine is offered only if its required connectors have a tool."""
    out = []
    for p in ids:
        for rid in packs[p].manifest.get('routines', []):
            meta, prompt = read_routine(os.path.join(packs[p].dir, 'routines', rid + '.md'))
            missing = routine_missing(meta, tools)
            out.append({'pack': p, 'id': rid, 'meta': meta, 'prompt': prompt, 'missing': missing, 'connectors': {}, 'tokens': {}})
    return out


def routine_cron(days, hhmm):
    """Cron expression in the user's own timezone (the routine is created with that timezone)."""
    h, m = map(int, hhmm.split(':'))
    return f"{m} {h} * * {','.join(str(d) for d in parse_days(days))}"


def connection_doc(capability, cid, entry):
    """How a report reaches a capability served by the user's connection: its source and read tools, then the vault's guide."""
    source = f"the MCP server `{entry['server']}`" if 'server' in entry else f"the command `{entry['command']}`"
    return (f'## Your tool: the connection {cid}\n\nThis capability uses {source}. A report may call only its read tools: '
            + ', '.join(f'`{r}`' for r in entry['read_tools']) + f'.\n\nHow to query it for this vault is in `.claude/adapters/{capability}-guide.md`: '
            'read it before the first call. If that file is missing, query nothing and say in the report that the guide is missing.\n')


def adapter_doc(repo, capability, tool, answers):
    with open(os.path.join(repo, 'adapters', capability, 'contract.md'), encoding='utf-8') as fh:
        contract = fh.read()
    cid = tool_connection(answers, capability)
    if cid:
        doc = connection_doc(capability, cid, answers['connections'][cid])
    else:
        with open(os.path.join(repo, 'adapters', capability, tool + '.md'), encoding='utf-8') as fh:
            doc = fh.read()
    return (f'<!-- Installed by control-tower {VERSION}: capability {capability}, tool {tool}. '
            f'Jobs and skills read this file to know how to query the tool. -->\n\n'
            f'# {capability.capitalize()} adapter: {tool}\n\n## Contract\n\n{contract}\n\n---\n\n{doc}\n')


def allow_hint(answers):
    """How to allow a job's read tools: the vault skill, or (runtime-only installs, no kit skill in the vault) the commands."""
    if answers.get('vault_mode') == 'runtime':
        return (f'run `python3 {REPO}/installer/configure.py denials --vault {answers["vault_path"]}` after a scheduled run, then '
                '`configure.py grant --vault <vault> --job <id> --rule <rule>` for each read tool to allow')
    return 'in Claude, in your vault, say "connect" and the name of the tool'


def next_steps(repo, answers, jobs_on, jobs_off, routines=(), mcp_blocked=()):
    lines = ['---', 'title: "Setup next steps"', f'date: {datetime.date.today().isoformat()}', 'tags: [setup]',
             'type: resource', 'status: active', '---', '', '# Setup next steps', '',
             'The installer created your vault, jobs and notes. A few things must be done by you, because they change your own '
             'Claude Code or Obsidian configuration, which the installer never touches.', '',
             '## 1. Obsidian', '',
             '- Open this folder as a vault in Obsidian.',
             '- Settings > Community plugins > turn on community plugins, then install **Tasks** (required by the dashboards).',
             '- Settings > Core plugins: make sure **Bases**, **Templates** and **Daily notes** are enabled.',
             '- Optional: install **Iconize** for folder icons.', '',
             '## 2. Connect your tools', '']
    any_tool = False
    for cap, tool in sorted((answers.get('tools') or {}).items()):
        if tool == 'none':
            continue
        any_tool = True
        if tool_connection(answers, cap):
            lines += [f'### {cap}: your connection {tool_connection(answers, cap)}', '', f'Reports that need {cap} use it. How to query it is in '
                      f'`.claude/adapters/{cap}-guide.md`; in Claude, in your vault, say: check my setup, to know whether it is there.', '']
            continue
        man = jload(os.path.join(repo, 'adapters', cap, tool + '.json'))
        lines += [f'### {cap}: {tool}', '', f"Official documentation: {man['setup_url']}", '']
        if man.get('setup_steps'):  # steps that are not shell commands (for example a connector made in the tool's own UI)
            lines += ['Steps:', ''] + [f'{i}. {step}' for i, step in enumerate(man['setup_steps'], 1)] + ['']
        if man.get('connect') == 'sign-in':
            lines += [f'In Claude, in your vault, say: connect {tool}. Claude adds it to this vault, and you sign in in your browser.', '']
        else:
            if man.get('install'):
                lines += ['Set up once by someone comfortable with the terminal, from the vault folder (a key stays in the environment):',
                          '', '```bash'] + man['install'] + ['```', '']
            if man.get('access') == 'mcp':
                lines += [f'Once it is set up, in Claude, in your vault, say: connect {tool}.', '']
        if man.get('env'):
            lines += ['Environment variables to set: ' + ', '.join(f'`{e}`' for e in man['env']), '']
        if not man.get('read_only', True):
            lines += [f"> Read-only caution: {man.get('read_only_mitigation', '')}", '']
        if (cap, tool) in mcp_blocked:
            lines += [f'> Scheduled reports cannot use this tool until it is connected with read tools allowed: {allow_hint(answers)}.', '']
        lines += [f"Check the connection: {man['verify']}", '']
    if not any_tool:
        lines += ['No external tool was selected: the vault works on its own.', '']
    lines += ['## 3. Scheduled jobs', '']
    if jobs_on:
        lines += ['Installed jobs: ' + ', '.join(f"`{j['id']}`" for j in jobs_on) + '. Test one by hand with:', '',
                  '```bash', f"python3 {answers['ct_home']}/bin/run_job.py --job {jobs_on[0]['id']} --ct-home {answers['ct_home']}", '```', '']
    for j in jobs_off:
        lines.append(f"- `{j['id']}` was not installed: no tool chosen for {', '.join(j['missing'])}.")
    lines += ['', '## 4. Cloud routines (optional)', '']
    if routines:
        lines += ['Cloud routines run on a schedule from claude.ai. Those that write notes need to reach this vault: link this computer '
                  'to the routine (simplest; the computer must be on at that time), or attach the vault\'s GitHub repository '
                  '(runs even when the computer is off). See docs/scheduling.md. Available for your answers:', '',
                  '| Routine | When |', '|---|---|'] + [f"| {r['name']} | {r['days']} at {r['time']} |" for r in routines] + [
                  '', 'To create them, start Claude Code in the control tower repository and run `/install-control-tower routines`: '
                  'it proposes each routine and creates only the ones you accept. Or paste a prompt by hand from '
                  f"`{answers['ct_home']}/routines/<name>.prompt.md` into a new routine on claude.ai.", '']
    else:
        lines += ['No cloud routine is available for the tools you chose.', '']
    lines += [
              '## 5. Health check', '', '```bash', f"python3 {shlex.quote(os.path.join(repo, 'installer', 'doctor.py'))} --vault {shlex.quote(answers['vault_path'])} --ct-home {shlex.quote(answers['ct_home'])}", '```', '']
    return '\n'.join(lines)


WIDE_PAGES_CSS = '''/* control tower: wider pages so dashboards and report tables fit. Settings > Appearance > CSS snippets to turn off. */
.markdown-source-view.mod-cm6 .cm-sizer,
.markdown-preview-view .markdown-preview-sizer {
  max-width: 1200px;
  margin-inline: auto;
}
'''


def obsidian_seed(vault):
    cfg = os.path.join(vault, '.obsidian')
    if os.path.exists(cfg):
        return []
    files = {
        'app.json': {'attachmentFolderPath': '_system/attachments', 'newFileLocation': 'folder', 'newFileFolderPath': '_inbox',
                     'alwaysUpdateLinks': True, 'userIgnoreFilters': ['_system/attachments/', '_system/archive/', '.claude/'],
                     # dashboards and report tables need width: Obsidian's readable line length would override the snippet below;
                     # every page carries its own title, so no file name ("today") is shown above it
                     'readableLineLength': False, 'showInlineTitle': False},
        'appearance.json': {'enabledCssSnippets': ['wide-pages']},
        'daily-notes.json': {'folder': 'journal/daily', 'format': 'YYYY/YYYY-MM-DD', 'template': '_system/templates/daily'},
        'templates.json': {'folder': '_system/templates'},
        'core-plugins.json': {'file-explorer': True, 'global-search': True, 'switcher': True, 'graph': True, 'backlink': True,
                              'outgoing-link': True, 'tag-pane': True, 'properties': True, 'page-preview': True,
                              'daily-notes': True, 'templates': True, 'command-palette': True, 'bases': True, 'outline': True},
    }
    for name, data in files.items():
        jdump(os.path.join(cfg, name), data)
    os.makedirs(os.path.join(cfg, 'snippets'), exist_ok=True)
    with open(os.path.join(cfg, 'snippets', 'wide-pages.css'), 'w', encoding='utf-8') as fh:
        fh.write(WIDE_PAGES_CSS)
    return ['.obsidian/' + n for n in files] + ['.obsidian/snippets/wide-pages.css']


# ----------------------------------------------------------------------------- jobs and schedule
def abs_rule(tool, path):
    """Permission rule for an absolute path: Claude Code reads `//abs/path` as absolute, `/path` as relative to the settings file."""
    return f'{tool}(/{path})' if path.startswith('/') else f'{tool}({path})'


def fix_rule(rule):
    """Upgrade `Edit(/abs/...)` written by a pack to the absolute form `Edit(//abs/...)`."""
    m = re.fullmatch(r'(Edit|Write|Read|MultiEdit)\((/[^/].*)\)', rule)
    return f'{m.group(1)}(/{m.group(2)})' if m else rule


def declared_rules(repo, answers, meta):
    """What a job declares it uses: (allow, deny, network hosts) from its own job.json (a pack's, or a report's sources), the
    chosen tools' adapters and the answers' per-capability `permissions`; never what the user granted it later."""
    allow = [fix_rule(p) for p in meta['permissions'].get('allow', [])]
    deny = [fix_rule(p) for p in meta['permissions'].get('deny', [])]
    network = list(meta.get('network', []))
    for cap, (_, man) in job_adapters(repo, answers, meta).items():
        allow += adapter_allow(answers, cap, man)
        deny += on_server(man.get('permissions_deny', []), (answers.get('servers') or {}).get(cap))
        network += man.get('network', [])
    return allow, deny, network


def job_rules(repo, answers, job):
    """What one job may use beyond the base rules: (allow, deny, network hosts), what it declares plus what the user granted
    it (`job_permissions`), with the hosts its commands reach."""
    allow, deny, network = declared_rules(repo, answers, job['meta'])
    allow += list((answers.get('job_permissions') or {}).get(job['id'], []))
    return allow, deny, network + command_needs(repo, answers, allow)[0]


# Claude Code's sandbox around every shell command of a job that may run one (any Bash rule): writes only in the vault minus
# its protected folders, no read of the secret folders, network only to the declared hosts. A job that runs no command gets none. Absolute paths are written `//abs` (Claude Code's absolute form;
# a plain `//` is the same folder for the operating system anyway).
SANDBOX_DENY_READ = ['~/.ssh', '~/.aws', '~/.gnupg', '~/.kube', '~/.docker', '~/.claude']
SANDBOX_DENY_WRITE = list(PROTECTED_DIRS) + list(PROTECTED_FILES_CASED)  # the guard's list: one source for both


def sandbox_settings(vault, network, writable, weaker):
    fs = {'denyRead': list(SANDBOX_DENY_READ), 'denyWrite': ['/' + os.path.join(vault, p) for p in SANDBOX_DENY_WRITE]}
    if writable:
        fs['allowWrite'] = sorted(set(writable))
    box = {'enabled': True, 'failIfUnavailable': True, 'allowUnsandboxedCommands': False, 'filesystem': fs,
           'network': {'allowedDomains': sorted(set(network))}}
    if weaker:  # from adapters/commands.json: gh (Go) checks TLS certificates through a macOS service the sandbox blocks
        box['enableWeakerNetworkIsolation'] = True
    return box


def job_settings(repo, answers, job):
    vault = expand(answers['vault_path'])
    extra_allow, extra_deny, network = job_rules(repo, answers, job)  # rendered and checked in Ctx.plan_jobs
    allow = list(BASE_ALLOW) + [abs_rule('Edit', f'{vault}/**')] + [str(r).strip() for r in extra_allow]  # every job writes its report in the vault
    deny = list(BASE_DENY) + [str(r).strip() for r in extra_deny]
    deny += ['Read(**/.mcp.json)', 'Read(**/.env*)', 'Read(**/.ssh/**)', 'Read(**/.aws/**)', 'Read(**/.gnupg/**)', 'Read(**/*credentials*)', 'Read(**/id_rsa*)', 'Read(**/id_ed25519*)']
    # defence in depth (the guard hook enforces the same): jobs never edit their own settings, the vault rules, git internals or the installer state
    deny += [abs_rule('Edit', f'{vault}/{p}/**') for p in PROTECTED_DIRS] + [abs_rule('Edit', f'{vault}/{f}') for f in PROTECTED_FILES_CASED]
    hook = [python_bin(answers), os.path.join(expand(answers['ct_home']), 'bin', 'guard.py'), '--vault', vault]
    guard = ' '.join(shlex.quote(x) for x in hook)
    settings = {'permissions': {'allow': sorted(set(allow)), 'deny': sorted(set(deny))},
                'hooks': {'PreToolUse': [{'matcher': GUARD_MATCHER, 'hooks': [{'type': 'command', 'command': guard, 'timeout': 10}]}]}}
    if any(r.startswith('Bash(') for r in allow):
        _, writable, weaker = command_needs(repo, answers, allow)
        settings['sandbox'] = sandbox_settings(vault, network, list(job['meta'].get('sandbox_allow_write', [])) + writable, weaker)
        table = known_commands(repo)
        env = {k: v for r in allow for p in [bash_parts(r)] if p for k, v in table.get(p[1], {}).get('env', {}).items()}
        settings.update({'env': env} if env else {})  # switches from the kit's command table only, never from answers
    return settings


def python_bin(answers):
    """Absolute interpreter for hooks and schedules: launchd and cron have a minimal PATH."""
    return answers.get('python_bin') or sys.executable or 'python3'


# ----------------------------------------------------------------------------- install
class Ctx:
    """One install run. __init__ is the whole PLAN phase: it resolves and checks everything, and writes nothing. Steps only
    write; they add to `report` and `files` (the two accumulators) and return what the next step needs."""

    def __init__(self, answers, repo, dry_run, update):
        a = merged_answers(answers)
        self.packs = validate(a, repo)
        a['tools'] = {c: (a.get('tools') or {}).get(c, 'none') for c in CAPABILITIES}
        self.vault, self.ct_home = expand(a['vault_path']), expand(a['ct_home'])
        a['vault_path'], a['ct_home'] = self.vault, self.ct_home
        self.manifest_path = os.path.join(self.vault, '.control-tower', 'manifest.json')
        self.previous = jload(self.manifest_path) if os.path.isfile(self.manifest_path) else {}
        if 'vault_mode' not in answers and self.previous.get('vault_mode') == 'runtime':
            a['vault_mode'] = 'runtime'  # a runtime-only vault stays runtime-only unless the answers explicitly say "full"
        self.a, self.repo, self.dry_run, self.update = a, repo, dry_run, update
        self.runtime_only = a.get('vault_mode', 'full') == 'runtime'
        self.policy = CorePolicy.from_packs([self.packs[p] for p in a['packs']])
        clash = static_collisions(repo, a['packs'], self.packs, self.policy)
        if clash:
            raise InstallError('these files would be written by two packs or by a pack and the core: ' + '; '.join(clash))
        self.table = render.build_table(vocab_files(repo, a['packs'], self.packs), a)
        self.translation = translate.load(self.vault, a['language'], a.get('translation_file'))
        self.named = translate.named_headings(render.render_text(text, self.table, 'kit', []) for text in kit_texts(repo, a['packs'], self.packs))
        self.collect = []  # the vault's texts, gathered while rendering: only their translation is kept
        for p in a['packs']:  # skills and notes as they will be written (a vocabulary word could otherwise build a forbidden key)
            check_rendered(self.packs[p], lambda text, rel: render.render_text(text, self.table, rel, []))
        self.installed, self.stash_dir = None, None
        if update:
            if not self.previous:
                raise InstallError(f'--update needs a vault installed by this kit: {self.manifest_path} not found')
            self.installed = self.previous.get('files', {})
            self.stash_dir = os.path.join(self.vault, '.control-tower', 'updates', datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
        self.report = {'vault': self.vault, 'ct_home': self.ct_home, 'created': 0, 'kept': 0, 'jobs': [], 'jobs_skipped': [],
                       'warnings': [], 'schedule': None, 'updated': [], 'stashed': [], 'skipped': [], 'stash_dir': self.stash_dir,
                       'routines': [], 'routines_skipped': [], 'vault_mode': 'runtime' if self.runtime_only else 'full',
                       'permissions_summary': [], 'everywhere': None, 'owner': {'name': a['owner_name'], 'handle': a['owner_handle'], 'timezone': a['timezone']}}
        self.files = {}  # vault paths written by this run: checksummed into the manifest
        self.seen = set()  # every kit file of the vault this run produces, written or not
        self.approved = approved_servers(self.vault, a, recorded_servers(a))  # the servers jobs may start, as approved
        self.mcp_blocked = set()  # (capability, tool) of an MCP server no job may call yet: not connected, or no read tool allowed
        self.jobs_on, self.jobs_off = self.plan_jobs()

    def plan_jobs(self):
        """Which jobs run, their final (rendered) definition, and every check on them: nothing is written if one fails."""
        a, on, off = self.a, [], []
        for cap, rules in (a.get('permissions') or {}).items():
            check_permissions(f'answers permissions "{cap}"', rules)
        pack_jobs, mine = eligible_jobs(a['packs'], self.packs, a['tools']), my_jobs(a)
        clash = sorted({j['id'] for j in mine} & {j['id'] for j in pack_jobs})
        if clash:
            raise InstallError(f'your report {", ".join(clash)} has the id of a pack job: choose another id')
        taken = sorted(j['id'] for j in pack_jobs if any(MY_REPORTS.match(posixpath.normpath(str(o))) for o in j['meta'].get('outputs', [])))
        if taken:  # a report named ...-my-<id> is the user's own
            raise InstallError(f'pack job {", ".join(taken)} declares a report named like your own (journal/reports/<date>-my-...)')
        known = set((a.get('servers') or {}).values())
        for j in pack_jobs + mine:
            cfg = (a.get('jobs') or {}).get(j['id'], {})
            if j['missing'] or cfg.get('enabled') is False:
                off.append(j)
                self.report['jobs_skipped'].append({'id': j['id'], 'missing': j['missing']})
                continue
            meta = dict(j['meta'])
            meta['schedule'] = job_schedule(meta['schedule'], cfg)
            j['rendered'] = json.loads(render.render_text(json.dumps(meta), self.table, j['id'], []))
            # checked on the FINAL strings: a pack's vocabulary could otherwise inject text into a rule after the check
            check_permissions(f'job "{j["id"]}"', j['rendered']['permissions'].get('allow', []))
            allow, _, network = job_rules(self.repo, a, {'id': j['id'], 'meta': j['rendered']})
            check_permissions(f'job "{j["id"]}"', allow)  # adapters and the user's grants: the same limits
            # its servers: the known tools', and the connections it uses (a connection's server goes only to its reports)
            adapters = job_adapters(self.repo, a, j['rendered'])
            j['servers'] |= {man['server'] for _, man in adapters.values() if man.get('server')}
            j['approved'] = {s: e for s, e in self.approved.items() if s in known | j['servers']}
            self.mcp_blocked |= unreachable_servers(adapters, a, allow, j['approved'])
            uses = describe_rules(allow, network)
            if any(uses.values()):  # what the user consents to, in plain words (the guided installer asks about it)
                self.report['permissions_summary'].append({'job': j['id'], 'name': j['rendered'].get('name', j['id']), **uses})
            sched = j['rendered']['schedule']
            self.report['jobs'].append({'id': j['id'], 'pack': j['pack'], 'days': sched['days'], 'time': sched['time']})
            on.append(j)
        if self.runtime_only and any(j['pack'] and not self.packs[j['pack']].private for j in on):
            self.report['warnings'].append('runtime-only mode with public-pack jobs: their prompts expect the kit vault layout; '
                                           'check they fit your vault, or use jobs from your own private pack')
        self.report['warnings'] += [f'{cap}/{tool}: jobs cannot call this MCP server until it is connected with read tools allowed: {allow_hint(a)}'
                                    for cap, tool in sorted(self.mcp_blocked)]
        if 'strict' in a:
            self.report['warnings'].append('"strict" in the answers is ignored: every job that may run a command now runs in the sandbox')
        if self.runtime_only:
            self.report['warnings'] += vault_settings_warnings(self.vault, a)
        return on, off

    def record(self, res):
        self.report['created'] += len(res.get('created', [])) + len(res.get('replaced', []))
        self.report['kept'] += len(res.get('kept', []))
        for key in ('updated', 'stashed', 'skipped'):
            self.report[key] += res.get(key, [])
        for rel in res.get('created', []) + res.get('replaced', []) + res.get('updated', []):
            self.files[rel] = None  # stashed files keep their install-time checksum
        self.seen.update(rel for key in ('created', 'replaced', 'kept', 'updated', 'stashed', 'skipped') for rel in res.get(key, []))

    def render(self, src, **kw):
        self.record(render.render_tree(src, self.vault, self.table, dry_run=self.dry_run, installed=self.installed,
                                       stash_dir=self.stash_dir, transform=self.translated, **kw))

    def translated(self, rel, content):
        """A vault file in the vault's language; its texts are gathered first."""
        self.collect.extend(translate.segments(rel, content, self.named))
        return translate.apply(rel, content, self.translation, self.named)


def vault_settings_warnings(vault, answers):
    """What in the vault's settings, .mcp.json or skills could widen jobs."""
    out = [f'{os.path.join(vault, rel)} {text}' for rel, _, text in vault_settings_findings(vault)]
    out += [f'{os.path.join(vault, ".mcp.json")}: {text}' for _, text in mcp_file_findings(vault, answers)]
    skills = os.path.join(vault, '.claude', 'skills')
    for name in sorted(os.listdir(skills)) if os.path.isdir(skills) else []:
        p = os.path.join(skills, name, 'SKILL.md')
        if os.path.isfile(p) and TOOLS_KEY_ANYWHERE.search(open(p, encoding='utf-8', errors='replace').read()):
            out.append(f'{p} declares allowed-tools: a job that loads this skill gets those tools too')
    return out


# ----------------------------------------------------------------------------- write steps
def step_fresh(ctx, fresh):
    """Kit files to write again (update mode): the user's version is moved to _system/archive/<time>/, then the vault step
    writes the kit's version as for a new file."""
    unknown = [rel for rel in fresh if rel not in (ctx.installed or {})]
    if unknown:
        raise InstallError(f'not a file installed by the kit: {", ".join(unknown)}')
    if any(rel.startswith('.obsidian/') for rel in fresh):  # seeded once, when the vault has no .obsidian folder yet
        raise InstallError("Obsidian's settings are Obsidian's after the first install: change them in Obsidian")
    archive, moved = os.path.join(ctx.vault, '_system', 'archive', datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')), []
    for rel in fresh:
        if not ctx.dry_run and os.path.isfile(os.path.join(ctx.vault, rel)):
            os.makedirs(os.path.dirname(os.path.join(archive, rel)), exist_ok=True)
            os.replace(os.path.join(ctx.vault, rel), os.path.join(archive, rel))
            moved.append((os.path.join(ctx.vault, rel), os.path.join(archive, rel)))
        ctx.installed = {k: v for k, v in ctx.installed.items() if k != rel}
    return moved


def step_vault(ctx):
    """Core vault (minus what private packs replace or exclude), then each pack's vault files."""
    ctx.render(os.path.join(ctx.repo, 'core', 'vault'), skip=ctx.policy.skips if ctx.policy else None)
    for p in ctx.a['packs']:
        pv = os.path.join(ctx.packs[p].dir, 'vault')
        if os.path.isdir(pv):
            ctx.render(pv)


def step_adapters(ctx):
    """One note per chosen tool in .claude/adapters/, under the same update rules as every kit file."""
    for cap, tool in ctx.a['tools'].items():
        if tool == 'none':
            continue
        rel = f'.claude/adapters/{cap}.md'
        target = os.path.join(ctx.vault, rel)
        errs = []
        content = render.render_text(adapter_doc(ctx.repo, cap, tool, ctx.a), ctx.table, rel, errs)
        if errs:
            raise InstallError('; '.join(errs))
        if ctx.update:
            action = render.update_action(target, rel, content, None, ctx.installed)
        else:
            action = 'kept' if os.path.exists(target) else 'create'
        ctx.record({'create': {'created': [rel]}, 'kept': {'kept': [rel]}}.get(action, {action: [rel]}))
        if not ctx.dry_run and action in ('create', 'updated', 'stashed'):
            dest = os.path.join(ctx.stash_dir, rel) if action == 'stashed' else target
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'w', encoding='utf-8') as fh:
                fh.write(content)


def step_runtime(ctx):
    """Runner and guard, then one folder per job (prompt, job.json, settings.json). Folders of jobs no longer on are removed."""
    if ctx.dry_run:
        return
    os.makedirs(os.path.join(ctx.ct_home, 'bin'), exist_ok=True)
    for name in ('run_job.py', 'guard.py'):
        shutil.copy2(os.path.join(ctx.repo, 'scheduler', name), os.path.join(ctx.ct_home, 'bin', name))
    runtime = os.path.join(ctx.ct_home, 'install.json')
    prev = jload(runtime, {})  # kit_commit: step_manifest records the new one last; everywhere: the shortcut it wrote
    jdump(runtime, {'vault': ctx.vault, 'claude_bin': ctx.a.get('claude_bin', 'claude'), 'timezone': ctx.a['timezone'], 'version': VERSION,
                    'kit_commit': prev.get('kit_commit'), **({'everywhere': prev['everywhere']} if 'everywhere' in prev else {})})
    jobs_root = os.path.join(ctx.ct_home, 'jobs')
    keep = {j['id'] for j in ctx.jobs_on}
    for old in (os.listdir(jobs_root) if os.path.isdir(jobs_root) else []):
        if old not in keep:
            shutil.rmtree(os.path.join(jobs_root, old), ignore_errors=True)
    for j in ctx.jobs_on:
        jdir = os.path.join(jobs_root, j['id'])
        os.makedirs(jdir, exist_ok=True)
        with open(os.path.join(j['dir'], 'prompt.md.tmpl'), encoding='utf-8') as fh:
            errs = []
            prompt = render.render_text(fh.read(), {**ctx.table, **j['tokens']}, j['id'], errs)
        if errs:
            raise InstallError('; '.join(errs))
        with open(os.path.join(jdir, 'prompt.md'), 'w', encoding='utf-8') as fh:  # only the prompt: nothing else from the pack
            fh.write(prompt)
        jdump(os.path.join(jdir, 'job.json'), j['rendered'])
        settings = job_settings(ctx.repo, ctx.a, {'id': j['id'], 'meta': j['rendered']})
        jdump(os.path.join(jdir, 'settings.json'), settings)
        calls = {mcp_server(r) for r in settings['permissions']['allow']}  # the runner passes only this file (--strict-mcp-config)
        jdump(os.path.join(jdir, 'mcp.json'), {'mcpServers': {s: e for s, e in j['approved'].items() if s in calls}})


def step_schedule(ctx):
    """launchd plists or a crontab block mirroring the jobs that are on. Sets report['schedule'], returns the plist paths."""
    a, ct_home = ctx.a, ctx.ct_home
    sched_dir = os.path.join(ct_home, 'schedule')
    kind = pick_scheduler(a.get('scheduler', 'auto'))
    if not ctx.dry_run:
        shutil.rmtree(sched_dir, ignore_errors=True)
    plist_paths, cron_lines = [], []
    runs = [(j['id'], [os.path.join(ct_home, 'bin', 'run_job.py'), '--job', j['id'], '--ct-home', ct_home], j['rendered']['schedule'])
            for j in ctx.jobs_on]
    if runs and unsafe_in_text(ctx.repo):
        ctx.report['warnings'].append("the kit's folder name cannot go into the schedule: no weekly look for a new version")
    elif runs:  # with the reports, a weekly look for a new version of the kit (an id no job can have)
        runs.append(('kit.update', [os.path.join(ctx.repo, 'installer', 'configure.py'), 'update', '--vault', ctx.vault, '--notify'],
                     {'days': 'mon', 'time': '09:00'}))
    for rid, args, sched in runs:
        args = [python_bin(a)] + args
        lt, shift, warn = local_time(sched['time'], a['timezone'])
        days = shift_days(parse_days(sched['days']), shift)
        if warn:
            ctx.report['warnings'].append(f"{rid}: {warn}")
        if kind == 'launchd':
            label = f"com.control-tower.{rid}"
            path = os.path.join(sched_dir, 'launchd', label + '.plist')
            plist_paths.append((label, path))
            if not ctx.dry_run:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as fh:
                    fh.write(launchd_plist(label, args, days, lt, os.path.join(ct_home, 'logs', rid + '.launchd.log')))
        elif kind == 'cron':
            cron_lines.append(f'# {rid}\n' + cron_line(args, days, lt))
    if kind == 'cron' and cron_lines and not ctx.dry_run:  # no job: no file, and applying removes this install's block
        os.makedirs(sched_dir, exist_ok=True)
        with open(os.path.join(sched_dir, 'crontab.txt'), 'w', encoding='utf-8') as fh:
            fh.write(cron_header(sched_dir) + '\n'.join(cron_lines) + '\n' + CRON_END + '\n')
    ctx.report['schedule'] = {'kind': kind, 'applied': False, 'dir': sched_dir}
    return plist_paths


def step_routines(ctx):
    """Cloud routines: rendered prompts and an index the guided installer reads to create them on request. Returns the list."""
    a, report = ctx.a, ctx.report
    index, seen_ids = [], {}
    for r in eligible_routines(a['packs'], ctx.packs, a['tools']) + my_routines(a):
        if r['id'] in seen_ids and not r['missing'] and r['pack'] != MY_PACK:
            report['routines_skipped'].append({'id': f"{r['pack']}--{r['id']}", 'missing': [], 'duplicate_of': seen_ids[r['id']]})
            continue
        if r['missing']:
            report['routines_skipped'].append({'id': f"{r['pack']}--{r['id']}", 'missing': r['missing']})
            continue
        key = f"{r['pack']}--{r['id']}"
        seen_ids[r['id']] = key
        meta = r['meta']
        errs = []
        prompt = render.render_text(r['prompt'], {**ctx.table, **r['tokens']}, key, errs)
        if errs:
            raise InstallError('; '.join(errs))
        entry = {'key': key, 'pack': r['pack'], 'id': r['id'], 'name': meta['name'],
                 'days': meta['days'], 'time': meta['time'], 'timezone': a['timezone'], 'cron': routine_cron(meta['days'], meta['time']),
                 'connectors_required': {**{c: a['tools'][c] for c in meta.get('connectors_required', [])}, **r['connectors']},
                 'connectors_optional': {c: a['tools'][c] for c in meta.get('connectors_optional', []) if a['tools'].get(c, 'none') != 'none'},
                 'vault': meta.get('vault', 'write'), 'after': meta.get('after', ''),
                 'prompt_file': os.path.join(ctx.ct_home, 'routines', key + '.prompt.md')}
        index.append(entry)
        report['routines'].append({'key': key, 'name': entry['name'], 'days': entry['days'], 'time': entry['time']})
        if not ctx.dry_run:
            os.makedirs(os.path.join(ctx.ct_home, 'routines'), exist_ok=True)
            with open(entry['prompt_file'], 'w', encoding='utf-8') as fh:
                fh.write(prompt)
    if not ctx.dry_run:  # the index and prompts follow the answers: a report removed or moved off claude.ai leaves nothing behind
        rdir, keys = os.path.join(ctx.ct_home, 'routines'), {e['key'] + '.prompt.md' for e in index}
        os.makedirs(rdir, exist_ok=True)
        for f in os.listdir(rdir):
            if f.endswith('.prompt.md') and f not in keys:
                os.remove(os.path.join(rdir, f))
        jdump(os.path.join(rdir, 'routines.json'), index)
    return report['routines']


def step_next_steps(ctx, routines):
    """What the user must do next. Full install: a note in the vault, written once. Runtime-only: next to the runtime,
    rewritten every run (it is the installer's file, never the user's)."""
    text = next_steps(ctx.repo, ctx.a, ctx.jobs_on, ctx.jobs_off, routines, ctx.mcp_blocked)
    if ctx.runtime_only:
        path = os.path.join(ctx.ct_home, 'setup-next-steps.md')
        if not ctx.dry_run:
            os.makedirs(ctx.ct_home, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(text)
    else:
        rel = 'library/setup-next-steps.md'
        path = os.path.join(ctx.vault, rel)
        ctx.seen.add(rel)
        if not os.path.exists(path):
            ctx.record({'created': [rel]})
            if not ctx.dry_run:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as fh:
                    fh.write(text)
    ctx.report['next_steps'] = path


def step_obsidian(ctx):
    if not ctx.dry_run:
        for rel in obsidian_seed(ctx.vault):
            ctx.files[rel] = None


def everywhere_text(ctx):
    """The personal /control-tower skill: the kit's own hub, as is (never the vault's copy, a pack's, or an answer's text: what
    every session follows comes from the kit only), with this vault named and a way out for another vault's session."""
    hub = hub_text(ctx).split('\n---\n', 1)[-1]  # its frontmatter is replaced
    kit_job_permissions = os.path.join(ctx.repo, 'core', 'vault', '.claude', 'skills', 'job-permissions', 'SKILL.md')
    return ('---\nname: control-tower\ndescription: Your control tower from any folder. Use when the user says /control-tower or "hello control '
            'tower".\n---\n'
            f'<!-- {EVERYWHERE_MARK}{ctx.ct_home} -->\n\n# Control tower, from any folder\n\n'
            f'Written by the control tower installer from its kit. Below, "this vault" is `{ctx.vault}`, whatever folder this session is on; '
            f'the kit (`repo`) is `{ctx.repo}` and the runtime folder (`ct_home`) is `{ctx.ct_home}`: use these, never the ones in the '
            "vault's manifest, which is read only to check that the vault was installed by the kit.\n\n"
            f'- If this session\'s folder is another control tower vault (it holds `.control-tower/manifest.json`) and is not `{ctx.vault}`, '
            'this text is not for it: say so, and follow that folder\'s own `.claude/skills/control-tower/SKILL.md` with that folder as the vault.\n'
            f'- Where this text hands over to `/job-permissions` and this session is not on `{ctx.vault}`, follow `{kit_job_permissions}` instead.\n'
            f'- Signing in to a tool (`/mcp`) works only in a session opened on `{ctx.vault}`: from another folder, say so and offer to open a '
            'session there (with a tool that starts a session in a folder, if you have one), or tell the user to start a new Code session on it.\n\n'
            + hub)


HUB = os.path.join('.claude', 'skills', 'control-tower', 'SKILL.md')


def hub_text(ctx):
    with open(os.path.join(ctx.repo, 'core', 'vault', HUB), encoding='utf-8') as fh:
        return fh.read()


def hub_not_the_kit_s(ctx):
    """Why the vault's /control-tower is not the kit's own hub (a pack replaces or drops it), or why the kit's cannot be
    written as is (a token in it), or None."""
    packs = [p for p in ctx.a['packs'] if any(os.path.isfile(os.path.join(ctx.packs[p].dir, 'vault', HUB + ext)) for ext in ('', '.tmpl'))]
    if packs or (ctx.policy and ctx.policy.excluded(HUB.replace(os.sep, '/'))):
        return f'the pack {", ".join(packs) or "chosen"} changes /control-tower'
    return 'the kit\'s /control-tower holds an answer token' if '{{ct.' in hub_text(ctx) else None


def step_everywhere(ctx):
    """The personal /control-tower shortcut: written after the user's yes ("everywhere"), refreshed with the kit, removed when
    turned off. Its path and checksum go to install.json: a shortcut the user edited, another install's, or a skill of the
    user's is never replaced or removed. A runtime-only install has no hub."""
    runtime = os.path.join(ctx.ct_home, 'install.json')
    path, unedited = our_shortcut(ctx.ct_home)
    if ctx.a.get('everywhere') and not ctx.runtime_only:
        why = ('the kit\'s folder name holds a backtick, a control character or "-->"' if unsafe_in_text(ctx.repo)
               else hub_not_the_kit_s(ctx))
        if why:
            ctx.report['warnings'].append(f'/control-tower everywhere: {why}: not written; /control-tower works in the vault session')
            return
        target = user_skill_path()
        if os.path.exists(target) and not (target == path and unedited):
            with open(target, encoding='utf-8', errors='replace') as fh:
                text = fh.read()
            whose = ('your edited copy of the shortcut' if f'<!-- {EVERYWHERE_MARK}{ctx.ct_home} -->' in text else
                     'the shortcut of another control tower install' if EVERYWHERE_MARK in text else 'a personal skill of yours')
            ctx.report['warnings'].append(f'{target} is {whose}: it was kept, so /control-tower runs it outside the vault; this control '
                                          'tower\'s /control-tower works in its vault session')
            return
        ctx.report['everywhere'] = target
        if not ctx.dry_run:
            if path and path != target and unedited:  # Claude's folder moved: the copy at the old place goes
                remove_shortcut(path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'w', encoding='utf-8') as fh:
                fh.write(everywhere_text(ctx))
            jdump(runtime, dict(jload(runtime), everywhere={'path': target, 'sha256': file_sha256(target)}))
    elif path and not ctx.dry_run:
        if unedited:
            remove_shortcut(path)
        elif os.path.isfile(path):
            ctx.report['warnings'].append(f'{path}: your edited copy of the /control-tower shortcut was kept')
        jdump(runtime, {k: v for k, v in jload(runtime).items() if k != 'everywhere'})


def step_manifest(ctx):
    """Checksums of every kit file in the vault (doctor, --update, uninstall), the mode, the core policy, and the answers;
    then the kit commit the runtime now follows, once everything else is written."""
    if ctx.dry_run:
        return
    sums = {rel: render.sha256(os.path.join(ctx.vault, rel)) for rel in ctx.files if os.path.isfile(os.path.join(ctx.vault, rel))}
    files = {**ctx.previous.get('files', {}), **sums}
    jdump(ctx.manifest_path, {'version': VERSION, 'installed_at': datetime.datetime.now().isoformat(timespec='seconds'),
                              'packs': ctx.a['packs'], 'tools': ctx.a['tools'], 'ct_home': ctx.ct_home, 'files': files,
                              'vault_mode': ctx.report['vault_mode'], 'repo': ctx.repo, **ctx.policy.to_json()})
    jdump(os.path.join(ctx.vault, '.control-tower', 'answers.json'), {k: v for k, v in ctx.a.items() if k not in ('claude_bin', 'strict', 'translation_file')})
    seen = set(ctx.collect)
    texts = {k: v for k, v in ctx.translation.items() if k in seen}  # the vault's own texts, nothing else
    if texts:  # kept in the vault: every later write puts it back
        jdump(os.path.join(ctx.vault, '.control-tower', 'translation.json'), {'language': ctx.a['language'], 'texts': texts})
    runtime = os.path.join(ctx.ct_home, 'install.json')
    jdump(runtime, dict(jload(runtime), kit_commit=kit_commit(ctx.repo)))


def install(answers, repo=REPO, dry_run=False, schedule=None, launch_agents_dir=None, no_launchctl=False, log=print, update=False,
            fresh=(), strings=False):
    ctx = Ctx(answers, repo, dry_run, update)  # plan: everything is checked here, before the first write
    moved = step_fresh(ctx, fresh)
    try:
        if not ctx.runtime_only:               # runtime-only: the vault is the user's own, nothing of the kit goes in it
            step_vault(ctx)
            step_adapters(ctx)
        step_runtime(ctx)
        step_everywhere(ctx)
        plist_paths = step_schedule(ctx)
        routines = step_routines(ctx)
        step_next_steps(ctx, routines)
        if not ctx.runtime_only:
            step_obsidian(ctx)
        lost = [rel for rel in fresh if rel not in ctx.seen]
        if lost:  # a dropped tool or pack: the kit no longer writes it
            raise InstallError(f'the kit no longer writes: {", ".join(lost)}')
        step_manifest(ctx)                     # last: checksums every file the steps above wrote
    except Exception:
        for src, dest in moved:  # a refused run leaves the user's version of a fresh-copied file in place
            os.replace(dest, src)
        raise
    if strings:  # the vault's texts, once each, in the order the installer met them
        ctx.report['strings'] = list(dict.fromkeys(ctx.collect))
    sched = ctx.report['schedule']
    if schedule and not dry_run:  # 'load' this install's jobs in the scheduler, or 'unload' them all
        if sched['kind'] == 'none':
            ctx.report['warnings'].append(f'schedule not {schedule}ed: scheduler is "none" in the answers')
        else:
            problems = {'warnings': []}  # why the scheduler refused, apart from the installer's other warnings
            done = apply(sched['kind'], plist_paths, sched['dir'], launch_agents_dir, no_launchctl, problems, unload=schedule == 'unload')
            sched['problems'] = problems['warnings']
            sched['applied'] = done and not sched['problems'] and schedule == 'load'
            ctx.report['warnings'] += sched['problems']
    return ctx.report


def print_report(report, dry_run):
    mode = 'DRY RUN: nothing was written.\n' if dry_run else ''
    print(f"\n{mode}Vault: {report['vault']}\nRuntime: {report['ct_home']}")
    print(f"Files: {report['created']} {'would be created' if dry_run else 'created'}, {report['kept']} kept (already existed)")
    print('Jobs: ' + (', '.join(f"{j['id']} ({j['days']} {j['time']})" for j in report['jobs']) or 'none'))
    for j in report['jobs_skipped']:
        print(f"  skipped {j['id']}: " + (f"needs a tool for {', '.join(j['missing'])}" if j['missing'] else 'disabled'))
    if report.get('permissions_summary'):
        print('Access the jobs will have (besides reading your vault and writing their reports in it):')
        for p in report['permissions_summary']:
            uses = [f"{label}: {', '.join(p[key])}" for key, label in (('commands', 'commands'), ('mcp_tools', 'tools'), ('web', 'web sites'))
                    if p[key]]
            print(f"  {p['job']}: " + '; '.join(uses))
    s = report['schedule']
    if s:
        if s['kind'] == 'none':
            print('Schedule: none (jobs run only when you start them)')
        else:
            print(f"Schedule: {s['kind']} ({'applied' if s['applied'] else 'generated, not applied: re-run with --apply-schedule'})")
    if report.get('routines'):
        print('Cloud routines available (not created): ' + ', '.join(r['key'] for r in report['routines'])
              + '. Run /install-control-tower routines to create them on claude.ai.')
    for r in report.get('routines_skipped', []):
        why = f"same routine as {r['duplicate_of']}" if r.get('duplicate_of') else f"needs a tool for {', '.join(r['missing'])}"
        print(f"  routine {r['id']} not offered: {why}")
    for w in report['warnings']:
        print('warning: ' + w)
    if report.get('stash_dir') is not None:
        print(f"Update: {len(report['updated'])} file(s) updated (you had not edited them), "
              f"{len(report['stashed'])} kept because you edited them, {len(report['skipped'])} you deleted left deleted")
        for rel in report['stashed']:
            print(f"  edited by you, new version {'would be ' if dry_run else ''}saved for merging: {rel}")
        if report['stashed'] and not dry_run:
            print(f"  new versions are in {report['stash_dir']}: compare and merge what you want (or ask Claude: "
                  '"merge the kit updates from .control-tower/updates"), then delete that folder')
    if not dry_run:
        print(f"\nNext: open {report.get('next_steps') or 'library/setup-next-steps.md in your vault'}.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--answers')
    ap.add_argument('--interactive', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--match-tools', metavar='TEXT', help='the tools named in TEXT, for the capabilities of --packs (JSON)')
    ap.add_argument('--match-tools-file', metavar='FILE', help='the same with the text in FILE: what a user typed never goes on a command line')
    ap.add_argument('--known-tools', action='store_true', help='the tools the capabilities of --packs can use (JSON)')
    ap.add_argument('--packs', nargs='+', default=[], help='with --match-tools or --known-tools')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--apply-schedule', action='store_true')
    ap.add_argument('--runtime-only', action='store_true', help='install only the runtime (job runner, guard, jobs, schedule) on an '
                    'existing vault: nothing is written in it except .control-tower/ (same as "vault_mode": "runtime")')
    ap.add_argument('--update', action='store_true', help='after pulling a new version of the kit: refresh the files you never edited, '
                    'keep the ones you edited and save their new version under <vault>/.control-tower/updates/')
    ap.add_argument('--launch-agents-dir', help='where to link launchd plists (default ~/Library/LaunchAgents)')
    ap.add_argument('--no-launchctl', action='store_true', help='link plists but do not load them (tests)')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--strings', action='store_true', help='with --answers: the vault\'s texts to translate, as JSON (nothing is written)')
    args = ap.parse_args()
    if args.interactive:
        print('error: the terminal wizard is gone. Open Claude Code in the kit folder and type /install-control-tower: it asks four '
              'questions. Or give --answers FILE (see examples/answers).', file=sys.stderr)
        sys.exit(2)
    try:
        if args.match_tools_file:
            with open(args.match_tools_file, encoding='utf-8') as fh:
                args.match_tools = fh.read()
        if args.packs and args.match_tools is None and not args.known_tools:
            ap.error('--packs goes with --match-tools, --match-tools-file or --known-tools')
        if args.match_tools is not None or args.known_tools:
            found = known_tools(args.packs) if args.known_tools else match_tools(args.match_tools, args.packs)
            print(json.dumps(found, indent=2))
            return
        if not args.answers:
            ap.error('give --answers FILE')
        answers = jload(args.answers)
        if args.runtime_only:
            answers['vault_mode'] = 'runtime'
        if args.strings:
            print(json.dumps(install(answers, dry_run=True, strings=True, log=lambda *x: None)['strings'], indent=1, ensure_ascii=False))
            return
        report = install(answers, dry_run=args.dry_run, schedule='load' if args.apply_schedule else None,
                         launch_agents_dir=args.launch_agents_dir, no_launchctl=args.no_launchctl, update=args.update)
    except (InstallError, render.RenderError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as exc:
        print(f'error: {args.answers} is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})', file=sys.stderr)
        sys.exit(2)
    except OSError as exc:
        print(f'error: {exc.strerror or exc}: {exc.filename or ""}', file=sys.stderr)
        sys.exit(2)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report, args.dry_run)


if __name__ == '__main__':
    main()
