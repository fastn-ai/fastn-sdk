from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import click

from fastn.cli import (
    connector,
    API_BASE_URL,
    SOURCE_COMMUNITY,
    SOURCE_ORG,
    SOURCE_WORKSPACE,
)
from fastn.cli._helpers import (
    _ensure_fresh_token,
    _format_schema_properties,
    _to_snake_case,
    _verbose_post,
    _workspace_url,
)
from fastn.cli._registry import (
    _detect_languages,
    _extract_org_id,
    _fetch_tool_actions,
    _fetch_tools_by_scope,
    _fetch_registry_list,
    _parse_tool_node,
    _regenerate_stubs,
)
from fastn.config import (
    add_connector_to_manifest,
    find_fastn_dir,
    get_installed_connectors,
    load_config,
    load_manifest,
    load_registry,
    remove_connector_from_manifest,
    save_manifest,
    save_registry,
)


def _save_snapshot_and_generate_package_stubs(registry: dict) -> None:
    """Save registry snapshot and generate stubs into the SDK package tree.

    This writes stubs into ``python/fastn/`` so they ship in the published wheel.
    Only runs when executed from within the SDK repo (generator/ must exist).

    Compares against the existing snapshot to detect changes. Skips stub
    generation when nothing changed and highlights breaking changes.
    """
    from pathlib import Path as _Path

    sdk_root = _Path(__file__).resolve().parent.parent.parent.parent
    snapshot_path = sdk_root / "generator" / "registry_snapshot.json"
    package_dir = sdk_root / "python"

    if not snapshot_path.parent.exists():
        click.echo("  (Skipping package stub generation - not in SDK repo)")
        return

    try:
        from generator.generate import StubGenerator, _sanitize_identifier
    except ImportError:
        click.echo("  (Skipping package stub generation - generator not found)")
        return

    # Load existing snapshot for comparison
    old_registry: dict = {}
    if snapshot_path.exists():
        try:
            old_registry = json.loads(snapshot_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Diff old vs new across all connectors
    try:
        from generator.diff import diff_registries

        result = diff_registries(old_registry, registry)
    except ImportError:
        result = None

    if result is not None and not result.changes:
        click.echo("  Package stubs up to date - no changes detected.")
        return

    # Show what changed
    if result is not None and result.changes:
        summary = result.summary()
        if summary:
            click.echo()
            click.echo(summary)

        if result.has_breaking_changes:
            click.echo()
            click.echo(
                f"  \u26a0 {len(result.breaking_changes)} breaking change(s) "
                f"in package stubs!"
            )
        click.echo()

    # Save snapshot
    snapshot_path.write_text(json.dumps(registry, indent=2, sort_keys=True))
    click.echo(f"\u2713 Saved registry snapshot to {snapshot_path.relative_to(sdk_root)}")

    # Generate stubs into package dir
    all_names = [_sanitize_identifier(k) for k in registry.get("connectors", {}).keys()]
    generator = StubGenerator("python")
    files = generator.generate_all(registry, all_names, str(package_dir))

    # The shipped fastn/__init__.pyi also types the client API, which the
    # generator's index template does not: rebuild it from the connector stubs.
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, str(package_dir / "scripts" / "generate_client_stub.py")],
        check=True,
    )

    with_tools = sum(1 for c in registry.get("connectors", {}).values() if c.get("tools"))
    click.echo(f"\u2713 Generated {len(files)} package stubs ({with_tools} with typed methods)")


