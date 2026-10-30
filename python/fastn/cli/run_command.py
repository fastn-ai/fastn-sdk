from __future__ import annotations

import json
from typing import Optional

import click

from fastn import __version__
from fastn.cli import cli, connector, EXECUTE_URL, SOURCE_COMMUNITY
from fastn.cli._helpers import (
    _ensure_fresh_token,
    _extract_input_fields,
    _handle_execute_error,
    _parse_extra_args,
    _prompt_for_params,
    _to_snake_case,
    _verbose_post,
)
from fastn.cli._registry import _fetch_tool_actions, _parse_tool_node
from fastn.config import find_fastn_dir, load_config, load_manifest, load_registry, save_registry


@connector.command(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    ),
)
@click.argument("connector_name")
@click.argument("tool_name", required=False, default=None)
@click.argument("tenant_id", required=False, default=None)
@click.option("--connection-id", default=None, help="Connection ID for multi-connection connectors")
@click.option("--tenant", default=None, help="Tenant ID (overrides config)")
@click.pass_context
def run(ctx: click.Context, connector_name: str, tool_name: Optional[str], tenant_id: Optional[str], connection_id: Optional[str], tenant: Optional[str]) -> None:
    """Execute a connector tool directly from the command line.

    \b
    Usage:
      fastn connector run <connector>                              Show available tools
      fastn connector run <connector> <tool> [--key value]          Execute with inline params
      fastn connector run <connector> <tool> <tenant_id>            Execute for a specific tenant
      fastn connector run <connector> <tool>                        Execute with interactive prompts

    \b
    Examples:
      fastn connector run slack                                Show available Slack tools
      fastn connector run slack send_message --channel general --text "Hello!"
      fastn connector run slack send_message 3ab9d640-...      Execute as specific tenant
      fastn connector run slack send_message             Prompts for each field
    """
    config = load_config()
    if not config.auth_token and not config.api_key:
        raise click.ClickException("Not authenticated. Run `fastn login` first.")

    fastn_dir = find_fastn_dir()
    registry = load_registry(fastn_dir)
    connectors = registry.get("connectors", {})

    if not connectors:
        raise click.ClickException(
            "Registry is empty. Run `fastn connector sync` first."
        )

    if connector_name not in connectors:
        raise click.ClickException(
            f"Connector '{connector_name}' not found. Run `fastn connector ls` to see available connectors."
        )

    connector_data = connectors[connector_name]
    connector_id = connector_data.get("id", "")

    if not connector_id:
        raise click.ClickException(
            f"No ID for '{connector_name}'. Run `fastn connector sync`."
        )

    # Ensure tools are loaded
    tools = connector_data.get("tools", {})
    if not tools:
        source = connector_data.get("source", SOURCE_COMMUNITY)
        click.echo(f"Fetching tools for {connector_name}...")
        tool_nodes = _fetch_tool_actions(config, connector_id, source)
        tools = {}
        for node in tool_nodes:
            parsed = _parse_tool_node(node)
            tools[parsed["key"]] = parsed["data"]

        connector_data["tools"] = tools
        connector_data["tool_count"] = len(tools)
        save_registry(registry, fastn_dir)

    # If no tool given, list available tools
    if not tool_name:
        display_name = connector_data.get("display_name", connector_name)
        click.echo()
        click.echo(f"  {display_name} \u2014 available tools:")
        click.echo()
        for key in sorted(tools.keys()):
            tdata = tools[key]
            display_key = _to_snake_case(key)
            desc = tdata.get("description", "")
            if desc:
                click.echo(f"    {display_key:<30} {desc}")
            else:
                click.echo(f"    {display_key}")
        click.echo()
        click.echo(f"  Run: fastn connector run {connector_name} <tool> [--key value ...]")
        click.echo()
        return

    # Resolve the tool
    tool_info = tools.get(tool_name)
    # Fallback: try without underscores (send_message -> sendmessage)
    if tool_info is None and "_" in tool_name:
        tool_info = tools.get(tool_name.replace("_", ""))
    if tool_info is None:
        available = ", ".join(
            _to_snake_case(k) for k in sorted(tools.keys())
        )
        raise click.ClickException(
            f"Tool '{tool_name}' not found in '{connector_name}'. "
            f"Available: {available}"
        )

    tool_id = tool_info.get("toolId", "") or tool_info.get("actionId", "")
    if not tool_id:
        raise click.ClickException(
            f"No toolId for '{tool_name}'. Run `fastn connector sync` and `fastn connector add {connector_name}`."
        )

    # Extract input fields from schema for interactive prompting
    input_schema = tool_info.get("inputSchema", {})
    _pk, fields, required_fields = _extract_input_fields(input_schema)

    # Parse extra --key value args into params
    params = _parse_extra_args(ctx.args)

    # If no args were passed and there are fields, prompt interactively
    # (skip prompting when all fields are optional - just run with defaults)
    if not params and fields:
        desc = tool_info.get("description", "")
        click.echo()
        click.echo(f"  {connector_name}.{tool_name}")
        if desc:
            click.echo(f"  {desc}")
        if required_fields:
            params = _prompt_for_params(fields, required_fields)
        else:
            click.echo("  (all fields optional - running with defaults)")
            params = {}

    # Build execute payload - dynamically route params based on the schema
    from fastn.client import _build_params_from_schema

    workspace_id = config.resolve_project_id()
    parameters = _build_params_from_schema(tool_info, params)
    payload: dict = {
        "input": {
            "toolId": tool_id,
            "parameters": parameters,
            "agentId": workspace_id,
        }
    }
    if connector_id:
        payload["input"]["connectorId"] = connector_id
    if connection_id:
        payload["input"]["connectionId"] = connection_id

    effective_tenant = tenant_id or tenant
    if effective_tenant:
        config.tenant_id = effective_tenant

    # Refresh token right before the call (not earlier - interactive
    # prompting above can take long enough for the token to expire).
    _ensure_fresh_token(config)
    headers = config.get_headers()

    click.echo()
    click.echo(f"Running {connector_name}.{tool_name}...")
    resp = _verbose_post(EXECUTE_URL, headers, payload)

    _handle_execute_error(resp, f"{connector_name}.{tool_name}", workspace_id, config=config)

    data = resp.json()
    # Unwrap: API returns {body, statusCode, rawBody} - show the body
    if isinstance(data, dict) and "body" in data:
        result = data["body"]
    else:
        result = data

    click.echo(json.dumps(result, indent=2))


