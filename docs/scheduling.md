# Scheduling

## Local jobs

Each installed job lives in `~/.control-tower/jobs/<id>/` (`prompt.md`, `job.json`, `settings.json`). The runner is `~/.control-tower/bin/run_job.py`:

```bash
python3 ~/.control-tower/bin/run_job.py --job morning-prs --ct-home ~/.control-tower
```

It starts `claude -p` in the vault with:

- `--permission-mode dontAsk`: anything not explicitly allowed is refused, nothing waits for a human,
- a per-job `settings.json`: reads, vault-scoped edits and the adapter's read tools only,
- a PreToolUse guard hook ([security](security.md)),
- a lock so two runs of one job never overlap, a timeout (30 minutes by default) and logs in `~/.control-tower/logs/`.

Try each job by hand first.

### Scheduler choice

| Value | Behaviour |
|---|---|
| `auto` | launchd on macOS, cron on Linux |
| `launchd` | writes plists to `~/.control-tower/schedule/launchd/` |
| `cron` | writes `~/.control-tower/schedule/crontab.txt` (a `# BEGIN control-tower` block) |
| `none` | no schedule files |

Files are generated but **not loaded** until you run the installer with `--apply-schedule` (symlinks plists into `~/Library/LaunchAgents` and loads them, or installs the crontab block). `uninstall.py` reverses both. Times in `job.json` use your timezone; the generated schedule uses the machine's local time.

A laptop that is asleep misses its run. If that matters, use a cloud routine.

## Cloud routines

Each pack ships prompts in `packs/<id>/routines/`. To use one:

1. Open claude.ai, Routines (scheduled agents), create a new routine.
2. Paste the prompt below the `---` line, set the suggested schedule and the connectors it lists.
3. Attach the vault repository only if you want the routine to write into it.

Cloud routines cannot be created or edited by the installer: they are configured by you on claude.ai.

## Writing rules for unattended prompts

Never ask questions, be read-only on external systems, always pass explicit limits and paginate, tag proposed tasks `#to-triage`, and never include secrets or customer data.