@connector.command()
@click.option("--force", is_flag=True, help="Re-fetch all tool schemas even if cached")
def sync(force: bool = False) -> None:
    """Sync all connectors, fetch tool schemas, and generate type stubs."""
    config = load_config()
    if not config.auth_token and not config.api_key:
        raise click.ClickException("Not authenticated. Run `fastn login` first.")

    _ensure_fresh_token(config)

    click.echo("Syncing connector registry...")

    fastn_dir = find_fastn_dir()
    fastn_dir.mkdir(parents=True, exist_ok=True)

    # Capture old registry for breaking change detection
    old_registry = load_registry(fastn_dir)

    registry = _fetch_registry_list(config)

    # Preserve cached tool schemas from the previous sync so we only
    # re-fetch connectors that are genuinely new or never had tools.
    if not force:
        old_connectors = old_registry.get("connectors", {})
        for name, cdata in registry.get("connectors", {}).items():
            if not cdata.get("tools") and name in old_connectors:
                cached = old_connectors[name]
                if cached.get("tools"):
                    cdata["tools"] = cached["tools"]
                    cdata["tool_count"] = cached.get("tool_count", len(cached["tools"]))

    save_registry(registry, fastn_dir)

    # Update manifest
    manifest = load_manifest(fastn_dir)
    manifest["registry_version"] = registry.get("version", "unknown")
    manifest["last_synced"] = datetime.now(timezone.utc).isoformat()
    save_manifest(manifest, fastn_dir)

    connector_count = len(registry.get("connectors", {}))
    click.echo(f"\u2713 Registry synced: {connector_count} connectors available.")

    # Fetch tool schemas only for connectors without cached tools
    reg_connectors = registry.get("connectors", {})
    to_fetch = [
        (name, cdata)
        for name, cdata in reg_connectors.items()
        if not cdata.get("tools") and cdata.get("id")
    ]
    skipped = len(reg_connectors) - len(to_fetch)

    if to_fetch:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        click.echo(f"Fetching tool schemas for {len(to_fetch)} connectors...")
        fetched = 0
        failed = 0

        def _fetch_one(name: str, cdata: dict) -> bool:
            source = cdata.get("source", SOURCE_COMMUNITY)
            try:
                tool_nodes = _fetch_tool_actions(config, cdata["id"], source)
                tools = {}
                for node in tool_nodes:
                    parsed = _parse_tool_node(node)
                    tools[parsed["key"]] = parsed["data"]
                cdata["tools"] = tools
                cdata["tool_count"] = len(tools)
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {
                pool.submit(_fetch_one, name, cdata): name
                for name, cdata in to_fetch
            }
            for future in as_completed(futures):
                if future.result():
                    fetched += 1
                else:
                    failed += 1
                done = fetched + failed
                if done % 50 == 0:
                    click.echo(f"  ... {done}/{len(to_fetch)} connectors")

        save_registry(registry, fastn_dir)
        click.echo(f"\u2713 Fetched tool schemas: {fetched} new, {skipped} cached, {failed} failed.")
    else:
        click.echo(f"\u2713 Tool schemas up to date ({skipped} cached).")

    # Save snapshot and generate package stubs
    _save_snapshot_and_generate_package_stubs(registry)

    # Regenerate stubs for ALL connectors (with breaking change detection)
    languages = _detect_languages(fastn_dir)
    updated = False
    for lang in languages:
        result = _regenerate_stubs(
            fastn_dir, lang, old_registry=old_registry,
            _skip=not updated if updated else None,
        )
        updated = updated or result
    if updated:
        click.echo(f"\u2713 Refreshed type stubs for {connector_count} connectors.")


