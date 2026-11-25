# Updating

The kit and your vault are two different things. Updating one never overwrites your work in the other.

| | Where | What it is | Who changes it |
|---|---|---|---|
| **The kit** | the folder you cloned (`control-tower-agentic/`) | the source: core vault, packs, adapters, installer, scheduler | the project; you get new versions with `git pull` |
| **Your vault** | the folder you chose (`~/control-tower-vault/`) | your notes, plus the skills, templates, dashboards and pages the installer copied in | you, every day |
| **The runtime** | `~/.control-tower/` | the job runner, the guard, each job's prompt and permissions, the schedule | the installer only: never edit it |

Pulling the kit changes nothing in your vault or runtime by itself. The update step below copies what changed, carefully.

## Update in three commands

```bash
cd ~/control-tower-agentic
git pull
python3 installer/install.py --answers ~/control-tower-vault/.control-tower/answers.json --update --dry-run
```

The dry run lists what would change. If it looks right, run it again without `--dry-run`:

```bash
python3 installer/install.py --answers ~/control-tower-vault/.control-tower/answers.json --update
```

Replace `~/control-tower-vault` with your vault folder. The installer saved your answers in `.control-tower/answers.json` the first time, so you are not asked the questions again. Read [CHANGELOG.md](../CHANGELOG.md) first: it says when an update needs anything else.

## What the update does

| File in your vault | What happens |
|---|---|
| Your own notes (projects, meetings, daily notes...) | Never touched: they did not come from the kit. |
| A kit file you **never edited** (a skill, a template, a dashboard) | Replaced by the new version. |
| A kit file you **edited** (for example your `CLAUDE.md`) | Kept as it is. The new version is saved in `.control-tower/updates/<date>/` so you can merge what you want. |
| A kit file you **deleted** | Left deleted. |
| A file that is **new** in the kit | Added. |
| The runtime (`~/.control-tower/`: guard, job prompts, permissions, schedule files) | Always refreshed: this is where most security fixes land. |

The installer knows which files you edited because it stored a checksum of every file it installed in `.control-tower/manifest.json`.

### Merging your edited files

After an update, if some files were kept because you edited them, the output lists them. Compare each one with its new version in `.control-tower/updates/<date>/`, or let Claude do it from the vault:

```text
merge the kit updates from .control-tower/updates: keep my changes, add what is new, show me the diff before writing
```

Delete the `.control-tower/updates/<date>/` folder once you are done. Until a file is merged, every update keeps reporting it.

## After the update

1. Run the health check: `python3 installer/doctor.py --vault ~/control-tower-vault`.
2. If you use a schedule, re-apply it so new or renamed jobs are registered: add `--apply-schedule` to the update command.
3. **Cloud routines are not updated** (they live on your claude.ai account). If the changelog says a routine prompt changed, open the routine on claude.ai and paste the new prompt from `~/.control-tower/routines/<name>.prompt.md`, or delete it and run `/install-control-tower routines` again.
4. Optional: run one job by hand to check it, `python3 ~/.control-tower/bin/run_job.py --job <job id> --ct-home ~/.control-tower`.

## Adding a pack or a tool later

Edit `.control-tower/answers.json` (add the pack to `packs`, or set a tool under `tools`), then run the update. New files are added; nothing you wrote is touched. Removing a pack does not delete its files: archive them yourself if you no longer need them.

## With the guided installer

In Claude Code, in the kit folder, `/install-control-tower update` does all of the above: it pulls nothing by itself (run `git pull` first), shows the dry run, applies it after your yes, and offers to merge your edited files.
