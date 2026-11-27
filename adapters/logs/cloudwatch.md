# Adapter: Amazon CloudWatch Logs (logs)

Official documentation: https://awslabs.github.io/mcp/servers/cloudwatch-mcp-server (AWS Labs MCP servers).

## Setup

The documented configuration runs the server locally with `uvx` (prerequisites: install `uv`, then `uv python install 3.10`): command `uvx`, args `awslabs.cloudwatch-mcp-server@latest`, env `AWS_PROFILE` and `FASTMCP_LOG_LEVEL=ERROR`, transport `stdio`. In Claude Code:

```
claude mcp add --scope user cloudwatch --env AWS_PROFILE=<read-only-profile> --env FASTMCP_LOG_LEVEL=ERROR -- uvx awslabs.cloudwatch-mcp-server@latest
```

The server name `cloudwatch` is a local choice. The documentation also gives a Docker variant and a Windows variant (which sets `AWS_REGION`). The page states the server can only run locally, on the same host as the client. The older `awslabs.cloudwatch-logs-mcp-server` is deprecated in favour of this one.

## Authentication and least-privilege scopes

- Uses your AWS credentials through `AWS_PROFILE`. Use a profile mapped to a read-only role.
- Permissions listed by the documentation: `cloudwatch:DescribeAlarms`, `cloudwatch:DescribeAlarmHistory`, `cloudwatch:GetMetricData`, `cloudwatch:ListMetrics`, `logs:DescribeLogGroups`, `logs:DescribeQueryDefinitions`, `logs:ListLogAnomalyDetectors`, `logs:ListAnomalies`, `logs:StartQuery`, `logs:GetQueryResults`, `logs:StopQuery`.
- The page does not state that the server is read-only. `logs:StartQuery` and `logs:StopQuery` start and stop queries (they do not change log data, and Logs Insights queries are billed by data scanned). Grant exactly the list above, nothing more.

## Commands or tools to call

Logs tools: `describe_log_groups`, `analyze_log_group` (anomalies, message and error patterns), `execute_log_insights_query` (returns a query id), `get_logs_insight_query_results`, `execute_cwl_insights_batch` (one query across several groups and regions, at most 50 groups, 10,000-record split). Timestamps are ISO 8601 with a timezone. Use `| limit N` in queries to bound results. Scheduled jobs are not allowed `cancel_logs_insight_query`: an unfinished query expires on its own.

Logs Insights query language syntax: check the official AWS documentation for CloudWatch Logs Insights.

## Field mapping to the contract

| Contract field | CloudWatch |
|---|---|
| `resource` | full log group name (or ARN) passed to the query |
| `window` | `start_time` and `end_time` given to the query |
| `records_scanned` | scanned-records statistic returned with the query results, check the official documentation for the field name |
| `error_count`, `top_signatures`, `first_seen` | result of an aggregate query (`stats count(*) by ...`, `min(@timestamp)`) |

## Pitfalls

- Pass the full log group name or ARN, and the right region and profile: the same short name can exist in several accounts.
- One log group per call for the contract. Use the batch tool only for the same query on comparable groups.
- Prefer `stats count(*) by <signature>` over reading raw messages.
- Level field depends on the format: JSON logs expose a level field, plain-text logs need a message pattern match. Check a sample first.
- Zero records scanned is a coverage gap (wrong group, window or ingestion delay), not a healthy service.

## Verification

Ask Claude Code: "Describe the log groups starting with <prefix>." Then run a count over the last hour on one group and check `records_scanned` is greater than zero.
