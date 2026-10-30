"""CLI command: fastn skill - list skills agents can load."""

from __future__ import annotations

import click

from fastn.cli import cli, GRAPHQL_URL
from fastn.cli._helpers import _ensure_fresh_token, _handle_401, _verbose_post
from fastn.config import load_config
from fastn._constants import LIST_SKILLS_QUERY


@cli.command()
def skill():
    """List skills in this project - tools and knowledge that agents load to handle tasks."""
    config = load_config()
    if not config.auth_token and not config.api_key:
        raise click.ClickException("Not authenticated. Run `fastn login` first.")

    _ensure_fresh_token(config)

    project_id = config.resolve_project_id()
    if not project_id:
        raise click.ClickException("No project configured. Run `fastn login` first.")

    headers = config.get_headers()
    variables = {"input": {"projectId": project_id}}
    payload = {"query": LIST_SKILLS_QUERY, "variables": variables}

    resp = _verbose_post(GRAPHQL_URL, headers=headers, payload=payload)

    if resp.status_code == 401:
        _handle_401(resp)
    if resp.status_code >= 400:
        raise click.ClickException(f"API error ({resp.status_code}): {resp.text[:200]}")

    data = resp.json().get("data", {})
    errors = resp.json().get("errors")
    if errors:
        raise click.ClickException(f"GraphQL error: {errors[0].get('message', 'Unknown error')}")

    items = data.get("listUCLAgents") or []

    if not items:
        click.echo("No skills found in this project.")
        return

    # Print table
    click.echo()
    click.echo(f"  {'Name':<30} {'Description':<50} {'ID'}")
    click.echo(f"  {'─' * 30} {'─' * 50} {'─' * 36}")
    for s in items:
        name = (s.get("name") or "")[:30]
        desc = (s.get("description") or "")[:50]
        sid = s.get("id", "")
        click.echo(f"  {name:<30} {desc:<50} {sid}")
    click.echo()
    click.echo(f"  {len(items)} skill(s) found.")
