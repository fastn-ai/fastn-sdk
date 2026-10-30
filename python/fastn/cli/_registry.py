"""Registry and connector fetching/management functions.

Handles workspace discovery, connector enumeration, tool parsing,
schema migration, and stub generation/installation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import click

from fastn.config import (
    FastnConfig,
    get_installed_connectors,
    load_manifest,
    load_migrations,
    load_registry,
    save_manifest,
    save_migrations,
)

# Constants from the main CLI module
from fastn.cli import (
    COMMUNITY_CONNECTOR_ID,
    TOOL_ACTIONS_QUERY,
    GRAPHQL_URL,
    SEARCH_TOOLS_QUERY,
    SOURCE_COMMUNITY,
    SOURCE_ORG,
    SOURCE_WORKSPACE,
)
from fastn._constants import GET_ORGANIZATIONS_QUERY

# Helpers from the helpers module
from fastn.cli._helpers import (
    _extract_org_id,
    _to_snake_case,
    _verbose_post,
)

# Optional generator imports
_SDK_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(_SDK_ROOT))

try:
    from generator.generate import StubGenerator, parse_registry
    from generator.diff import (
        build_migrations,
        compute_schema_hash,
        diff_registries,
        merge_migrations,
    )
except ImportError:
    StubGenerator = None  # type: ignore[assignment,misc]
    parse_registry = None  # type: ignore[assignment]
    compute_schema_hash = None  # type: ignore[assignment]
    diff_registries = None  # type: ignore[assignment]
    build_migrations = None  # type: ignore[assignment]
    merge_migrations = None  # type: ignore[assignment]


def _fetch_workspaces(config: FastnConfig) -> list:
    """Fetch all workspaces/organizations for the current user.

    Calls the getOrganizations GraphQL query using the userId from the JWT.

    Args:
        config: FastnConfig with a valid auth_token.

    Returns:
        List of workspace dicts with 'id', 'name', 'packageType', etc.
    """
    from fastn.oauth import _decode_jwt_payload

    # Extract userId from JWT
    payload = _decode_jwt_payload(config.auth_token)
    user_id = payload.get("sub", "")
    if not user_id:
        raise click.ClickException("Could not extract user ID from token.")

    headers = config.get_headers()
    gql_payload = {
        "query": GET_ORGANIZATIONS_QUERY,
        "variables": {"userId": user_id},
    }
    resp = _verbose_post(GRAPHQL_URL, headers, gql_payload)
    if resp.status_code != 200:
        raise click.ClickException(
            f"Failed to fetch workspaces: {resp.status_code} {resp.text}"
        )

    data = resp.json() or {}
    if data.get("errors"):
        error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
        raise click.ClickException(f"Failed to fetch workspaces: {error_msg}")

    orgs = (data.get("data") or {}).get("getOrganizations") or []
    return orgs


def _select_workspace(config: FastnConfig) -> Optional[str]:
    """Fetch workspaces and let the user search & select one.

    Displays a numbered list of workspaces. The user can:
    - Enter a number to select directly
    - Type text to filter/search by name, then select from results

    Returns the selected workspace ID, or None if no workspaces found.
    """
    try:
        workspaces = _fetch_workspaces(config)
    except Exception as e:
        click.echo(f"  \u26a0 Could not fetch projects: {e}")
        return None

    if not workspaces:
        click.echo("  No projects found.")
        return None

    click.echo()
    click.echo("  Select a project:")
    click.echo()

    # Display numbered list
    for i, ws in enumerate(workspaces, 1):
        name = ws.get("name", "Unknown")
        ws_id = ws.get("id", "")
        pkg = ws.get("packageType", "")
        label = f"  {i}. {name}"
        if pkg:
            label += f" ({pkg})"
        click.echo(label)

    click.echo()

    while True:
        choice = click.prompt("  Enter number or search", type=str).strip()

        # If it's a number, select directly
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(workspaces):
                selected = workspaces[idx - 1]
                return selected["id"]
            click.echo(f"  Invalid number. Enter 1-{len(workspaces)}.")
            continue

        # Otherwise, treat as search text
        query = choice.lower()
        matches = [
            ws for ws in workspaces
            if query in ws.get("name", "").lower()
        ]

        if not matches:
            click.echo(f"  No projects matching '{choice}'.")
            continue

        if len(matches) == 1:
            selected = matches[0]
            click.echo(f"  \u2192 {selected['name']}")
            return selected["id"]

        # Multiple matches - show filtered list
        click.echo()
        for i, ws in enumerate(matches, 1):
            name = ws.get("name", "Unknown")
            pkg = ws.get("packageType", "")
            label = f"  {i}. {name}"
            if pkg:
                label += f" ({pkg})"
            click.echo(label)

        click.echo()
        sub_choice = click.prompt("  Enter number", type=str).strip()
        if sub_choice.isdigit():
            idx = int(sub_choice)
            if 1 <= idx <= len(matches):
                selected = matches[idx - 1]
                return selected["id"]
        click.echo("  Invalid selection.")


def _fetch_tools_by_scope(
    config: FastnConfig, scope_id: str, source: str, is_community: bool = False
) -> dict:
    """Fetch connectors for a specific scope (workspace, org, or community).

    Args:
        config: FastnConfig with valid auth credentials.
        scope_id: The clientId / connectorId to query (workspace ID, org ID, or "community").
        source: Label for the source category (SOURCE_WORKSPACE, SOURCE_ORG, SOURCE_COMMUNITY).
        is_community: Whether this is a community connector query.

    Returns:
        Dict of connector key -> connector data.
    """
    headers = config.get_headers()
    headers["x-fastn-space-id"] = scope_id

    payload = {
        "query": SEARCH_TOOLS_QUERY,
        "variables": {
            "input": {
                "clientId": scope_id,
                "first": 500,
                "connectorId": scope_id,
                "query": '{"input":{"limit":500,"offset":0,"sort":"asc","query":"","filter":{}}}',
                "isCommunity": is_community,
                "offset": 0,
            }
        },
    }
    resp = _verbose_post(GRAPHQL_URL, headers, payload)
    if resp.status_code != 200:
        # Non-fatal for workspace/org - just return empty
        if source != SOURCE_COMMUNITY:
            return {}
        raise click.ClickException(f"Failed to fetch registry: {resp.status_code} {resp.text}")

    data = resp.json() or {}

    if data.get("errors"):
        if source != SOURCE_COMMUNITY:
            return {}
        error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
        raise click.ClickException(f"Registry sync failed: {error_msg}")

    search_result = (data.get("data") or {}).get("searchDataSourceGroups") or {}
    edges = search_result.get("edges") or []

    connectors: dict = {}
    for edge in edges:
        node = edge.get("node", {})
        connector_id = node.get("id", "")
        name = node.get("name", "")
        connector_type = node.get("connectorType", "connector")
        key = name.lower().replace(" ", "_").replace("-", "_")

        # The workspace tools connector is returned as "my_connectors"
        # by the API - rename it to "my_tools" for display.
        if key == "my_connectors":
            key = "my_tools"
            name = "My Tools"

        connectors[key] = {
            "id": connector_id,
            "display_name": name,
            "category": "",
            "source": source,
            "connector_type": connector_type,
            "tools": {},
            "tool_count": 0,
        }

    return connectors


def _fetch_registry_list(config: FastnConfig) -> dict:
    """Fetch all connectors from the GraphQL API across all scopes.

    Fetches connectors from three sources:
        1. My Workspace - connectors in the user's selected workspace
        2. My Org - connectors in the user's organization
        3. Community - public community connectors
    """
    connectors: dict = {}

    # 1. Workspace connectors
    workspace_id = config.resolve_project_id()
    if workspace_id:
        ws_connectors = _fetch_tools_by_scope(
            config, workspace_id, SOURCE_WORKSPACE
        )
        connectors.update(ws_connectors)

    # 2. Organization connectors
    org_id = _extract_org_id(config)
    if org_id:
        org_connectors = _fetch_tools_by_scope(
            config, org_id, SOURCE_ORG
        )
        # Only add org connectors that aren't already in workspace
        for key, data in org_connectors.items():
            if key not in connectors:
                connectors[key] = data

    # 3. Community connectors
    community_connectors = _fetch_tools_by_scope(
        config, COMMUNITY_CONNECTOR_ID, SOURCE_COMMUNITY, is_community=True
    )
    # Only add community connectors that aren't already present
    for key, data in community_connectors.items():
        if key not in connectors:
            connectors[key] = data

    return {"version": "1.0.0", "connectors": connectors}


def _fetch_tool_actions(
    config: FastnConfig, connector_id: str, source: str = SOURCE_COMMUNITY,
) -> list:
    """Fetch all tools for a connector via callCoreProjectFlow."""
    headers = config.get_headers()
    workspace_id = config.resolve_project_id()

    # orgId depends on the connector's source scope:
    #   workspace -> workspace/space ID
    #   org       -> org ID from JWT
    #   community -> "community"
    if source == SOURCE_WORKSPACE:
        org_id = workspace_id
    elif source == SOURCE_ORG:
        org_id = _extract_org_id(config) or workspace_id
    else:
        org_id = COMMUNITY_CONNECTOR_ID

    payload = {
        "query": TOOL_ACTIONS_QUERY,
        "variables": {
            "input": {
                "operationName": "getConnectorRegisteredTools_v1",
                "input": {
                    "connectorId": connector_id,
                    "orgId": org_id,
                    "workspaceId": workspace_id,
                    "gatewayId": workspace_id,
                },
            }
        },
    }
    resp = _verbose_post(GRAPHQL_URL, headers, payload)
    if resp.status_code != 200:
        raise click.ClickException(
            f"Failed to fetch connector tools: {resp.status_code} {resp.text}"
        )

    data = resp.json()

    # Check for GraphQL errors
    if data.get("errors"):
        error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
        raise click.ClickException(f"GraphQL error: {error_msg}")

    result = data.get("data", {}).get("callCoreProjectFlow") or {}
    tools = result.get("data") or []
    return tools


def _parse_tool_node(node: dict) -> dict:
    """Parse a single tool node from callCoreProjectFlow into registry format."""
    tool_name = node.get("name", "")
    action_id = node.get("id", "")
    description = node.get("description", "")

    # Extract params from inputSchema (already a dict)
    params = {}
    input_schema = node.get("inputSchema") or {}
    if isinstance(input_schema, dict):
        props = input_schema.get("properties", {})
        required_fields = input_schema.get("required", [])
        for pname, pdata in props.items():
            params[pname] = {
                "type": pdata.get("type", "string"),
                "description": pdata.get("description", ""),
                "required": pname in required_fields,
            }

    key = _to_snake_case(tool_name)
    return {
        "key": key,
        "data": {
            "toolId": action_id,
            "name": tool_name,
            "description": description,
            "params": params,
            "inputSchema": node.get("inputSchema") or {},
            "outputSchema": node.get("outputSchema") or {},
        },
    }


def _check_and_migrate(
    fastn_dir: Path,
    old_registry: Dict,
    new_registry: Dict,
    connector_names: Optional[list] = None,
) -> bool:
    """Detect breaking changes, prompt user, and save migration records.

    When breaking changes are found:
        1. Shows the diff summary
        2. Asks the user to confirm
        3. If confirmed, generates migration records so old code keeps
           working at runtime with deprecation warnings
        4. Saves migrations to .fastn/migrations.json

    Returns True if stubs should be regenerated, False to skip.
    """
    if diff_registries is None:
        return True

    result = diff_registries(old_registry, new_registry, connector_names)
    if not result.changes:
        return True

    summary = result.summary()
    if summary:
        click.echo()
        click.echo(summary)

    if result.has_breaking_changes:
        click.echo()
        click.echo("  Your existing code will continue to work with deprecation warnings.")
        if not click.confirm("  Update stubs with these breaking changes?"):
            click.echo("  Stubs not updated. Your existing stubs are unchanged.")
            return False

        # Generate and save migration records for runtime backward compat
        if build_migrations is not None:
            new_migrations = build_migrations(result, old_registry)
            existing_migrations = load_migrations(fastn_dir)
            if existing_migrations and merge_migrations is not None:
                merged = merge_migrations(existing_migrations, new_migrations)
            else:
                merged = new_migrations
            save_migrations(merged, fastn_dir)
            click.echo("  \u2713 Migration records saved. Old code will still work.")

    return True


def _update_schema_hashes(fastn_dir: Path, registry: Dict, installed: list) -> None:
    """Store schema hashes in manifest for each installed connector."""
    if compute_schema_hash is None:
        return

    manifest = load_manifest(fastn_dir)
    installed_data = manifest.get("installed", {})
    for name in installed:
        if name in installed_data:
            installed_data[name]["schema_hash"] = compute_schema_hash(registry, name)
    save_manifest(manifest, fastn_dir)


def _regenerate_stubs(
    fastn_dir: Path,
    language: str = "python",
    old_registry: Optional[Dict] = None,
    _skip: Optional[bool] = None,
) -> bool:
    """Regenerate type stubs based on current registry.

    All connectors in the registry get individual stub files so users
    get autocomplete for every connector without needing ``fastn add``.
    Connectors whose tool schemas have been fetched (via ``fastn add``)
    get fully typed method signatures; others get a ``__getattr__`` fallback.

    If old_registry is provided, performs breaking change detection
    before regenerating. The user is prompted to confirm when breaking
    changes are found. Migration records are saved for runtime backward
    compatibility.

    Returns False if the user declined the update, True otherwise.
    """
    if StubGenerator is None:
        return True

    registry = load_registry(fastn_dir)
    installed = get_installed_connectors(fastn_dir)
    output_dir = fastn_dir / language
    output_dir.mkdir(parents=True, exist_ok=True)

    # Detect breaking changes before regenerating (only once, on first language)
    if _skip is None and old_registry is not None and language == "python":
        if not _check_and_migrate(fastn_dir, old_registry, registry, installed):
            return False

    if _skip:
        return False

    # Treat ALL connectors as "installed" so each gets its own stub file.
    # Connectors with fetched tool schemas get fully typed stubs;
    # those without get a __getattr__ fallback (from the connector template).
    all_connector_names = list(
        (parse_registry(registry) if parse_registry else {}).get("connectors", [])
    )
    if all_connector_names:
        # Use parsed (sanitized) names from the registry
        stub_installed = [c["name"] for c in all_connector_names]
    else:
        stub_installed = installed

    generator = StubGenerator(language=language)
    generator.generate_all(registry, stub_installed, str(output_dir))

    # Update schema hashes after successful generation
    if language == "python":
        _update_schema_hashes(fastn_dir, registry, installed)

    return True


def _detect_languages(fastn_dir: Path) -> List[str]:
    """Detect which SDK languages are installed in the current project.

    Only Python has connector stubs (the Node SDK, @fastn-ai/sdk, is the
    platform API client and has no connector proxy to type), so this returns
    ["python"] when the fastn package is importable and [] otherwise.

    Args:
        fastn_dir: Path to the .fastn directory.

    Returns:
        ["python"] or [].
    """
    languages: List[str] = []

    # Python: check if fastn package is importable
    try:
        import fastn as _fastn_check  # noqa: F401
        languages.append("python")
    except ImportError:
        pass

    return languages


def _resolve_friendly_names(
    action_id: str,
    raw_action_name: str,
    raw_tool_name: str,
    tool_hint: Optional[str],
    registry: dict,
) -> tuple:
    """Resolve friendly connector and tool names from the registry.

    The getTools API may return raw internal IDs (e.g.
    ``_knexa_2XfaKS...``) as tool/connector names.  This function looks
    up the local registry to find human-readable names.

    Returns (connector_name, tool_name, connector_id, tool_info).
    """
    connectors = registry.get("connectors", {})

    # If we already have a good tool name from the hint or response
    friendly_tool = raw_tool_name or tool_hint or ""
    friendly_action = raw_action_name
    resolved_tool_id = ""
    resolved_action_info: Optional[dict] = None

    # Search the registry by toolId to find the friendly names
    for cname, cdata in connectors.items():
        actions = cdata.get("tools", {})
        for tname, tinfo in actions.items():
            if (tinfo.get("toolId") or tinfo.get("actionId")) == action_id:
                friendly_tool = cname
                friendly_action = tname
                resolved_tool_id = cdata.get("id", "")
                resolved_action_info = tinfo
                return friendly_tool, friendly_action, resolved_tool_id, resolved_action_info

    # Fallback: if tool hint was given, look up its tool_id
    if tool_hint and tool_hint in connectors:
        resolved_tool_id = connectors[tool_hint].get("id", "")
        friendly_tool = tool_hint

    return friendly_tool, friendly_action, resolved_tool_id, resolved_action_info
