# Adapter: Google Analytics (analytics)

Official documentation: https://developers.google.com/analytics/devguides/MCP (source: https://github.com/googleanalytics/google-analytics-mcp)

## Setup

Google publishes an MCP server as the PyPI package `analytics-mcp`. Requirements: Python 3.10+ and `pipx` or `uv`. Documented run command for Claude: `pipx run analytics-mcp`. The kit adds `--spec analytics-mcp` so pipx always runs the PyPI package, never a file of that name in the vault folder. In Claude Code:

```
claude mcp add --scope project analytics-mcp -- pipx run --spec analytics-mcp analytics-mcp
```

The server name is a local choice. Enable the APIs `analyticsadmin.googleapis.com` and `analyticsdata.googleapis.com` in the Google Cloud project, and set `GOOGLE_CLOUD_PROJECT` to its id.

## Authentication and least-privilege scopes

- Application Default Credentials with the read-only scope `https://www.googleapis.com/auth/analytics.readonly`.
- User credentials: `gcloud auth application-default login` with the `analytics.readonly` and `cloud-platform` scopes (exact flags: see the official page).
- Or a service account: `GOOGLE_APPLICATION_CREDENTIALS` pointing to its key file (keep it outside the repository and the vault), or `--impersonate-service-account`.
- The identity needs the Viewer role (`roles/analytics.viewer`) on the property.
- The documentation states the server is for read requests only and cannot create, modify or delete configuration.

## Commands or tools to call

Admin API: `get_account_summaries`, `get_property_details`, `list_google_ads_links`, `list_property_annotations`. Data API: `get_custom_dimensions_and_metrics`, `run_report`, `run_realtime_report`, `run_funnel_report`, `run_conversions_report`. Report parameters (dimensions, metrics, date ranges, limits): check the official documentation of the GA4 Data API.

## Field mapping to the contract

| Contract field | Google Analytics |
|---|---|
| `metric` | GA4 metric name (for example the one returned by `run_report`) |
| `period`, `previous_period` | two date ranges in the same report request |
| `value` | metric value for each range |
| `segment` | dimension filter or audience applied |

## Pitfalls

- Metric names are GA4 API names, not the interface labels: look them up with `get_custom_dimensions_and_metrics` or the official metadata.
- Data API results can be sampled or thresholded, and recent days can still change. The report response carries metadata about this: check the official documentation and state it.
- Reports are row-limited: say "at least N rows" when the limit is reached.
- Pick one property id explicitly: accounts often hold several properties.
- Do not store user-level identifiers in the vault.

## Verification

Ask Claude Code: "Call get_account_summaries." A list of accounts and properties confirms the credentials.
