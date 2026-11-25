# Contract: crm (customers, campaigns, email)

## Purpose

Lets jobs report marketing and sales activity (campaigns, email performance, deals) from a CRM or marketing platform (HubSpot, ...), as aggregates.

## Inputs the job gives

| Input | Meaning |
|---|---|
| `campaigns` | Campaign or list names or ids to report (or "all active") |
| `period` | Absolute start and end dates and timezone |
| `previous_period` | Same-length period to compare with |

## Outputs it expects (fields)

| Field | Meaning |
|---|---|
| `campaign_or_list` | Name and id of the campaign, email or list |
| `period` | Start and end dates, timezone |
| `sends` | Emails sent |
| `opens` | Opens (state whether the tool counts machine opens) |
| `clicks` | Clicks |
| `conversions` | Conversions as the tool defines them |
| `deals_created` | Deals created and attributed in the period |

No personal data: no names, emails, phone numbers or per-contact rows.

## Pagination and truncation

- Search results are paged and capped per page. Page until exhausted or report "at least N".
- Aggregate analytics first; list individual records only to count them.

## Pitfalls

- State the period in every figure and compare like with like (same length).
- Never report numbers from a sampled export without saying so.
- Open rates can be inflated by automated mail clients: do not over-interpret them.
- Attribution rules differ between tools: quote the tool's definition.
- Do not store customer personal data in the vault. Keep aggregates, ids and links.
- Sensitive-data settings in the tool can hide some content: an empty result may mean "blocked", not "none".

## Read-only guarantees

Read permissions only. Never create or update records, campaigns, emails, segments or content, and never send mail.

Some tools have no read-only mode (see `read_only` and `read_only_mitigation` in the adapter manifest). For those, the guarantee comes from the mitigation (view-only account, restricted role or token, denied write tools), not from the tool: apply it before use and never call a write tool.

## Failure handling

- No access to an object type: report it as "not available" with the tool's message.
- Empty result: state the period and filters used.
- Cap reached: report "at least N".
