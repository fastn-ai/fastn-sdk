"""CLI commands: fastn kit - manage the Connect Kit (connectors and configurations)."""

from __future__ import annotations

import json

import click

from fastn.cli import cli, OrderedGroup, GRAPHQL_URL
from fastn.cli._helpers import _ensure_fresh_token, _handle_401, _verbose_post
from fastn.config import load_config
from fastn._constants import (
    GET_CONNECTOR_QUERY,
    GET_KIT_CONNECTORS_QUERY,
    GET_KIT_METADATA_QUERY,
    SAVE_KIT_METADATA_MUTATION,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _require_auth():
    """Load config, verify auth, and return (config, headers, project_id)."""
    config = load_config()
    if not config.auth_token and not config.api_key:
        raise click.ClickException("Not authenticated. Run `fastn login` first.")
    _ensure_fresh_token(config)
    project_id = config.resolve_project_id()
    if not project_id:
        raise click.ClickException("No project configured. Run `fastn login` first.")
    return config, config.get_headers(), project_id


def _gql_post(headers, query, variables):
    """POST to the GraphQL API and handle common errors."""
    payload = {"query": query, "variables": variables}
    resp = _verbose_post(GRAPHQL_URL, headers=headers, payload=payload)

    if resp.status_code == 401:
        _handle_401(resp)
    if resp.status_code >= 400:
        raise click.ClickException(f"API error ({resp.status_code}): {resp.text[:200]}")

    data = resp.json().get("data", {})
    errors = resp.json().get("errors")
    if errors:
        raise click.ClickException(
            f"GraphQL error: {errors[0].get('message', 'Unknown error')}"
        )
    return data


def _fetch_connectors(headers, project_id, query=""):
    """Fetch Connect Kit connectors and return a list of node dicts."""
    inner_query = json.dumps({
        "input": {
            "limit": 50,
            "offset": 0,
            "sort": "desc",
            "query": query,
            "filter": {},
        }
    })
    variables = {
        "input": {
            "projectId": project_id,
            "first": 50,
            "after": None,
            "query": inner_query,
        }
    }
    data = _gql_post(headers, GET_KIT_CONNECTORS_QUERY, variables)
    connectors = data.get("widgetConnectors") or {}
    edges = connectors.get("edges") or []
    return [e["node"] for e in edges if "node" in e]


# ---------------------------------------------------------------------------
# fastn kit group
# ---------------------------------------------------------------------------

@cli.group(
    cls=OrderedGroup,
    command_order=["ls", "get", "config"],
)
@click.pass_context
def kit(ctx):
    """Manage the Connect Kit - connectors, AI agent chat, and configurations.

    \b
    Usage:
      fastn kit ls                         List Connect Kit connectors
      fastn kit get <name>                 Get connector details
      fastn kit config                     Show Connect Kit configuration
      fastn kit config -d '{"key": "val"}' Update Connect Kit configuration
    """
    pass


# ---------------------------------------------------------------------------
# fastn kit ls
# ---------------------------------------------------------------------------

@kit.command(name="ls")
@click.option("--query", "-q", default="", help="Search query to filter connectors")
def kit_ls(query):
    """List Connect Kit connectors in the current project.

    \b
    Examples:
      fastn kit ls
      fastn kit ls -q slack
    """
    _config, headers, project_id = _require_auth()
    items = _fetch_connectors(headers, project_id, query)

    if not items:
        click.echo("No Connect Kit connectors found.")
        return

    click.echo()
    click.echo(f"  {'Name':<25} {'ID'}")
    click.echo(f"  {'─' * 25} {'─' * 50}")
    for w in items:
        name = (w.get("name") or "")[:25]
        wid = w.get("id", "")
        click.echo(f"  {name:<25} {wid}")
    click.echo()
    click.echo(f"  {len(items)} connector(s) found.")


# ---------------------------------------------------------------------------
# fastn kit get <name>
# ---------------------------------------------------------------------------

@kit.command(name="get")
@click.argument("name")
def kit_get(name):
    """Get full details for a Connect Kit connector by name.

    Looks up the connector by name from the Connect Kit connectors list,
    then fetches the full connector details including actions, events,
    connected connectors, and more.

    \b
    Examples:
      fastn kit get slack
      fastn kit get hubspot
    """
    _config, headers, project_id = _require_auth()

    # Look up connector by name
    items = _fetch_connectors(headers, project_id)
    match = None
    for w in items:
        if (w.get("name") or "").lower() == name.lower():
            match = w
            break

    if not match:
        raise click.ClickException(
            f"Connector '{name}' not found. "
            "Run `fastn kit ls` to see available connectors."
        )

    # Fetch full connector details
    connector_id = match["id"]
    variables = {
        "input": {
            "projectId": project_id,
            "id": connector_id,
            "template": False,
        }
    }

    data = _gql_post(headers, GET_CONNECTOR_QUERY, variables)
    connector = data.get("connector")

    if not connector:
        raise click.ClickException(
            f"Could not fetch details for connector '{name}' (id: {connector_id})."
        )

    click.echo()
    click.echo(json.dumps(connector, indent=2))


# ---------------------------------------------------------------------------
# fastn kit config
# ---------------------------------------------------------------------------

@kit.command(name="config")
@click.option("--data", "-d", "settings_json", default=None,
              help='Connect Kit settings as JSON string to update (e.g. \'{"showFilterBar": true}\')')
def kit_config(settings_json):
    """Show or update Connect Kit configuration for the current project.

    Without --data/-d, displays the current Connect Kit configuration
    including authentication settings, filter options, RBAC, styles,
    and advanced settings.

    With --data/-d, updates the Connect Kit configuration. Fields not included
    in the JSON are left unchanged.

    \b
    Supported update fields:
      authenticationApi, isCustomAuthenticationEnabled, showFilterBar,
      showLabels, styles, labelsLayout, disableFor, filterWidgets,
      isRBACEnabled, advancedSettings

    \b
    Examples:
      fastn kit config
      fastn kit config -d '{"showFilterBar": true, "showLabels": false}'
      fastn kit config -d '{"isRBACEnabled": true}'
    """
    _config, headers, project_id = _require_auth()

    if settings_json is not None:
        # --- Update mode ---
        try:
            settings = json.loads(settings_json)
        except json.JSONDecodeError as e:
            raise click.ClickException(f"Invalid JSON for --data: {e}")

        if not isinstance(settings, dict):
            raise click.ClickException("--data must be a JSON object")

        variables = {
            "input": {
                "projectId": project_id,
                **settings,
            }
        }

        data = _gql_post(headers, SAVE_KIT_METADATA_MUTATION, variables)
        result = data.get("saveWidgetMetadata", data)

        click.echo()
        click.echo("  \u2713 Connect Kit configuration updated successfully.")
        if result and isinstance(result, dict):
            click.echo()
            click.echo(json.dumps(result, indent=2))
    else:
        # --- Show mode ---
        variables = {
            "input": {
                "id": project_id,
                "clientId": project_id,
            }
        }

        data = _gql_post(headers, GET_KIT_METADATA_QUERY, variables)
        metadata = data.get("widgetMetadata")

        if not metadata:
            click.echo("No Connect Kit configuration found for this project.")
            return

        click.echo()
        click.echo(json.dumps(metadata, indent=2))
