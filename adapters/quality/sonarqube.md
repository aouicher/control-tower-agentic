# Adapter: SonarQube (quality)

Official documentation: https://docs.sonarsource.com/sonarqube-mcp-server/ (setup: https://docs.sonarsource.com/sonarqube-mcp-server/quickstart-guide/claude-code.md, tools: https://docs.sonarsource.com/sonarqube-mcp-server/reference/tools.md, variables: https://docs.sonarsource.com/sonarqube-mcp-server/reference/environment-variables.md).

## Setup

SonarQube Cloud (add `SONARQUBE_URL=https://sonarqube.us` for the US region only):

```bash
claude mcp add sonarqube \
  --env SONARQUBE_TOKEN=$SONARQUBE_TOKEN \
  --env SONARQUBE_ORG=$SONARQUBE_ORG \
  --env SONARQUBE_READ_ONLY=true \
  -- docker run -i --rm --init --pull=always -e SONARQUBE_TOKEN -e SONARQUBE_ORG -e SONARQUBE_READ_ONLY sonarsource/sonarqube-mcp
```

SonarQube Server: replace `SONARQUBE_ORG` with `SONARQUBE_URL` (your server URL). The documented quick-start commands do not include `SONARQUBE_READ_ONLY`; it is added here from the environment-variable reference. A configuration generator is linked from the official page: https://mcp.sonarqube.com/config-generator.html.

## Authentication and least-privilege scopes

- A **user token** is required; the documentation warns that project, global and scoped organization tokens do not bind correctly.
- Set `SONARQUBE_READ_ONLY=true` to disable write operations (documented: "disables all write operations, such as changing issue status").
- Give the token's user only browse permission on the projects to report. Token permission levels beyond that: check the official documentation.

## Commands or tools to call

Read tools: `get_project_quality_gate_status`, `get_component_measures`, `search_metrics`, `search_my_sonarqube_projects`, `list_branches`, `list_pull_requests`, `search_sonar_issues_in_projects`, `search_files_by_coverage`, `search_duplicated_files`. Never call `change_sonar_issue_status`, `change_security_hotspot_status` or `create_webhook`.

## Field mapping to the contract

| Contract field | SonarQube |
|---|---|
| `project_key` | key returned by `search_my_sonarqube_projects` |
| `gate_status` | result of `get_project_quality_gate_status` |
| `bugs`, `vulnerabilities`, `code_smells`, `coverage`, `duplication`, `technical_debt` | `get_component_measures` with the metric keys for each. Look the exact keys up with `search_metrics`; do not guess them |
| `last_analysis` | check the official documentation for the tool that returns the analysis date (branch listing may include it) |

## Pitfalls

- Project keys rarely match repository names: search by name, list candidates, confirm.
- A gate that "passed" months ago is stale: always read the analysis date.
- The Docker image name `sonarsource/sonarqube-mcp` is the documented one; the Docker MCP Hub image can lag behind.
- Results of project searches are paged: do not assume the first page is complete.

## Verification

Ask Claude Code: "Find the SonarQube project named <repository> and show its quality gate status." Run `/mcp` to confirm the server is connected.