@connector.command()
@click.argument("connector_name")
@click.argument("tool_name", required=False, default=None)
def schema(connector_name: str, tool_name: Optional[str]) -> None:
    """Show raw JSON schema for a connector's tools.

    \b
    Usage:
      fastn connector schema slack                  Show schemas for all Slack tools
      fastn connector schema slack send_message     Show schema for a specific tool
    """
    fastn_dir = find_fastn_dir()
    registry = load_registry(fastn_dir)
    connectors = registry.get("connectors", {})

    if connector_name not in connectors:
        raise click.ClickException(
            f"Connector '{connector_name}' not found. Run `fastn connector add {connector_name}` first."
        )

    connector_data = connectors[connector_name]
    tools = connector_data.get("tools", {})

    if not tools:
        raise click.ClickException(
            f"No tools cached for '{connector_name}'. Run `fastn connector add {connector_name}` first."
        )

    if tool_name:
        tool = tools.get(tool_name)
        # Fallback: try without underscores (send_message -> sendmessage)
        if tool is None and "_" in tool_name:
            tool = tools.get(tool_name.replace("_", ""))
        if tool is None:
            available = ", ".join(
                _to_snake_case(k) for k in sorted(tools.keys())
            )
            raise click.ClickException(
                f"Tool '{tool_name}' not found in {connector_name}. Available: {available}"
            )
        output = {
            "name": tool_name,
            "description": tool.get("description", ""),
            "toolId": tool.get("toolId", "") or tool.get("actionId", ""),
            "inputSchema": tool.get("inputSchema", {}),
            "outputSchema": tool.get("outputSchema", {}),
        }
        click.echo(json.dumps(output, indent=2))
    else:
        output = []
        for name, tool in sorted(tools.items()):
            output.append({
                "name": _to_snake_case(name),
                "description": tool.get("description", ""),
                "toolId": tool.get("toolId", "") or tool.get("actionId", ""),
                "inputSchema": tool.get("inputSchema", {}),
                "outputSchema": tool.get("outputSchema", {}),
            })
        click.echo(json.dumps(output, indent=2))


@cli.command()
def version() -> None:
    """Show SDK and registry version."""
    fastn_dir = find_fastn_dir()
    manifest = load_manifest(fastn_dir)

    click.echo(f"Fastn SDK v{__version__}")
    reg_version = manifest.get("registry_version", "not synced")
    click.echo(f"Registry version: {reg_version}")
    last_synced = manifest.get("last_synced", "never")
    click.echo(f"Last synced: {last_synced}")
