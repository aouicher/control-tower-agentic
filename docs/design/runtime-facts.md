# Runtime facts

Claude Code behaviours the kit relies on, checked with the real CLI rather than read from its documentation. Re-run the checks after upgrading Claude Code and update this page:

```bash
CT_REAL_CLAUDE=1 python3 tests/e2e/smoke_real_claude.py --facts --save-init tests/e2e/fixtures/init_message.json
```

Each check runs in a temporary folder with Haiku, `claude -p --permission-mode dontAsk --setting-sources project`, the mode the job runner uses. It adds no server and changes no setting (Claude Code keeps its usual session transcripts). The last run made 16 calls for $0.07. `tests/e2e/facts_mcp_server.py` is a local test MCP server with one read tool and one action tool.

Last run: Claude Code 2.1.332, macOS, 2026-11-27.

| Fact | Result | What was observed |
|---|---|---|
| F1. A server added with `claude mcp add --scope user` is visible to a job. | **Fail** | The account's user-scope server appears with `--setting-sources user,project` and not with `--setting-sources project`. Jobs do not see user-scope servers. |
| F1b. A server declared in the vault's `.mcp.json` and enabled in the job's settings (`enabledMcpjsonServers`) is visible to a job. | Pass | With an allow rule for `mcp__facts__get_fact`, the call runs and returns the server's answer. |
| F1c. A server given with `--mcp-config <file> --strict-mcp-config` runs in a job, and with an empty one an enabled `.mcp.json` server does not start. | Pass | The test server given with `--mcp-config` answers the job; with `--mcp-config '{"mcpServers": {}}'`, the vault's `.mcp.json` server is not started even though the job settings enable it. The job runner relies on it: each job starts only the copy of its connected servers. |
| F2. A claude.ai connector can be used by a job. | **Fail** | Connectors load in job mode (tool names `mcp__claude_ai_<Name>__<tool>`), but `mcp__claude_ai_Context7__query-docs` is refused under `dontAsk` with its exact allow rule, while a `.mcp.json` server's tool with the same kind of rule runs (F1b). Checked by hand on the same connector: a whole-server rule `mcp__claude_ai_Context7` is refused too. Not checked: other connectors, whether a per-tool permission set on claude.ai changes this, and the launchd case. |
| F3. `permission_denials` names a refused MCP tool in full. | Pass | `mcp__facts__get_fact`, `mcp__facts__create_fact`. |
| F4. A rule in `.claude/settings.local.json` (where an interactive "don't ask again" goes) does not reach a job. | Pass | With `--setting-sources project`, the tool it allows is refused in the job and never runs; the runner always passes that flag. That the interactive answer is written to that file is Claude Code's documented behaviour, not checked here. |
| F5. With `dontAsk`, a prefix rule covers a redirection. | Pass (answer: no) | `Bash(echo f5:*)` refuses `echo f5 > f5.txt`; the file is not written. |
| F6. A skill's `allowed-tools` grants tools to a job. | Pass (answer: no) | A skill with `allowed-tools: Bash(echo f6:*)`, run through `Skill`, is refused the command. |
| F7. The first `system`/`init` message of `--output-format stream-json --verbose` lists the MCP servers and tools a job sees. | Pass, with a limit | Servers from `.mcp.json` are listed. claude.ai connectors load asynchronously and are often missing from `init` (present in only a few runs); with F2 failing, jobs cannot use them anyway. |
| F8b. The result of a command the sandbox stopped is marked `is_error` and ends with its `<sandbox_violations>` block. | Pass | The runner reads blocked hosts only from such results. |
| F9. A `${NAME}` in the `env` of a server given with `--mcp-config` is filled from the environment of the run. | Pass | The test server answers the value of a variable set only in the environment of `claude`. The adapters that need a key rely on it. |
| F10. Under `--output-format stream-json`, a refusal of the guard hook reaches the runner. | Pass, not on stderr | The call is a permission denial, and its tool result is an error that starts with `PreToolUse:<tool> hook error: [<hook command>]: BLOCKED by control-tower guard: <reason>`; stderr holds nothing. The runner labels the denial of that id as the guard's, with its reason. |
| F8. When the sandbox blocks a command's network access, the blocked host is visible. | Pass | The command's tool result, in the tool results of `--output-format stream-json` (which the runner reads), starts with `Exit code 1` and ends with `<sandbox_violations> deny network-outbound api.github.com:443 (user denied) </sandbox_violations>`. |

Hosts the known command-line tools tried first, each run in the sandbox with no host allowed: the host is the one named in the sandbox's refusal (`deny network-outbound <host>:443`).

| Command | Host |
|---|---|
| `gh api /zen` | `api.github.com` |
| `TWG_AGENT_DEFAULTS=1 twg jira workitem query --jql ...` | `api.atlassian.com` |
| `slackcli conversations unread` | `<workspace>.slack.com` (the company's Slack workspace) |

Only the first blocked host shows: once it is allowed, a command may need more. `twg` reaches Atlassian's shared API host, not the company's `<site>.atlassian.net`.

## Not checked by the script

- F2 when the job is started by launchd, outside a login shell.
- How an MCP server that needs a sign-in shows in the init message (`needs-auth` is assumed; without it, the diagnosis falls back to the error text).
- A6: on a Mac without developer tools, the first `git` or `python3` call opens the dialog that installs them, Python 3.9 or newer included.
- A7: the Claude desktop app lists the vault folder in its recent folders after a session on it.

## What follows for the kit

- Jobs cannot see user-scope servers (F1), so the adapters add servers to the vault's `.mcp.json` (`--scope project`). A job does not load that file: when a tool is connected, the installer copies the server's entry into the job's own `mcp.json`, and the runner passes it with `--strict-mcp-config` (F1c), so a later change to the vault's entry is never started.
- claude.ai connectors, Gmail included, cannot be used by local jobs (F2). Scheduled use of a connector needs a cloud routine on claude.ai.
- Interactive approvals (F4) and skills (F6) cannot widen a job.
- A prefix rule does not cover a redirection (F5); the sandbox stays the boundary for what an allowed command does.
- To show a blocked host to the user, or the guard's refusals, the runner reads the tool results of `stream-json` (F8, F8b, F10).