@connector.command()
@click.argument("connector_names", nargs=-1, required=True)
def add(connector_names: tuple) -> None:
    """Fetch full tool schemas for specific connectors (enhances autocomplete)."""
    config = load_config()
    try:
        config.validate()
    except Exception as e:
        raise click.ClickException(str(e))

    _ensure_fresh_token(config)

    fastn_dir = find_fastn_dir()
    registry = load_registry(fastn_dir)

    # Capture old registry for breaking change detection
    old_registry = copy.deepcopy(registry)

    if not registry.get("connectors"):
        click.echo("Registry is empty. Running sync first...")
        registry = _fetch_registry_list(config)
        fastn_dir.mkdir(parents=True, exist_ok=True)
        save_registry(registry, fastn_dir)
        old_registry = {}  # No old data to compare against

    reg_connectors = registry.get("connectors", {})
    added_connectors: List[str] = []

    for connector_name in connector_names:
        click.echo(f"Adding {connector_name}...")

        if connector_name not in reg_connectors:
            click.echo(f"  \u2717 Connector '{connector_name}' not found in registry.")
            click.echo("    Run `fastn connector sync` to refresh, then try again.")
            continue

        connector_data = reg_connectors[connector_name]
        connector_id = connector_data.get("id", "")

        if not connector_id:
            click.echo(f"  \u2717 No ID for '{connector_name}'. Run `fastn connector sync`.")
            continue

        # Fetch tools for this connector
        source = connector_data.get("source", SOURCE_COMMUNITY)
        click.echo(f"  Fetching tools for {connector_name}...")
        tool_nodes = _fetch_tool_actions(config, connector_id, source)
        tools = {}
        for node in tool_nodes:
            parsed = _parse_tool_node(node)
            tools[parsed["key"]] = parsed["data"]

        connector_data["tools"] = tools
        connector_data["tool_count"] = len(tools)
        save_registry(registry, fastn_dir)

        version = registry.get("version", "unknown")
        add_connector_to_manifest(connector_name, version, fastn_dir)
        added_connectors.append(connector_name)
        click.echo(f"  \u2713 {connector_name} added ({len(tools)} tools).")

    # Regenerate stubs (with breaking change detection for re-added connectors)
    languages = _detect_languages(fastn_dir)
    updated = False
    for lang in languages:
        result = _regenerate_stubs(
            fastn_dir, lang, old_registry=old_registry,
            _skip=not updated if updated else None,
        )
        updated = updated or result
    if updated:
        click.echo("✓ Type stubs generated.")


@connector.command()
@click.argument("connector_name")
def remove(connector_name: str) -> None:
    """Remove connector stubs."""
    fastn_dir = find_fastn_dir()

    if remove_connector_from_manifest(connector_name, fastn_dir):
        # Remove stub files for detected languages only
        languages = _detect_languages(fastn_dir)
        for lang in languages:
            ext = "pyi" if lang == "python" else "d.ts"
            stub_file = fastn_dir / lang / "connectors" / f"{connector_name}.{ext}"
            if stub_file.exists():
                stub_file.unlink()

        for lang in languages:
            _regenerate_stubs(fastn_dir, lang)
        click.echo(f"\u2713 Removed {connector_name}.")
    else:
        click.echo(f"Connector '{connector_name}' is not installed.")


def _show_connector_detail(
    connector_name: str,
    connectors: dict,
    registry: dict,
    fastn_dir: Any,
    verbose: bool,
) -> None:
    """Show tools and details for a specific connector."""
    config = load_config()
    if not config.auth_token and not config.api_key:
        raise click.ClickException("Not authenticated. Run `fastn login` first.")

    _ensure_fresh_token(config)

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

    # Check if tools are already cached in registry
    cached_tools = connector_data.get("tools", {})
    if cached_tools:
        tool_list = cached_tools
    else:
        source = connector_data.get("source", SOURCE_COMMUNITY)
        click.echo(f"Fetching tools for {connector_name}...")
        tool_nodes = _fetch_tool_actions(config, connector_id, source)
        tool_list = {}
        for node in tool_nodes:
            parsed = _parse_tool_node(node)
            tool_list[parsed["key"]] = parsed["data"]

        # Cache in registry
        connector_data["tools"] = tool_list
        connector_data["tool_count"] = len(tool_list)
        save_registry(registry, fastn_dir)

    display_name = connector_data.get("display_name", connector_name)
    click.echo()
    click.echo(f"  {display_name} ({len(tool_list)} tools):")
    click.echo()

    for key, tool_entry in sorted(tool_list.items()):
        display_key = _to_snake_case(key) if key != _to_snake_case(key) else key
        usage = f"fastn.{connector_name}.{display_key}()"
        desc = tool_entry.get("description", "")
        if verbose:
            click.echo(f"  {display_key}")
            click.echo(f"    Usage: {usage}")
            if desc:
                click.echo(f"    {desc}")

            input_schema = tool_entry.get("inputSchema", {})
            input_lines = _format_schema_properties(input_schema)
            if input_lines:
                click.echo("    Input:")
                for line in input_lines:
                    click.echo(line)

            output_schema = tool_entry.get("outputSchema", {})
            output_lines = _format_schema_properties(output_schema)
            if output_lines:
                click.echo("    Output:")
                for line in output_lines:
                    click.echo(line)

            click.echo()
        else:
            if desc:
                click.echo(f"    {display_key:<30} {desc}")
            else:
                click.echo(f"    {display_key}")


