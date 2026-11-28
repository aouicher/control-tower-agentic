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
2. asks how routines that write notes reach the vault: through your computer, linked to the routine, or through the vault's GitHub repository,
3. skips routines that already exist on your account, so running it twice creates no duplicates,
4. asks one question, which routines to create, and creates exactly the ones you tick,
5. gives you the claude.ai link and next run time of each one.

What it needs from you: Claude Code signed in to your claude.ai account, a way to reach the vault for routines marked `vault: write` (your computer linked to the routine, or the vault in a GitHub repository), and the listed connectors connected on claude.ai.

What it never does: update or delete a routine (an update through the API replaces the whole configuration; change routines on claude.ai), handle your credentials, or create a routine you did not tick. `uninstall.py` does not remove cloud routines: delete them on claude.ai.

By hand instead: open claude.ai routines, create one, paste the content of the `.prompt.md` file, set the schedule and connectors.

### Cloud routines and your local vault

A routine reaches the vault in one of two ways:

| | Linked computer | GitHub repository |
|---|---|---|
| How | In the routine's settings on claude.ai, link the computer that holds the vault | Put the vault in a GitHub repository and attach it to the routine |
| Runs | On your computer, which must be on and awake at that time | In the cloud, even when your computer is off |
| Sees the local jobs' reports | Immediately, same folder | Only after the local vault is pushed (Obsidian Git plugin, auto commit and push every few minutes) |
| Its own writes | In place, nothing to sync | Committed and pushed to the default branch: pull to see them (Obsidian Git does it) |
| Best for | A vault on one machine, routines that follow local jobs | Several machines, or routines that must run while the laptop sleeps |

Whatever the mode, a routine that finds a report missing or older than today says so and continues with what it has.

## Writing rules for unattended prompts

Never ask questions, be read-only on external systems, always pass explicit limits and paginate, tag proposed tasks `#to-triage`, and never include secrets or customer data.

Dates come from the runner. Before each run, `run_job.py` puts a `## Run context` block at the top of the prompt, in the timezone you installed with: now, today, the year, the current ISO week, the last complete ISO week, the week before it and the previous working day, each week with its Monday and Sunday. A prompt takes its dates from there and never runs `date`; it finds vault notes with the Glob tool, never `ls`. A skill that a job follows says so before its first `date` command, so the same skill still works in an interactive session. Tests check both (`tests/test_run_context.py`).
