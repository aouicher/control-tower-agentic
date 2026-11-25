---
id: weekly-review
name: "Weekly review"
days: fri
time: "16:30"
connectors_required: []
connectors_optional: []
vault: write
after: "product-weekly"
---

# Routine: weekly review

Writes the weekly review with the product loop section.

| Setting | Value |
|---|---|
| Schedule | fri at 16:30 ({{ct.timezone}}), after the `product-weekly` job |
| Connectors | required: none; optional: none |
| Vault | Needs the vault repository attached to the routine (it writes notes). |

The guided installer can create this routine for you (`/install-control-tower`). To create it by hand, paste everything under **Prompt** into a new claude.ai routine.

## Prompt

Unattended routine: never ask, never wait. Read-only on external systems; write only inside the vault repository attached to this routine. Follow CLAUDE.md. Write in English.

1. Get the ISO week with `date +%G-W%V`.
2. Follow .claude/skills/weekly-review/SKILL.md for the week, without asking questions: leave the "Wins and lessons" section with a placeholder for me to fill.
3. Add a "Product loop" section: interviews added this week (count from library/interviews/ by interview_date), opportunities by stage (count only what you read in full), opportunities with incomplete scoring inputs, and {{ct.workstreams}} with no activity this week.
4. Link the latest journal/reports/product-weekly-<week>.md if it exists; otherwise say it is missing.
5. Propose the top 3 for next week. Proposed tasks carry #to-triage; you cannot check for duplicates, so propose only new, important items. Never write rag, owner, due or stage of existing notes, and never change an opportunity's stage.
