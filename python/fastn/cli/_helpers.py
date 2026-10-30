"""Shared helper utilities for the fastn CLI commands."""

from __future__ import annotations

import json
from typing import Any

import click
import httpx

from fastn._http import _redact_headers


def _to_snake_case(name: str) -> str:
    """Convert a camelCase or PascalCase name to snake_case.

    Examples:
        sendMessage   -> send_message
        SendMessage   -> send_message
        getUsers      -> get_users
        getUserByEmail -> get_user_by_email
        testauth      -> testauth  (no-op for already lowercase)
    """
    import re
    # Insert underscore before uppercase letters that follow a lowercase letter or digit
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Insert underscore before uppercase letters followed by lowercase (for runs of caps)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    # Replace spaces and hyphens with underscores
    s = s.replace(" ", "_").replace("-", "_")
    return s.lower()


def _extract_org_id(config):
    """Extract the organization ID from the JWT token.

    Looks for a role like ``ORG#<orgId>#admin`` in ``realm_access.roles``.

    Returns:
        The org ID string, or empty string if not found.
    """
    if not config.auth_token:
        return ""
    try:
        from fastn.oauth import _decode_jwt_payload

        payload = _decode_jwt_payload(config.auth_token)
        roles = payload.get("realm_access", {}).get("roles", [])
        for role in roles:
            if role.startswith("ORG#"):
                parts = role.split("#")
                if len(parts) >= 3 and parts[2].lower() == "admin":
                    return parts[1]
    except Exception:
        pass
    return ""


def _handle_401(resp: httpx.Response, config=None, connector_label: str = "") -> None:
    """Raise a clear error for 401 responses.

    If the user's Fastn token is still valid locally, the 401 is most likely
    a *connector*-level auth failure (the downstream connector's OAuth token
    has expired or been revoked).  In that case we suggest reconnecting the
    connector rather than re-logging in.

    When we can't determine token status, we suggest ``fastn login``.
    """
    # Try to figure out whether the user's token is actually expired.
    token_expired = True  # pessimistic default
    if config is not None:
        try:
            from fastn.oauth import is_token_expired
            token_expired = is_token_expired(config.token_expiry)
        except Exception:
            pass

    # Extract the API's own error detail regardless of expiry path.
    detail = ""
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = body.get("message", "") or body.get("error", "") or ""
    except (ValueError, RuntimeError):
        pass

    if not token_expired:
        # User's Fastn token is still valid → the 401 is likely a
        # connector-level auth failure (e.g. Slack OAuth token expired).
        hint = f" for '{connector_label}'" if connector_label else ""
        workspace_id = ""
        if config is not None:
            try:
                workspace_id = config.resolve_project_id()
            except Exception:
                pass
        app_url = _workspace_url(workspace_id)
        raise click.ClickException(
            f"Connector authentication failed{hint}: {detail or 'token invalid'}.\n"
            f"  Your Fastn login is valid - this means the connector's OAuth token\n"
            f"  has expired or been revoked.\n"
            f"  Reconnect it at: {app_url}\n"
            f"  Then retry: fastn connector run ..."
        )

    # Token appears expired or we can't tell - assume platform auth issue.
    raise click.ClickException(
        detail or "Authentication failed. Run `fastn login` to re-authenticate."
    )


def _ensure_fresh_token(config) -> None:
    """Auto-refresh the access token if it has expired.

    Mutates *config* in place and persists the new tokens to disk.
    """
    from fastn.oauth import is_token_expired

    if not config.refresh_token or not is_token_expired(config.token_expiry):
        return

    from fastn.oauth import compute_token_expiry, refresh_access_token
    from fastn.config import save_config

    try:
        tokens = refresh_access_token(config.refresh_token)
        config.auth_token = tokens.access_token
        config.refresh_token = tokens.refresh_token
        config.token_expiry = compute_token_expiry(tokens.expires_in)
        save_config(config)
    except Exception:
        raise click.ClickException(
            "Session expired. Run `fastn login` to re-authenticate."
        )


def _is_verbose() -> bool:
    """Check if verbose mode is enabled via the CLI context."""
    ctx = click.get_current_context(silent=True)
    if ctx and ctx.obj:
        return ctx.obj.get("verbose", False)
    return False


def _build_curl(url: str, headers: dict, payload: dict) -> str:
    """Build a copy-pasteable curl command from a request."""
    parts = [f"curl -X POST '{url}'"]
    for k, v in headers.items():
        parts.append(f"  -H '{k}: {v}'")
    parts.append(f"  -d '{json.dumps(payload)}'")
    return " \\\n".join(parts)


