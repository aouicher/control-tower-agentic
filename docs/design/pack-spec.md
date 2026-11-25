# Pack and adapter specification

Read `core-spec.md` first. A **pack** adapts the neutral core to a profession. An **adapter** connects a capability (tracker, errors, analytics...) to a real tool. Everything is English, company-neutral and read-only on external systems.

## 1. Pack layout

```
packs/<id>/
  pack.json                 manifest (schema below)
  vocabulary.json           overrides of core/vocabulary.json (same shape)
  README.md                 what the pack gives, who it is for, first week with it
  vault/                    overlay copied on top of core/vault (never overwrites a core file)
    .claude/rules/<id>.md.tmpl          pack rules, loaded automatically by Claude Code
    .claude/skills/<skill>/SKILL.md.tmpl
    _system/templates/<template>.md
    _system/dashboards/<dashboard>.base
    cockpit/<page>.md
    library/<page>.md
  jobs/<job-id>/
    job.json                schedule, capabilities, permissions (schema below)
    prompt.md.tmpl          the prompt of the unattended job
  routines/<id>.md          prompts to paste into claude.ai cloud routines (optional)
```

`{{ct.*}}` tokens are rendered by `installer/render.py` using `core/vocabulary.json` then `packs/<id>/vocabulary.json`. Never hardcode a vocabulary word that has a token. Obsidian's `{{title}}` and `{{date:...}}` stay untouched.

## 2. `pack.json`

```json
{
  "id": "engineering",
  "name": "Engineering leader",
  "audience": "Heads of engineering, CTOs, engineering managers",
  "summary": "one sentence",
  "vocabulary": "vocabulary.json",
  "skills": ["weekly-digest", "postmortem"],
  "templates": ["postmortem"],
  "dashboards": ["delivery"],
  "cockpit_pages": ["pulse"],
  "jobs": ["morning-triage", "weekly-digest"],
  "routines": ["morning-brief"],
  "capabilities": {
    "required": ["calendar"],
    "optional": ["tracker", "code", "errors", "quality", "logs"]
  },
  "questions": [
    {"id": "tracker_tool", "ask": "Which issue tracker do you use?", "capability": "tracker",
     "choices": ["jira", "linear", "github-issues", "none"]}
  ]
}
```

- Every name listed must exist as a file or folder in the pack (`skills/<name>`, `templates/<name>.md`, `dashboards/<name>.base`, `cockpit/<name>.md`, `jobs/<name>/`, `routines/<name>.md`).
- `capabilities.required|optional` use the capability ids of section 4. The installer asks `questions` and installs only the adapters and jobs the user can actually run.
- `questions[].choices` must be tool ids that exist under `adapters/<capability>/` (or `none`).

## 2b. What a pack may add

- New folders under `work/` or `library/` (for example `work/content/`), never a rename or removal of a core folder.
- New note types (for example `type: content`) with their properties, documented in the pack rules file `.claude/rules/<id>.md.tmpl`; the pack dashboards filter on them. A pack never changes the meaning of a core type or property.
- New templates, dashboards, cockpit pages and skills, with names that do not collide with the core ones (the installer refuses a collision).
- It never edits `CLAUDE.md`: pack rules live in `.claude/rules/<id>.md.tmpl`.

## 3. Jobs

`job.json`:

```json
{
  "id": "morning-triage",
  "name": "Morning triage",
  "description": "one sentence",
  "schedule": {"days": "mon-fri", "time": "08:00"},
  "model": "sonnet",
  "capabilities": ["errors", "quality"],
  "outputs": ["journal/reports/triage-YYYY-MM-DD.md"],
  "permissions": {"allow": [], "deny": []}
}
```

`prompt.md.tmpl` rules (unattended run, nobody answers):
- First lines: "Unattended scheduled job ... never ask, never wait. Read-only on every external system; write only inside the vault. Follow CLAUDE.md. Write in English."
- State the data window, the numbered steps, and the exact output files with their layout (use the page style of the core spec: `🕐 Generated on` line, `> [!summary] Summary`, tables, folded `> [!note]-` annexes).
- Reference capabilities by id, never by product: "use the tracker adapter configured in `.claude/adapters/tracker.md`". The installer writes the chosen adapter notes there.
- Counting rules: never report a count taken from a truncated page; paginate or say "at least N (truncated)".
- Tasks created by the job are tagged `#to-triage`; the job cannot check the vault for duplicates (shell search may be denied), so it proposes tasks only for new important findings.
- The job never writes `rag`, `owner`, `due`, `group` of existing notes.
- Frontmatter free text values are always in double quotes.

## 4. Capabilities and adapters

Capability ids: `calendar`, `tracker` (issues and sprints), `code` (pull requests and releases), `errors` (error tracking), `quality` (code quality gates), `logs` (log search and metrics), `analytics` (product or web analytics), `crm` (customers, campaigns, email).

```
adapters/<capability>/
  contract.md               what jobs and skills expect from ANY tool of this capability
  <tool>.md                 how to use <tool> for this capability
  <tool>.json               machine-readable manifest
```

`<tool>.json`:

```json
{
  "tool": "sentry",
  "capability": "errors",
  "access": "mcp",
  "setup_url": "https://...",
  "install": ["claude mcp add ..."],
  "env": ["SENTRY_AUTH_TOKEN"],
  "permissions_allow": ["mcp__sentry__*"],
  "verify": "one command or prompt the user runs to check the connection",
  "read_only": true,
  "permissions_deny": ["mcp__sentry__update_issue"],
  "status": "documented"
}
```

`permissions_allow` lists explicit tool names, never a wildcard. If the tool has no read-only mode, set `"read_only": false` and add `"read_only_mitigation"` (for example a view-only account, a read-only token or role). If the official documentation does not list the tool names, leave `permissions_allow` empty and tell the user to review the server's tool list and allow only read-only tools.

`status` is `documented` (written from the official documentation, not exercised by the tests) or `verified` (exercised against a real account). Never claim `verified` without a real test.

`contract.md` sections: Purpose · Inputs the job gives · Outputs it expects (fields) · Pagination and truncation rules · Read-only guarantees · Failure handling.
`<tool>.md` sections: Setup · Authentication and least-privilege scopes · Commands or tools to call · Field mapping to the contract · Pitfalls · Verification.

Facts must come from the tool's official documentation: cite the URL in `setup_url` and in the `.md`. If a detail cannot be verified, write "check the official documentation" rather than guessing a command.

## 5. Quality gates

A pack or adapter is acceptable when:
1. `tests/test_packs.py` passes: manifests are valid, every referenced file exists, the pack renders on top of the core without leftover tokens, skill names equal their folders.
2. `python3 tools/scan-leaks.py` reports nothing: no company, product, people or ticket names from any private setup, no non-English text.
3. Skills and prompts follow the core spec: one task lives once, `#to-triage` for automations, quoted free-text frontmatter, page style.
