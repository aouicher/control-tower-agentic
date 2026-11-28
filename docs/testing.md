# Testing

Every test runs in throwaway directories. None touches your real vault, `~/.claude`, `~/Library/LaunchAgents` or your crontab, and none calls Claude or any external tool.

| Level | Command | What it proves |
|---|---|---|
| Unit | `python3 -W ignore -m unittest discover -s tests -p "test_*.py"` | Rendering, packs, adapters, permissions, guard rules, runner, schedule files, docs links |
| End to end | `python3 tests/e2e/run_e2e.py` | For each pack and all packs together, in a disposable `HOME`: dry run, install, idempotent re-install, doctor, every job through the real runner, guard blocks hostile calls, schedule generated (plists linted on macOS), uninstall keeps your edits |
| Clean Linux | `docker build -f tests/e2e/Dockerfile -t control-tower-e2e . && docker run --rm --network none control-tower-e2e` | The same on a fresh Debian with Python 3.9, unprivileged user, no network, and the crontab block really loaded then removed |
| Leaks | `python3 tools/scan-leaks.py --strict` | No secret patterns, no private terms (from your local `.denylist.local`), English only |

## The real `claude` (opt-in)

```bash
CT_REAL_CLAUDE=1 python3 tests/e2e/smoke_real_claude.py
```

Installs the developer pack in a temporary folder whose path holds a space and a quote, swaps one job's prompt for a short probe and runs it with the real CLI on Haiku (about one cent). It checks what Claude Code itself allowed: the report is written in the vault, `.claude/settings.json` is refused, a write outside the vault is blocked. It is the only test that exercises Claude Code's permission rules; run it after changing permissions or upgrading Claude Code.

```bash
CT_REAL_CLAUDE=1 python3 tests/e2e/smoke_real_claude.py --facts
```

Checks, with the real CLI in temporary folders, the Claude Code behaviours the kit relies on: which MCP servers and connectors a job sees, how refusals are reported, whether interactive approvals or a skill's `allowed-tools` can widen a job, and whether the sandbox shows the host it blocked. It prints PASS, FAIL or UNKNOWN per fact (a dozen Haiku calls, a few cents) and exits non-zero unless all pass. It adds no MCP server and changes no setting. Record the results in [docs/design/runtime-facts.md](design/runtime-facts.md) after upgrading Claude Code.

## The fake `claude`

`tests/e2e/fake_claude.py` replaces Claude Code (through `CT_CLAUDE_BIN`). It reads the job's settings, replays hostile tool calls through the guard hook those settings declare (git push, credential reads, edits to `.claude/settings.json`, writes outside the vault, secret globs) and fails if one is not blocked. It then writes one allowed report and prints the JSON the runner expects.

## A real run (optional, costs tokens)

After installing with your own answers, run one job by hand with the real CLI and read its log:

```bash
python3 ~/.control-tower/bin/run_job.py --job <id> --ct-home ~/.control-tower
tail -n 40 ~/.control-tower/logs/<id>.log
```

CI runs the unit, end-to-end and leak checks on macOS (Python 3.9 and 3.13) and Ubuntu (Python 3.13), plus the container test on Python 3.9; the private denylist stays local, so CI scans generic patterns only (`.github/workflows/ci.yml`).