def _verbose_post(url: str, headers: dict, payload: dict, timeout: float = 30.0) -> httpx.Response:
    """Make a POST request with verbose logging when -v is enabled."""
    verbose = _is_verbose()

    if verbose:
        click.echo()
        click.echo(f"  [API] POST {url}")
        click.echo(f"  [API] Headers: {json.dumps(_redact_headers(headers), indent=2)}")
        click.echo(f"  [API] Payload: {json.dumps(payload, indent=2)}")
        click.echo()
        click.echo("  [curl]")
        click.echo(f"  {_build_curl(url, headers, payload)}")
        click.echo()

    resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)

    if verbose:
        click.echo(f"  [API] Response {resp.status_code}: {resp.text[:500]}")
        if len(resp.text) > 500:
            click.echo(f"  [API] ... ({len(resp.text)} bytes total)")
        click.echo()

    return resp


FASTN_APP_BASE = "https://app.ucl.dev"


def _workspace_url(workspace_id: str) -> str:
    """Build the Fastn UI URL for a workspace's connector management page."""
    if workspace_id:
        return f"{FASTN_APP_BASE}/projects/{workspace_id}/ucl/{workspace_id}"
    return FASTN_APP_BASE


def _handle_execute_error(resp: httpx.Response, connector_label: str = "",
                          workspace_id: str = "", config=None) -> None:
    """Check for execution errors and raise with helpful messages.

    Detects common error patterns from the executeTool API and provides
    actionable guidance, especially for connectors that aren't enabled yet.
    """
    if resp.status_code == 401:
        _handle_401(resp, config, connector_label=connector_label)

    if resp.status_code >= 400:
        # Try to parse the error body for specific error types
        error_body = None
        try:
            error_body = resp.json()
        except Exception:
            pass

        error_msg = ""
        if isinstance(error_body, dict):
            error_msg = (
                error_body.get("message", "")
                or error_body.get("error", "")
                or error_body.get("body", {}).get("message", "")
                if isinstance(error_body.get("body"), dict) else ""
            )

        err_lower = (error_msg or resp.text).lower()

        # Detect "connector not enabled" / "connector not connected" errors
        not_enabled_keywords = [
            "not enabled", "not connected", "not configured",
            "not authorized", "no connection", "connection not found",
            "connector not found", "tool not found",
            "not active", "disabled",
        ]
        if any(kw in err_lower for kw in not_enabled_keywords):
            hint = f" '{connector_label}'" if connector_label else ""
            app_url = _workspace_url(workspace_id)
            raise click.ClickException(
                f"Connector{hint} is not enabled in your project.\n"
                f"  Enable it at: {app_url}\n"
                f"  Then run `fastn connector sync` to refresh your local registry."
            )

        raise click.ClickException(
            f"API error {resp.status_code}: {resp.text}"
        )


def _parse_extra_args(args: list) -> dict:
    """Parse remaining CLI args like --key value into a dict.

    Supports:
        --channel general           -> {"channel": "general"}
        --count 5                   -> {"count": 5}
        --verbose true              -> {"verbose": true}
        --tags '["a","b"]'          -> {"tags": ["a", "b"]}
        --flag                      -> {"flag": true}  (no value -> boolean true)
    """
    params: dict = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            key = arg[2:].replace("-", "_")
            # Check if next arg exists and is not another flag
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                raw = args[i + 1]
                # Auto-detect JSON types
                try:
                    value = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    value = raw
                params[key] = value
                i += 2
            else:
                # Flag with no value -> true
                params[key] = True
                i += 1
        else:
            i += 1
    return params


def _coerce_value(raw: str) -> Any:
    """Convert a raw string input to the appropriate Python type."""
    if not raw:
        return raw
    # Try JSON first (handles numbers, booleans, arrays, objects)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    return raw


# Header fields that are managed by the SDK / API gateway -- never prompt the user
_INTERNAL_HEADER_FIELDS = {
    "authorization", "x-fastn-space-id", "x-fastn-space-tenantid",
    "x-fastn-space-connection-id", "x-fastn-api-key",
}


