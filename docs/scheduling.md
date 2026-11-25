# Scheduling

## Local jobs

Each installed job lives in `~/.control-tower/jobs/<id>/` (`prompt.md`, `job.json`, `settings.json`). The runner is `~/.control-tower/bin/run_job.py`:

```bash
python3 ~/.control-tower/bin/run_job.py --job <job id from library/setup-next-steps.md> --ct-home ~/.control-tower
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

Files are generated but **not loaded** until you run `python3 installer/install.py --answers <vault>/.control-tower/answers.json --apply-schedule` (the installer saved your answers there) (symlinks plists into `~/Library/LaunchAgents` and loads them, or installs the crontab block). `uninstall.py` reverses both. Times in `job.json` use your timezone; the generated schedule uses the machine's local time.

A laptop that is asleep misses its run. If that matters, use a cloud routine.

## Cloud routines

Routines run on claude.ai on a schedule, even when your computer is off. Each pack ships some in `packs/<id>/routines/`: a frontmatter (schedule, connectors, vault need) and the prompt under `## Prompt`.

The installer renders the ones that fit your tools into `~/.control-tower/routines/` (one `<pack>--<id>.prompt.md` per routine, plus `routines.json`) and lists them. **It does not create them.** To create them:

```bash
claude
```

then, in the control tower repository, `/install-control-tower routines`. The assistant:

1. shows each routine with its schedule, connectors and vault need,
2. asks for the vault's GitHub repository when a routine writes notes (a cloud routine cannot see a folder on your computer),
3. skips routines that already exist on your account, so running it twice creates no duplicates,
4. asks one question, which routines to create, and creates exactly the ones you tick,
5. gives you the claude.ai link and next run time of each one.

What it needs from you: Claude Code signed in to your claude.ai account, the vault in a GitHub repository for routines marked `vault: write`, and the listed connectors connected on claude.ai.

What it never does: update or delete a routine (an update through the API replaces the whole configuration; change routines on claude.ai), handle your credentials, or create a routine you did not tick. `uninstall.py` does not remove cloud routines: delete them on claude.ai.

By hand instead: open claude.ai routines, create one, paste the content of the `.prompt.md` file, set the schedule and connectors.

### Cloud routines and your local vault

A routine sees the vault only through its GitHub repository, never the folder on your computer. Routines that read job reports (those with `after:`, such as a morning brief) need the local vault pushed first: install the Obsidian Git plugin and set it to commit and push automatically every few minutes, or push by hand. Routines that write (`vault: write`) commit and push to the default branch of that repository: pull it (Obsidian Git does this too) to see what they wrote. A routine that finds a report missing or older than today says the vault was not synced and continues with what it has.

## Writing rules for unattended prompts

Never ask questions, be read-only on external systems, always pass explicit limits and paginate, tag proposed tasks `#to-triage`, and never include secrets or customer data.
