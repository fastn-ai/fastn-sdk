"""Fastn SDK Stub Generator.

Reads connector definitions from the Fastn registry API and generates
Python type stubs (.pyi) for IDE autocomplete.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader


TEMPLATES_DIR = Path(__file__).parent / "templates"

TYPE_MAP_PYTHON = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "List[Any]",
    "object": "Dict[str, Any]",
}

def _sanitize_identifier(name: str) -> str:
    """Convert a name to a valid Python identifier."""
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if name and name[0].isdigit():
        name = "_" + name
    return name


def _to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase for TypeScript."""
    parts = snake_str.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _to_pascal_case(snake_str: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(p.capitalize() for p in snake_str.split("_"))


def _map_type(param_type: str, language: str) -> str:
    """Map a registry type string to the Python stub type."""
    if language != "python":
        raise ValueError(f"Unsupported language: {language}")
    return TYPE_MAP_PYTHON.get(param_type, "Any")


def _extract_tool_params(
    tool_data: Dict[str, Any], tool_name: str = "",
) -> List[Dict[str, Any]]:
    """Extract the inner user-facing params from a tool's inputSchema.

    Processes ALL top-level wrapper keys (body, url, param, headers, etc.)
    and flattens their inner properties into a single param list that
    matches the SDK calling convention.  This mirrors the runtime routing
    logic in ``_build_params_from_schema`` (client.py).

    For inner params that are objects with their own properties, attaches
    ``typed_dict_name`` and ``sub_params`` for TypedDict stub generation.

        # Registry inputSchema structure (multi-wrapper):
        # { "properties": {
        #     "body": { "properties": { "title": {...}, "body": {...} }, ... },
        #     "url":  { "properties": { "OWNER": {...}, "REPO": {...} }, ... }
        # } }
        #
        # SDK usage:  fastn.github.github_create_issue(title="bug", OWNER="org", REPO="repo")
        # Stub:       def github_create_issue(self, OWNER: str, REPO: str, title: str, ...) -> ...: ...
    """
    params: List[Dict[str, Any]] = []
    input_schema = tool_data.get("inputSchema", {})
    schema_props = input_schema.get("properties", {})

    if not schema_props:
        # Fallback: use legacy "params" field if no inputSchema
        raw_params = tool_data.get("params", {})
        for param_name, param_info in sorted(raw_params.items()):
            safe_param_name = _sanitize_identifier(param_name)
            params.append({
                "name": safe_param_name,
                "camel_name": _to_camel_case(safe_param_name),
                "type": param_info.get("type", "string"),
                "required": param_info.get("required", False),
                "description": param_info.get("description", ""),
                "typed_dict_name": None,
            })
        return params

    # Iterate ALL top-level properties.  Object-typed entries with inner
    # properties are treated as wrappers (body, url, param, headers, …)
    # whose contents are flattened into the user-facing param list.
    seen_names: set = set()
    top_required = set(input_schema.get("required", []))

    for wrapper_key, wrapper_data in sorted(schema_props.items()):
        if (
            isinstance(wrapper_data, dict)
            and wrapper_data.get("type") == "object"
            and wrapper_data.get("properties")
        ):
            # Wrapper — extract inner properties as flat user-facing params
            inner_props = wrapper_data["properties"]
            inner_required = set(wrapper_data.get("required", []))

            for param_name, param_info in sorted(inner_props.items()):
                safe_param_name = _sanitize_identifier(param_name)
                if safe_param_name in seen_names:
                    continue  # deduplicate across wrappers (first wins)
                seen_names.add(safe_param_name)

                param_dict: Dict[str, Any] = {
                    "name": safe_param_name,
                    "camel_name": _to_camel_case(safe_param_name),
                    "type": param_info.get("type", "string"),
                    "required": param_name in inner_required,
                    "description": param_info.get("description", ""),
                    "typed_dict_name": None,
                }

                # Nested object with own properties → TypedDict
                if (
                    param_info.get("type") == "object"
                    and param_info.get("properties")
                    and tool_name
                ):
                    td_name = (
                        "_" + _to_pascal_case(tool_name)
                        + _to_pascal_case(safe_param_name)
                    )
                    sub_required = set(param_info.get("required", []))
                    sub_params = []
                    for sp_name, sp_info in sorted(
                        param_info["properties"].items()
                    ):
                        safe_sp = _sanitize_identifier(sp_name)
                        sub_params.append({
                            "name": safe_sp,
                            "camel_name": _to_camel_case(safe_sp),
                            "type": sp_info.get("type", "string"),
                            "required": sp_name in sub_required,
                            "description": sp_info.get("description", ""),
                        })
                    param_dict["typed_dict_name"] = td_name
                    param_dict["sub_params"] = sub_params

                params.append(param_dict)
        else:
            # Flat (non-wrapper) top-level field
            safe_param_name = _sanitize_identifier(wrapper_key)
            if safe_param_name in seen_names:
                continue
            seen_names.add(safe_param_name)
            params.append({
                "name": safe_param_name,
                "camel_name": _to_camel_case(safe_param_name),
                "type": (
                    wrapper_data.get("type", "string")
                    if isinstance(wrapper_data, dict) else "string"
                ),
                "required": wrapper_key in top_required,
                "description": (
                    wrapper_data.get("description", "")
                    if isinstance(wrapper_data, dict) else ""
                ),
                "typed_dict_name": None,
            })

    return params


def parse_registry(registry_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse raw registry JSON into a normalized structure for templates.

    Returns a dict with:
        version: str
        connectors: list of connector dicts, each with:
            name: str (snake_case identifier)
            display_name: str
            category: str
            class_name: str (PascalCase)
            tools: list of tool dicts
    """
    connectors = []
    raw_connectors = registry_data.get("connectors", {})

    for connector_name, connector_data in sorted(raw_connectors.items()):
        safe_name = _sanitize_identifier(connector_name)
        tools = []
        raw_tools = connector_data.get("tools", {})

        for tool_name, tool_data in sorted(raw_tools.items()):
            safe_tool_name = _sanitize_identifier(tool_name)
            params = _extract_tool_params(tool_data, tool_name=tool_name)

            # Sort: required params first, then optional
            params.sort(key=lambda p: (not p["required"], p["name"]))

            # Collect TypedDict definitions from nested-object params
            typed_dicts = []
            for param in params:
                if param.get("typed_dict_name"):
                    typed_dicts.append({
                        "name": param["typed_dict_name"],
                        "fields": param["sub_params"],
                    })

            tools.append({
                "name": safe_tool_name,
                "camel_name": _to_camel_case(safe_tool_name),
                "action_id": tool_data.get("toolId", "") or tool_data.get("actionId", ""),
                "description": tool_data.get("description", ""),
                "params": params,
                "typed_dicts": typed_dicts,
            })

        connectors.append({
            "name": safe_name,
            "display_name": connector_data.get("display_name", connector_name),
            "category": connector_data.get("category", ""),
            "class_name": _to_pascal_case(safe_name) + "Connector",
            "tools": tools,
            "tool_count": len(tools),
        })

    return {
        "version": registry_data.get("version", "unknown"),
        "connectors": connectors,
    }


def parse_connector(
    connector_name: str, connector_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Parse a single connector's data into normalized form."""
    registry = {
        "version": "",
        "connectors": {connector_name: connector_data},
    }
    parsed = parse_registry(registry)
    if parsed["connectors"]:
        return parsed["connectors"][0]
    return {}


class StubGenerator:
    """Generates type stub files from Fastn registry data."""

    def __init__(self, language: str = "python") -> None:
        if language != "python":
            raise ValueError(f"Unsupported language: {language}")
        self.language = language
        template_dir = TEMPLATES_DIR / language
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        self.env.filters["map_type"] = lambda t: _map_type(t, language)
        self.env.filters["camel_case"] = _to_camel_case
        self.env.filters["pascal_case"] = _to_pascal_case

    def generate_index(
        self,
        all_connectors: List[Dict[str, Any]],
        installed_connectors: List[str],
    ) -> str:
        """Generate the root index stub (__init__.pyi)."""
        ext = "pyi"
        template = self.env.get_template(f"index.{ext}.j2")
        return template.render(
            connectors=all_connectors,
            installed=installed_connectors,
        )

    def generate_connector(self, connector: Dict[str, Any]) -> str:
        """Generate a full connector stub file."""
        ext = "pyi"
        template = self.env.get_template(f"connector.{ext}.j2")
        return template.render(connector=connector)

    def generate_placeholder(
        self, connectors: List[Dict[str, Any]]
    ) -> str:
        """Generate placeholder stubs for non-installed connectors."""
        ext = "pyi"
        template = self.env.get_template(f"placeholder.{ext}.j2")
        return template.render(connectors=connectors)

    def generate_all(
        self,
        registry_data: Dict[str, Any],
        installed_connectors: List[str],
        output_dir: str,
    ) -> List[str]:
        """Generate all stub files and write them to output_dir.

        Returns list of generated file paths.
        """
        parsed = parse_registry(registry_data)
        all_connectors = parsed["connectors"]
        generated_files: List[str] = []

        output_path = Path(output_dir)

        # For Python, put stubs inside a fastn/ package directory
        # so Pylance resolves them via stubPath setting.
        if self.language == "python":
            stub_root = output_path / "fastn"
        else:
            stub_root = output_path

        connectors_dir = stub_root / "connectors"
        connectors_dir.mkdir(parents=True, exist_ok=True)

        # Generate index
        ext = "pyi"
        index_content = self.generate_index(all_connectors, installed_connectors)
        index_file = stub_root / f"__init__.{ext}"
        index_file.write_text(index_content)
        generated_files.append(str(index_file))

        # Generate per-connector stubs for installed connectors
        installed_set = set(installed_connectors)
        placeholder_connectors = []

        for connector in all_connectors:
            if connector["name"] in installed_set:
                content = self.generate_connector(connector)
                filename = f"{connector['name']}.{ext}"
                filepath = connectors_dir / filename
                filepath.write_text(content)
                generated_files.append(str(filepath))
            else:
                placeholder_connectors.append(connector)

        # Generate placeholder file
        if placeholder_connectors:
            placeholder_content = self.generate_placeholder(placeholder_connectors)
            placeholder_file = connectors_dir / f"_placeholders.{ext}"
            placeholder_file.write_text(placeholder_content)
            generated_files.append(str(placeholder_file))

        # For Python, add __init__.pyi to connectors/ so it's a package
        if self.language == "python":
            connectors_init = connectors_dir / "__init__.pyi"
            if not connectors_init.exists():
                connectors_init.write_text("")
                generated_files.append(str(connectors_init))

        return generated_files


def generate_stubs(
    registry_data: Dict[str, Any],
    installed_connectors: List[str],
    output_dir: str,
    language: str = "python",
) -> List[str]:
    """Convenience function to generate stubs.

    Args:
        registry_data: Full registry JSON from the API.
        installed_connectors: List of connector names the user has added.
        output_dir: Directory to write stub files to.
        language: 'python' (the only supported language).

    Returns:
        List of generated file paths.
    """
    generator = StubGenerator(language=language)
    return generator.generate_all(registry_data, installed_connectors, output_dir)
