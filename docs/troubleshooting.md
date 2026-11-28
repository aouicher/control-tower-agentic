# Troubleshooting

Start with the health check: in Claude, in your vault, type `/control-tower` and choose "Check my setup". It runs the kit's doctor (`installer/doctor.py`) and explains each warning in plain words.

| Symptom | Cause and fix |
|---|---|
| Obsidian shows "Invalid properties" | A frontmatter value contains `: ` or ` #` unquoted. Wrap it in double quotes. |
| Task queries are empty | Tasks plugin not installed or enabled (Settings, Community plugins). |
| Dashboards do not render | Enable the Bases core plugin. |
| `claude CLI on PATH` warning | Install Claude Code, then ask `/control-tower` in your vault to check the setup again. |
| A job does nothing | Run it by hand; read the newest file in `~/.control-tower/logs/`. |
| A job reports `BLOCKED by control-tower guard`, or its log says `denied: N` | The job tried something it may not use. In Claude Code, in the vault, run `/job-permissions`: it explains each refusal and asks whether to allow it (refusals are in `~/.control-tower/logs/<job>.denials.json`). Some things can never be allowed: see [permissions](permissions.md). |
| A job is missing after install | A capability it needs was set to `none`. The installer lists skipped jobs. |
| Scheduled job did not run | The computer was asleep or off, or automatic runs are not turned on. Ask `/control-tower` in your vault to check the setup: it says whether they are loaded, and can turn them on. |
| Numbers look too low | The query hit a limit. Reports must say "at least N (truncated)"; if not, fix the prompt. |
| Installer says files were kept | Existing files are never overwritten. To get the kit's version of a file back, ask `/control-tower` in your vault for a fresh copy: your version is kept in `_system/archive/`. |

Still stuck? Open an issue with the output of `doctor.py --json` (it contains no secrets).