def _show_active_connectors(
    connectors: dict,
    registry: dict,
    fastn_dir: Any,
    installed_names: set,
    verbose: bool,
) -> None:
    """Show only active/enabled connectors (project + org)."""
    config = load_config()
    if not config.auth_token and not config.api_key:
        raise click.ClickException("Not authenticated. Run `fastn login` first.")

    _ensure_fresh_token(config)

    headers = config.get_headers()
    workspace_id = config.resolve_project_id()

    # --- 1. Get all active/connected connectors via the UCL getTools API --
    active_payload: dict = {
        "input": {
            "agentId": workspace_id,
            "limit": 500,
        }
    }

    click.echo("Fetching active connectors...")
    resp = _verbose_post(f"{API_BASE_URL}/getTools", headers, active_payload)

    if resp.status_code >= 400:
        raise click.ClickException(
            f"Failed to fetch active connectors: {resp.status_code} {resp.text}"
        )

    data = resp.json()
    # Response is a plain array of tool objects
    tool_list = data if isinstance(data, list) else data.get("tools", data.get("data", []))
    if isinstance(tool_list, dict):
        tool_list = []

    # --- 2. Fetch selected connectors from the workspace -----------------
    # The UI's "Selected Connectors" page shows connectors that are added
    # to the workspace's UCL.  We approximate this by re-fetching workspace
    # and org-scoped connectors, which includes both native connectors
    # (flows, test) and community connectors that have been selected.
    selected_connectors: dict = {}
    try:
        ws_selected = _fetch_tools_by_scope(
            config, workspace_id, SOURCE_WORKSPACE
        )
        selected_connectors.update(ws_selected)
    except Exception:
        pass

    org_id = _extract_org_id(config)
    if org_id:
        try:
            org_selected = _fetch_tools_by_scope(
                config, org_id, SOURCE_ORG
            )
            for key, sdata in org_selected.items():
                if key not in selected_connectors:
                    selected_connectors[key] = sdata
        except Exception:
            pass

    if not tool_list and not selected_connectors:
        app_url = _workspace_url(workspace_id)
        click.echo(f"No active connectors. Enable connectors at: {app_url}")
        return

    # --- 3. Build toolId -> connector_name reverse lookup ---------------
    # The getTools API response doesn't include connector names -- tools
    # only have toolId, type, and function.{name, description, parameters}.
    action_to_connector: Dict[str, str] = {}
    for cname, cdata in connectors.items():
        for _tkey, tinfo in cdata.get("tools", {}).items():
            aid = tinfo.get("toolId", "") or tinfo.get("actionId", "")
            if aid:
                action_to_connector[aid] = cname

    # Collect the set of active toolIds that still need resolving
    active_action_ids = {
        (t.get("toolId", "") or t.get("actionId", "")) for t in tool_list if (t.get("toolId") or t.get("actionId"))
    }
    unresolved_ids = active_action_ids - set(action_to_connector.keys())

    # For connectors that haven't been `fastn connector add`-ed yet (tools dict is
    # empty), fetch their tool list so we can map toolIds.
    # Phase 1: workspace/org connectors (always fetched)
    # Phase 2: community connectors (only if unresolved IDs remain)
    unfetched_local = [
        (cname, cdata)
        for cname, cdata in connectors.items()
        if not cdata.get("tools")
        and cdata.get("id")
        and cdata.get("source") in (SOURCE_WORKSPACE, SOURCE_ORG)
    ]
    unfetched_community = [
        (cname, cdata)
        for cname, cdata in connectors.items()
        if not cdata.get("tools")
        and cdata.get("id")
        and cdata.get("source") == SOURCE_COMMUNITY
    ]

    registry_updated = False

    def _fetch_and_map(cname: str, cdata: dict) -> None:
        nonlocal registry_updated
        try:
            source = cdata.get("source", SOURCE_COMMUNITY)
            tool_nodes = _fetch_tool_actions(config, cdata["id"], source)
            tools_map: Dict[str, Any] = {}
            for node in tool_nodes:
                parsed = _parse_tool_node(node)
                aid = parsed["data"].get("toolId", "") or parsed["data"].get("actionId", "")
                if aid:
                    action_to_connector[aid] = cname
                tools_map[parsed["key"]] = parsed["data"]
            cdata["tools"] = tools_map
            cdata["tool_count"] = len(tools_map)
            registry_updated = True
        except Exception:
            pass  # Non-fatal -- will show as "other"

    if unfetched_local or unresolved_ids:
        click.echo("  Resolving connector details...")

    # Always resolve workspace/org connectors
    for cname, cdata in unfetched_local:
        _fetch_and_map(cname, cdata)
        unresolved_ids -= set(action_to_connector.keys())

    # Resolve community connectors only while unresolved IDs remain.
    # Stop early once all active tools are mapped.
    if unresolved_ids:
        for cname, cdata in unfetched_community:
            if not unresolved_ids:
                break
            _fetch_and_map(cname, cdata)
            unresolved_ids -= set(action_to_connector.keys())

    if registry_updated:
        save_registry(registry, fastn_dir)

    # --- 4. Group active tools by connector name ---------------------------
    by_connector: dict = {}
    for tool_entry in tool_list:
        action_id = tool_entry.get("toolId", "") or tool_entry.get("actionId", "")
        func = tool_entry.get("function", {})
        tname = func.get("name", "") or action_id
        desc = func.get("description", "")

        # Look up connector name from our reverse map
        cname = action_to_connector.get(action_id, "")

        # Fallback: try matching by function name against cached registry
        if not cname:
            for reg_cname, cdata in connectors.items():
                for _tkey, tinfo in cdata.get("tools", {}).items():
                    if tinfo.get("name") == tname or _tkey == _to_snake_case(tname):
                        cname = reg_cname
                        break
                if cname:
                    break

        if not cname:
            cname = "other"

        by_connector.setdefault(cname, []).append({
            "name": tname,
            "description": desc,
            "toolId": action_id,
        })

    # --- 5. Include selected connectors with 0 active tools -------------
    # Workspace/org connectors that appear in searchDataSourceGroups but
    # have no tools in the getTools response are "selected but not connected"
    for cname, sdata in selected_connectors.items():
        if cname not in by_connector:
            by_connector[cname] = []
            # Merge display info into connectors dict so display names work
            if cname not in connectors:
                connectors[cname] = sdata

    total_tools = len(tool_list)
    total_connectors = len(by_connector)
    click.echo()
    click.echo(f"  Active connectors ({total_tools} tools across {total_connectors} connectors):")

    for cname in sorted(by_connector.keys()):
        tools_in_group = by_connector[cname]
        display = connectors.get(cname, {}).get("display_name", cname)
        marker = "\u2705" if cname.lower() in installed_names else "  "
        count_label = f"{len(tools_in_group)} tools"
        if not tools_in_group:
            count_label = "0 tools \u2014 not connected"
        click.echo()
        click.echo(f"  {marker} {display} ({count_label})")
        if verbose and tools_in_group:
            for t in sorted(tools_in_group, key=lambda x: x["name"]):
                desc = t.get("description", "")
                tname = _to_snake_case(t["name"]) if t["name"] else t["toolId"]
                if desc:
                    click.echo(f"      {tname:<30} {desc}")
                else:
                    click.echo(f"      {tname}")

    click.echo()
    app_url = _workspace_url(workspace_id)
    click.echo(f"  {total_connectors} connectors active. Manage at: {app_url}")
    click.echo("  Run `fastn connector add <name>` to fetch full tool schemas.")
    click.echo()


