# Troubleshooting

Start with the health check:

```bash
python3 installer/doctor.py --vault <vault> --ct-home ~/.control-tower
```

| Symptom | Cause and fix |
|---|---|
| Obsidian shows "Invalid properties" | A frontmatter value contains `: ` or ` #` unquoted. Wrap it in double quotes. |
| Task queries are empty | Tasks plugin not installed or enabled (Settings, Community plugins). |
| Dashboards do not render | Enable the Bases core plugin. |
| `claude CLI on PATH` warning | Install Claude Code, or set `claude_bin` in the answers file. |
| A job does nothing | Run it by hand; read the newest file in `~/.control-tower/logs/`. |
| A job reports `BLOCKED by control-tower guard`, or its log says `denied: N` | The job tried something it may not use. In Claude Code, in the vault, run `/job-permissions`: it explains each refusal and asks whether to allow it (refusals are in `~/.control-tower/logs/<job>.denials.json`). Some things can never be allowed: see [permissions](permissions.md). |
| A job is missing after install | A capability it needs was set to `none`. The installer lists skipped jobs. |
| Scheduled job did not run | Machine was asleep or off, or the schedule was never applied (`--apply-schedule`). Check `launchctl list \| grep control-tower` or `crontab -l`. |
| "lock held" | A previous run is still active or crashed. Check the pid in the lock folder, remove it if the process is gone. |
| Numbers look too low | The query hit a limit. Reports must say "at least N (truncated)"; if not, fix the prompt. |
| Installer says files were kept | Existing files are never overwritten. Delete the file yourself to get a fresh copy. |

Still stuck? Open an issue with the output of `doctor.py --json` (it contains no secrets).
