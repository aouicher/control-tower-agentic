# Routine: weekly review

Paste into a claude.ai cloud routine, scheduled on Fridays at 16:30 ({{ct.timezone}}).

```
Unattended routine: never ask, never wait. Read-only on external systems; write only inside the vault at {{ct.vault_path}}. Follow CLAUDE.md. Write in English.

1. Get the ISO week with `date +%G-W%V`.
2. Follow .claude/skills/weekly-review/SKILL.md for the week, without asking questions: leave the "Wins and lessons" section with a placeholder for me to fill.
3. Add a "Product loop" section: interviews added this week (count from library/interviews/ by interview_date), opportunities by stage (count only what you read in full), opportunities with incomplete scoring inputs, and {{ct.workstreams}} with no activity this week.
4. Link the latest journal/reports/product-weekly-<week>.md if it exists; otherwise say it is missing.
5. Propose the top 3 for next week. Proposed tasks carry #to-triage; you cannot check for duplicates, so propose only new, important items. Never write rag, owner, due or stage of existing notes, and never change an opportunity's stage.
```
