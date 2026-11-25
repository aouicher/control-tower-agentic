# Contract: quality (code quality gates)

## Purpose

Lets jobs report the quality state of each repository from a code quality platform (SonarQube, ...): gate status, freshness of the analysis and the main metrics.

## Inputs the job gives

| Input | Meaning |
|---|---|
| `repositories` | Repository names to inspect |
| `branch` | Branch to read (default: the main branch) |
| `projects` | Optional explicit mapping repository to project key |

## Outputs it expects (fields)

| Field | Meaning |
|---|---|
| `project_key` | Key of the project in the quality tool |
| `repository` | Repository it was matched to, and how it was matched |
| `gate_status` | `passed`, `failed`, `none` (no gate or never analysed) |
| `last_analysis` | ISO 8601 date of the last analysis |
| `bugs` | Number of bugs |
| `vulnerabilities` | Number of vulnerabilities |
| `code_smells` | Number of code smells |
| `coverage` | Percentage, or `n/a` |
| `duplication` | Percentage of duplicated lines, or `n/a` |
| `technical_debt` | Remediation effort, with its unit (minutes or days, as the tool states) |

## Pagination and truncation

- Project lists are paged and often capped by default. Page until exhausted or report "at least N projects".
- Metrics are returned per branch and per time of analysis. State the branch.

## Pitfalls

- Project keys are inconsistent with repository names. Match repositories to project keys by name (case-insensitive, ignoring prefixes and separators), list the matches, and ask the user when several candidates exist. Never assume a key.
- A project not analysed for months is stale, not green. Always output `last_analysis` and flag anything older than the agreed threshold (default: 30 days).
- A gate status without a recent analysis proves nothing. Report "stale" instead of "passed".
- Coverage and duplication can be absent (not configured): report `n/a`, not 0.

## Read-only guarantees

Use a read-only token. Never change issue statuses, mark false positives, create webhooks or trigger analyses.

Some tools have no read-only mode (see `read_only` and `read_only_mitigation` in the adapter manifest). For those, the guarantee comes from the mitigation (view-only account, restricted role or token, denied write tools), not from the tool: apply it before use and never call a write tool.

## Failure handling

- Project not found: report the repository as "unmatched", never as healthy.
- Authentication error: stop and report "quality: no access".
- Missing metric: output `n/a` and keep the rest of the record.
