# Adapters: connecting your tools

Jobs and skills ask for a **capability**, not a product. You choose the tool for each capability at install time, and the matching adapter tells Claude how to read it.

| Capability | Meaning | Tools |
|---|---|---|
| `calendar` | Your meetings | Google Calendar |
| `tracker` | Tickets and tasks | Jira, Linear, GitHub Issues, Asana |
| `code` | Pull requests, releases | GitHub |
| `errors` | Production errors | Rollbar, Sentry |
| `quality` | Code quality gates | SonarQube |
| `logs` | Service logs | CloudWatch, Datadog |
| `analytics` | Product and web metrics | Google Analytics, Amplitude |
| `crm` | Customers and deals | HubSpot |

## How an adapter works

- `adapters/<capability>/contract.md` defines the inputs a job gives and the records it expects back, so every tool answers in the same shape.
- `adapters/<capability>/<tool>.md` explains the tool: how to connect, what to verify.
- `adapters/<capability>/<tool>.json` is the machine-readable manifest: other names people give the tool (`aliases`, lowercase, for example `ga4`; the guided install matches the tools the user names against them and the tool id), how it is connected (`connect`: `sign-in` when the user does it alone from the vault, `developer` when it needs a key, a secret or an address filled in), install commands, environment variables, `permissions_allow` / `permissions_deny`, whether the tool is `read_only`, and a `read_only_mitigation` when it is not.

The installer renders the notes into `<vault>/.claude/adapters/` and writes the exact commands to `<vault>/library/setup-next-steps.md`. **It does not run them.**

## Connecting a tool

In Claude, in your vault, type `/control-tower` and say "connect" and the tool's name. Claude:

1. adds the tool to the vault's own `.mcp.json` after your yes (scheduled reports only see the vault's servers, not the ones added for your user account: see [runtime facts](design/runtime-facts.md));
2. asks you to sign in with `/mcp`;
3. runs Claude once the way a report runs (`configure.py probe`), shows you what the server runs, and records the server name reports really see and a fingerprint of its entry (`configure.py connect`), so the adapter's read tools match it. Each report gets its own copy of the entries of the connected servers it uses, as they were when connected, and starts nothing else (`--strict-mcp-config`); jobs cannot read `.mcp.json`, and write only Markdown notes, so they cannot plant a file a server would run. If the vault's entry changes later, reports keep the approved copy until the next change of setup drops it, and the setup check asks you to connect the tool again;
4. for a tool whose adapter lists no read tool (Jira, Linear), asks which of its read tools reports may use (`configure.py set-permissions`); tools that act are never offered.

A command-line tool (`gh`), a tool that needs a secret key or a client secret (Rollbar, SonarQube, CloudWatch, Google Analytics, Asana, HubSpot) or one whose address names your own organization (Sentry) is set up once by someone comfortable with the terminal, from the adapter note, run from the vault folder. A key stays a reference read from the environment (`--env 'NAME=${NAME}'`, in single quotes), never written into the vault, so the variable must also be set where scheduled reports run (launchd or cron do not read your shell profile). Claude never asks for or handles a key. Once the server is in the vault's `.mcp.json`, anyone can say "connect" and the tool's name to finish from step 2. A claude.ai connector works when you talk to Claude, but only reports that run on claude.ai can use it.

## Connecting a tool the kit does not know

Say "connect" and the tool's name anyway: `/control-tower` asks how it connects.

- **An MCP address** (a URL): after your yes, Claude adds it to the vault's `.mcp.json` (`configure.py add-server`: an `https` address on a public host, with no key, password or parameters in it; anything else is for a developer to set up), you sign in with `/mcp`, and you choose which of its read tools reports may use (tools that act are never offered). `configure.py add-connection --server` records it as `connections.<id>` in the answers, with a fingerprint of its entry, like a known tool.
- **A command-line tool** (usually for developers): you name the command and choose which of its read subcommands reports may use. Its web addresses come from `adapters/commands.json` or from your answer (`configure.py add-command --host`, or `--no-network`); `configure.py add-connection --command` refuses a command whose addresses are not known yet.
- **A claude.ai connector** (Gmail): it works when you talk to Claude, but reports on this computer cannot use it. `configure.py add-connection --connector <name>` records it for your reports that run on claude.ai as cloud routines; its tools are the ones allowed for the connector on claude.ai.

A connection gives no report anything by itself: reports use it once you choose it as a source for one of your own reports. `configure.py remove-connection` forgets it; a command's recorded addresses cannot be removed while a connection uses the command.

## Read-only

Jobs are read-only on external systems. Where a tool has no read-only mode, use an account with view-only permissions and allow only read tools by exact name. Wildcard MCP permissions are rejected by the tests. Adapter status `documented` means written from the tool's documentation, `verified` means tested against a live account.

## Command-line tools in jobs

A job that runs a command runs it in Claude Code's sandbox, which reaches only the web addresses the job was given. `adapters/commands.json` lists the addresses of known tools, measured with the real CLI ([runtime facts](design/runtime-facts.md)): `gh` reaches `api.github.com` (and needs `enableWeakerNetworkIsolation` on macOS for its certificate checks), `twg` reaches `api.atlassian.com`, and `slackcli` reaches the company's own Slack address, which the person granting it is asked for. The table can also set an environment switch for a command (`env`): `slackcli` runs with `SLACKCLI_NO_UPDATE_NOTIFIER=1`, so its update check never reaches a host the job may not; only the kit's table sets one, never the answers. For any other command, `/job-permissions` asks which address it talks to before allowing it, and records the answer as `commands` in the answers (`installer/configure.py add-command`). Addresses are exact public host names: no wildcard, no IP address, no local-only name (`.local`, `.localhost`, `.internal`). A public name that points to a private address is not detected: check the address you give. An address recorded for a command applies to every job that is allowed that command; `/job-permissions` can take it back.

## Adding an adapter

Copy a sibling manifest, keep to the capability contract, and run the tests. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## Your own tool for a capability

A capability can be served by a tool you already have instead of one of the kit's: `"tools": {"logs": "connection:<id>"}`, where `<id>` is one of your connections to an MCP server or a command (`configure.py add-connection`; a claude.ai connector cannot serve reports on this computer). The kit's reports that need the capability then get that connection's read tools and server, and `.claude/adapters/<capability>.md` points them to `.claude/adapters/<capability>-guide.md`, your vault's guide to querying it, which `/control-tower` writes with you ("Use one of your connections for a capability") from a skill, a note or a document you already have. Without the guide, a report queries nothing and says so; the setup check warns. Cloud routines never count on it: only this computer reaches the connection. Set it with `configure.py set --tool logs=connection:<id>`: the change shows the reports that start using it and needs your yes.
