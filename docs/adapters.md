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
- `adapters/<capability>/<tool>.json` is the machine-readable manifest: install commands, environment variables, `permissions_allow` / `permissions_deny`, whether the tool is `read_only`, and a `read_only_mitigation` when it is not.

The installer renders the notes into `<vault>/.claude/adapters/` and writes the exact commands to `<vault>/library/setup-next-steps.md`. **It does not run them.**

## Connecting a tool

1. Open `library/setup-next-steps.md`.
2. Run the listed `claude mcp add ...` command yourself (or install the CLI the note names, for example `gh`). The commands use `--scope user`, so the server is visible from every interactive session, the vault included. Scheduled jobs do not see user-scope servers (checked with Claude Code 2.1.332, see [runtime facts](design/runtime-facts.md)): a job sees a server only when it is declared in the vault's `.mcp.json` and enabled in the job's settings, which the kit does not do yet. Until it does, jobs that rely on an MCP tool cannot reach it; command-line tools such as `gh` are not affected. A tool without a single command (HubSpot) lists its setup steps instead.
3. Authenticate when asked (usually in `/mcp` inside Claude Code). Never paste secrets into notes or chat.
4. Run the `verify` step from the adapter note.
5. Re-run `doctor.py`.

## Read-only

Jobs are read-only on external systems. Where a tool has no read-only mode, use an account with view-only permissions and allow only read tools by exact name. Wildcard MCP permissions are rejected by the tests. Adapter status `documented` means written from the tool's documentation, `verified` means tested against a live account.

## Command-line tools in jobs

A job that runs a command runs it in Claude Code's sandbox, which reaches only the web addresses the job was given. `adapters/commands.json` lists the addresses of known tools, measured with the real CLI ([runtime facts](design/runtime-facts.md)): `gh` reaches `api.github.com` (and needs `enableWeakerNetworkIsolation` on macOS for its certificate checks), `twg` reaches `api.atlassian.com`, and `slackcli` reaches the company's own Slack address, which the person granting it is asked for. For any other command, `/job-permissions` asks which address it talks to before allowing it, and records the answer as `commands` in the answers (`installer/configure.py add-command`). Addresses are exact public host names: no wildcard, no IP address, no local-only name (`.local`, `.localhost`, `.internal`). A public name that points to a private address is not detected: check the address you give. An address recorded for a command applies to every job that is allowed that command; `/job-permissions` can take it back.

## Adding an adapter

Copy a sibling manifest, keep to the capability contract, and run the tests. See [CONTRIBUTING.md](../CONTRIBUTING.md).