def _show_installed_connectors(
    connectors: dict,
    installed_names: set,
) -> None:
    """Show only locally installed connectors."""
    if not installed_names:
        click.echo("No connectors installed. Run `fastn connector add <name>` to fetch tool schemas.")
        return

    items = [(k, v) for k, v in connectors.items() if k in installed_names]
    items.sort(key=lambda x: x[0])
    click.echo()
    click.echo(f"  Installed connectors ({len(items)}):")
    click.echo()
    for name, data in items:
        click.echo(f"  \u2705 {name}")
    click.echo()
    click.echo(f"  {len(items)} installed. Run `fastn connector add <name>` to fetch full tool schemas.")
    click.echo()


def _show_all_connectors(
    connectors: dict,
    installed_names: set,
) -> None:
    """Default listing: show all available connectors grouped by source."""
    # Group connectors by source
    source_order = [
        (SOURCE_WORKSPACE, "My Project"),
        (SOURCE_ORG, "My Organization"),
        (SOURCE_COMMUNITY, "Marketplace"),
    ]

    click.echo()
    total = len(connectors)
    click.echo(f"  Available connectors ({total}):")

    for source_key, source_label in source_order:
        group = [
            (k, v) for k, v in connectors.items()
            if v.get("source", SOURCE_COMMUNITY) == source_key
        ]
        if not group:
            continue

        group.sort(key=lambda x: x[0])

        click.echo()
        click.echo(f"  {source_label} ({len(group)}):")
        for name, data in group:
            marker = "\u2705" if name in installed_names else "  "
            ctype = data.get("connector_type", "GROUP")
            if ctype == "DATABASE":
                type_label = " [database]"
            elif ctype and ctype != "GROUP":
                type_label = f" [{ctype.lower()}]"
            else:
                type_label = ""
            click.echo(f"    {marker} {name}{type_label}")

    click.echo()
    installed_count = len(installed_names)
    click.echo(f"  {installed_count} installed. Run `fastn connector add <name>` to fetch full tool schemas.")
    click.echo()


