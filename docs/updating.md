# Updating

The kit and your vault are two different things. Updating one never overwrites your work in the other.

| | Where | What it is | Who changes it |
|---|---|---|---|
| **The kit** | the folder you cloned (`control-tower-agentic/`) | the source: core vault, packs, adapters, installer, scheduler | the project; you get new versions with `git pull` |
| **Your vault** | the folder you chose (`~/control-tower-vault/`) | your notes, plus the skills, templates, dashboards and pages the installer copied in | you, every day |
| **The runtime** | `~/.control-tower/` | the job runner, the guard, each job's prompt and permissions, the schedule | the installer only: never edit it |

Pulling the kit changes nothing in your vault or runtime by itself. The update step below copies what changed, carefully.

## Update from your vault

In Claude, in your vault, say "update the kit" (or type `/control-tower` and ask for it). Claude checks how far behind the kit is and what changed (`installer/configure.py update`), and asks before anything happens. On yes, `configure.py update --apply --to <the version shown>`:

1. moves the kit's folder to exactly that version (a fast-forward, no new download); if a developer changed or committed anything there, or the move would overwrite a file the kit does not track, it stops and changes nothing;
2. hands over to the new version's `configure.py refresh`, which applies your answers like any change: if this version gives jobs more access (a new report, a new tool, a new web address), it lists it and changes nothing until you say yes; files you edited are kept, and the automatic runs are loaded again only if they were loaded.

Claude then checks the setup, offers for each kit file you had edited to merge the new parts into your version, and names the cloud routines whose prompt changed (they are not updated automatically). When you say "Not now" to new access, nothing was written and the kit's folder goes back to the version it was on. When the refresh fails after it started writing, the kit stays on the new version and the next check shows the update as "pending", as it does for a kit moved without being installed (a developer's `git pull` alone).

### Knowing when to update

"hello control tower" and "check my setup" say in one line when a new version is ready. With automatic reports, a notification says it too, once a week (Mondays 09:00): "A new version of the control tower is ready. Open Claude on your <vault> folder and say: update the kit." ([Scheduling](scheduling.md)). Nothing changes until you say yes.

## Update with three commands (developers)

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
| A translated kit file (a vault in another language than English) | Written again with its translation, from `.control-tower/translation.json`; Claude translates the texts the new version adds. |
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

In Claude, in your vault, type `/control-tower` and say what you want in your own words: "add the product profile", "I moved from Jira to Linear", "move the triage to 9:00", "stop the debt review". Claude shows what changes (reports added or removed, what they may use) and applies it after your yes. New files are added; nothing you wrote is touched. Removing a profile does not delete its notes.

## With the guided installer

In Claude Code, in the kit folder, `/install-control-tower update` does all of the above: it pulls nothing by itself (run `git pull` first), shows the dry run, applies it after your yes, and offers to merge your edited files.
