"""Authentication commands - login, logout, whoami."""

from __future__ import annotations

from typing import Optional

import click
import httpx

from fastn.config import (
    FastnConfig,
    ensure_gitignore,
    load_config,
    save_config,
)

from fastn.cli import cli
from fastn.cli._helpers import _ensure_fresh_token
from fastn.cli._registry import _select_workspace


def _run_device_login() -> Optional[FastnConfig]:
    """Run the Keycloak device authorization flow.

    Returns a partial FastnConfig with auth tokens set, or None if login fails.
    """
    import webbrowser

    from fastn.oauth import (
        compute_token_expiry,
        poll_for_token,
        request_device_code,
    )

    try:
        with httpx.Client(timeout=30.0) as client:
            device = request_device_code(client)

            click.echo()
            click.echo(f"  Visit: {device.verification_uri}")
            click.echo(f"  Enter code: {device.user_code}")
            click.echo()

            # Try to auto-open browser
            try:
                webbrowser.open(device.verification_uri_complete)
                click.echo("  (Browser opened automatically)")
            except Exception:
                click.echo("  Open the URL above in your browser.")

            click.echo()
            click.echo("  Waiting for authorization", nl=False)

            tokens = poll_for_token(
                device.device_code,
                interval=device.interval,
                expires_in=device.expires_in,
                client=client,
            )

            click.echo()
            click.echo("  \u2713 Login successful!")

            return FastnConfig(
                auth_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                token_expiry=compute_token_expiry(tokens.expires_in),
            )
    except Exception as e:
        click.echo()
        click.echo(f"  \u2717 Login failed: {e}")
        click.echo()
        click.echo("  If this persists, set FASTN_API_KEY env var instead.")
        return None


@cli.command()
def login() -> None:
    """Authenticate with Fastn and select a project."""
    click.echo()
    click.echo("  Fastn Login")

    result = _run_device_login()
    if result is None:
        raise SystemExit(1)

    # Merge with existing config (preserve space_id, etc.)
    existing = load_config()
    existing.auth_token = result.auth_token
    existing.refresh_token = result.refresh_token
    existing.token_expiry = result.token_expiry

    filepath = save_config(existing)
    ensure_gitignore()

    click.echo(f"  \u2713 Tokens saved to {filepath}")

    # Prompt user to select a project
    workspace_id = _select_workspace(existing)
    if workspace_id:
        existing.project_id = workspace_id
        save_config(existing)
        click.echo(f"  \u2713 Project set: {workspace_id}")

    click.echo()


@cli.command()
def logout() -> None:
    """Log out and clear saved credentials."""
    config = load_config()
    config.auth_token = ""
    config.refresh_token = ""
    config.token_expiry = ""

    filepath = save_config(config)
    click.echo("  \u2713 Logged out successfully.")
    click.echo(f"  Tokens cleared from {filepath}")


@cli.command()
def whoami() -> None:
    """Show the current logged-in user."""
    config = load_config()

    if not config.auth_token:
        click.echo("  Not logged in. Run `fastn login` to authenticate.")
        return

    _ensure_fresh_token(config)

    from fastn.oauth import fetch_userinfo

    try:
        user_info = fetch_userinfo(config.auth_token)
        click.echo()
        name = user_info.get("name", user_info.get("preferred_username", "Unknown"))
        email = user_info.get("email", "")
        sub = user_info.get("sub", "")
        click.echo(f"  Logged in as: {name}")
        if email:
            click.echo(f"  Email: {email}")
        if sub:
            click.echo(f"  User ID: {sub}")
        click.echo()
    except Exception as e:
        click.echo(f"  Failed to fetch user info: {e}")
        click.echo("  Try running `fastn login` to re-authenticate.")