@connector.command(name="ls")
@click.argument("connector_name", required=False, default=None)
@click.option("--active", is_flag=True, help="Show only active/enabled connectors (project + org)")
@click.option("--installed", is_flag=True, help="Show only locally installed connectors (fastn connector add)")
@click.option("-v", "--verbose", is_flag=True, help="Show input/output schemas for each tool")
def list_connectors(connector_name: Optional[str], active: bool, installed: bool, verbose: bool) -> None:
    """List connectors, or show details for a specific one.

    \b
    Usage:
      fastn connector ls              Show all available connectors
      fastn connector ls --active     Show only active/enabled connectors
      fastn connector ls --installed  Show only locally installed connectors
      fastn connector ls slack        Show tools for the 'slack' connector
      fastn connector ls slack -v     Show tools with input/output schemas
    """
    fastn_dir = find_fastn_dir()
    registry = load_registry(fastn_dir)
    connectors = registry.get("connectors", {})

    # Auto-sync if registry is empty
    if not connectors:
        config = load_config()
        if not config.auth_token and not config.api_key:
            raise click.ClickException(
                "Not authenticated. Run `fastn login` first."
            )

        _ensure_fresh_token(config)

        click.echo("Syncing connector registry...")
        registry = _fetch_registry_list(config)
        fastn_dir.mkdir(parents=True, exist_ok=True)
        save_registry(registry, fastn_dir)

        # Update manifest
        manifest = load_manifest(fastn_dir)
        manifest["registry_version"] = registry.get("version", "unknown")
        manifest["last_synced"] = datetime.now(timezone.utc).isoformat()
        save_manifest(manifest, fastn_dir)

        connectors = registry.get("connectors", {})
        if not connectors:
            click.echo("No connectors found in registry.")
            return

    # Dispatch to the appropriate handler
    if connector_name:
        _show_connector_detail(connector_name, connectors, registry, fastn_dir, verbose)
    elif active:
        installed_names = set(get_installed_connectors(fastn_dir))
        _show_active_connectors(connectors, registry, fastn_dir, installed_names, verbose)
    elif installed:
        installed_names = set(get_installed_connectors(fastn_dir))
        _show_installed_connectors(connectors, installed_names)
    else:
        installed_names = set(get_installed_connectors(fastn_dir))
        _show_all_connectors(connectors, installed_names)
