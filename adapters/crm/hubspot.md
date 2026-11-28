# Adapter: HubSpot (crm)

Official documentation: https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server (also https://developers.hubspot.com/docs/build-with-ai/remote-mcp-server)

## Setup

HubSpot hosts a remote MCP server at `https://mcp.hubspot.com` (Streamable HTTP transport). Steps from the documentation:

1. In HubSpot, go to Development > MCP Connectors and create an MCP connector (name, redirect URL).
2. Copy the connector client id and client secret.
3. Configure your MCP client with the server URL, the client id and the secret. The client must support OAuth with PKCE (S256).
4. Complete the OAuth flow (select the account, grant permissions).
5. Run `get_user_details` to check what you can access.

The exact `claude mcp add` command and options for a connector with client credentials: check the official documentation of Claude Code and HubSpot. Add the server from the vault folder at project scope (`--scope project`): scheduled reports start only servers of the vault's `.mcp.json`. Never write the client secret into that file.

## Authentication and least-privilege scopes

- You do not define scopes directly: they come from the tools available at installation and the permissions the user grants. Access respects the user's HubSpot permissions.
- The documentation does not describe a read-only mode: the server exposes write tools (CRM records, campaigns, marketing email drafts, content, segments). Limit the risk by authorising with a user who has view-only permissions in HubSpot, by not granting optional write-related permissions at the consent screen when offered, and by never calling write tools (`manage_*`, record creation or update). This is a precaution derived from the documented permission model: check the official documentation for stricter options.
- Write actions generally require user confirmation: decline them.

## Commands or tools to call

Read tools named in the documentation: `get_user_details`, `search_crm_objects` (up to 5 filter groups, 6 filters per group, 200 results per page), `get_crm_objects` (up to 100 ids), `search_owners`, `search_properties`, `query_crm_data` (no joins or subqueries), `read_campaign_data`. Readable data includes campaigns, marketing email aggregate send analytics, deals and content analytics. Tool names for email analytics: check the official documentation.

## Field mapping to the contract

| Contract field | HubSpot |
|---|---|
| `campaign_or_list` | campaign (`read_campaign_data`) or marketing email name and id |
| `sends`, `opens`, `clicks` | aggregate send analytics of the marketing email or campaign |
| `conversions` | as defined by the campaign or email analytics: quote the definition |
| `deals_created` | count from `search_crm_objects` on deals with a create-date filter |
| `period` | the date filters used |

## Pitfalls

- Never read or keep per-contact engagement or conversation content: aggregates only.
- If Sensitive Data is enabled in the account, conversation data is blocked: an empty result can mean "blocked".
- Search is paged (200 per page): say "at least N" when you stop early.
- Tool availability depends on subscription, permissions and account configuration.
- Compare same-length periods and state them.

## Verification

Ask Claude Code: "Run get_user_details for HubSpot." The reply lists the account and accessible tools.