def _extract_input_fields(input_schema: dict) -> tuple:
    """Extract the actual user-facing input fields from a tool's inputSchema.

    Handles all schema patterns:
        Single wrapper   ``{body: {type: object, props: {channel, text}}}``
        Multi wrapper    ``{headers: {...}, body: {type: object, props: {input}}}``
        Flat schema      ``{offset: {type: int}, limit: {type: int}}``

    Internal groups like ``headers`` (containing auth fields managed by the SDK)
    are automatically skipped.  Nested object properties are recursively
    unwrapped so the user is prompted for the actual leaf fields.

    Returns (param_key, fields, required_fields) where:
        param_key: the wrapper key name (e.g. "body") or None for flat schemas
        fields: dict of field_name -> {type, description, ...}
        required_fields: set of required field names
    """
    props = input_schema.get("properties", {})
    if not props:
        return None, {}, set()

    # Classify top-level properties into object groups and flat fields
    object_groups: dict = {}  # group_key -> property data
    flat_fields: dict = {}

    for key, pdata in props.items():
        if isinstance(pdata, dict) and pdata.get("type") == "object":
            object_groups[key] = pdata
        else:
            flat_fields[key] = pdata

    # If there are no object groups, everything is flat
    if not object_groups:
        required = set(input_schema.get("required", []))
        return None, flat_fields, required

    # Filter out internal groups (headers with SDK-managed auth fields)
    user_groups: dict = {}
    for key, pdata in object_groups.items():
        inner_props = pdata.get("properties", {})
        # Skip if ALL inner fields are internal header fields
        if inner_props and all(f in _INTERNAL_HEADER_FIELDS for f in inner_props):
            continue
        user_groups[key] = pdata

    # Single user-facing wrapper -> unwrap it
    if len(user_groups) == 1 and not flat_fields:
        key = next(iter(user_groups))
        wrapper = user_groups[key]
        inner_props = wrapper.get("properties", {})
        required = set(wrapper.get("required", []))
        # Recursively unwrap inner object fields that have their own properties
        unwrapped, req = _unwrap_nested_fields(inner_props, required)
        return key, unwrapped, req

    # Multiple user-facing groups or mix of groups + flat fields
    # Collect all inner fields across groups for prompting
    all_fields: dict = {}
    all_required: set = set()

    for key, pdata in user_groups.items():
        inner_props = pdata.get("properties", {})
        inner_required = set(pdata.get("required", []))
        unwrapped, req = _unwrap_nested_fields(inner_props, inner_required)
        all_fields.update(unwrapped)
        all_required.update(req)

    # Include flat fields too
    all_fields.update(flat_fields)
    flat_required = set(input_schema.get("required", []))
    for key in flat_fields:
        if key in flat_required:
            all_required.add(key)

    return None, all_fields, all_required


def _unwrap_nested_fields(
    props: dict, required: set,
) -> tuple:
    """Recursively unwrap nested object fields for interactive prompting.

    If a field is of type ``object`` and has inner properties, those inner
    properties are surfaced directly so the user gets prompted for the
    actual leaf fields instead of seeing ``[object]``.

    Returns (fields, required_fields).
    """
    result: dict = {}
    result_required: set = set()

    for name, fdata in props.items():
        if not isinstance(fdata, dict):
            result[name] = fdata
            if name in required:
                result_required.add(name)
            continue

        if fdata.get("type") == "object" and fdata.get("properties"):
            # Has nested fields -- recurse into them
            inner_props = fdata["properties"]
            inner_required = set(fdata.get("required", []))
            inner_result, inner_req = _unwrap_nested_fields(inner_props, inner_required)
            result.update(inner_result)
            # If the parent object is required, propagate inner requirements
            if name in required:
                result_required.update(inner_req)
            else:
                # Parent is optional -> all inner fields are optional
                pass
        else:
            # Leaf field (string, integer, etc.) or object without properties
            result[name] = fdata
            if name in required:
                result_required.add(name)

    return result, result_required


def _prompt_for_params(fields: dict, required_fields: set) -> dict:
    """Interactively prompt the user for each field in the schema.

    Required fields are prompted first, then optional fields.
    Empty input on optional fields is skipped.
    """
    params: dict = {}

    # Split into required and optional, preserving order
    required_list = [(k, v) for k, v in fields.items() if k in required_fields]
    optional_list = [(k, v) for k, v in fields.items() if k not in required_fields]

    if required_list:
        click.echo()
        for name, fdata in required_list:
            ftype = fdata.get("type", "string")
            desc = fdata.get("description", "")
            label = f"  {name}"
            if desc:
                label += f" ({desc})"
            label += f" [{ftype}]"

            while True:
                value = click.prompt(label)
                if value:
                    params[name] = _coerce_value(value)
                    break
                click.echo("    This field is required.")

    if optional_list:
        click.echo()
        click.echo("  Optional fields (press Enter to skip):")
        for name, fdata in optional_list:
            ftype = fdata.get("type", "string")
            desc = fdata.get("description", "")
            label = f"  {name}"
            if desc:
                label += f" ({desc})"
            label += f" [{ftype}]"

            value = click.prompt(label, default="", show_default=False)
            if value:
                params[name] = _coerce_value(value)

    return params


def _format_schema_properties(schema: dict, indent: int = 6) -> list:
    """Extract and format properties from an input or output schema.

    For inputSchema the real fields are typically nested under a wrapper
    key like ``body`` or ``param``.  This helper unwraps one level when
    the top-level schema has a single object property so the user sees
    the actual fields.

    Returns a list of formatted lines ready for ``click.echo``.
    """
    props = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    # Unwrap single wrapper key (e.g. "body" or "param")
    if len(props) == 1:
        wrapper_key = list(props.keys())[0]
        wrapper = props[wrapper_key]
        if isinstance(wrapper, dict) and wrapper.get("type") == "object":
            props = wrapper.get("properties", {})
            required_fields = set(wrapper.get("required", []))

    if not props:
        return []

    pad = " " * indent
    lines = []
    for name, pdata in props.items():
        ptype = pdata.get("type", "string")
        req = " (required)" if name in required_fields else ""
        desc = pdata.get("description", "")
        if desc:
            lines.append(f"{pad}{name}: {ptype}{req} - {desc}")
        else:
            lines.append(f"{pad}{name}: {ptype}{req}")
    return lines
