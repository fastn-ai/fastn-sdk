"""Dynamic connector proxy for Fastn SDK.

Provides attribute-based access to tools within a connector,
translating method calls into executeTool API calls.

This module is not used directly. Instead, access connectors through the client:
    fastn = FastnClient(api_key="...", project_id="...")
    fastn.slack.send_message(channel="general", text="Hello!")
    #     ^^^^^ DynamicConnector
    #          ^^^^^^^^^^^^^^ tool method resolved via __getattr__

How it works:
    1. ``fastn.slack`` triggers ``FastnClient.__getattr__("slack")``
    2. The client looks up "slack" in the local registry, gets tool definitions
    3. A ``DynamicConnector`` is created with those tools
    4. ``connector.send_message(channel=..., text=...)`` triggers
       ``DynamicConnector.__getattr__("send_message")`` which returns a
       closure that calls ``_execute_tool()`` with the correct toolId

connection_id / tenant_id support:
    # Per-call — extracted from kwargs before sending to API
    fastn.slack.send_message(connection_id="conn_abc", channel="general", text="Hi")
    fastn.slack.send_message(tenant_id="acme", channel="general", text="Hi")

    # Bound — all calls on this proxy use the same connection_id
    slack = fastn.connect("conn_abc")
    slack.send_message(channel="general", text="Hi")

Migrations:
    When tool schemas change between registry versions, migrations.json maps
    old calling conventions to new ones and emits DeprecationWarning so
    existing code keeps working.

Classes:
    DynamicConnector        Sync proxy. Tool calls return results directly.
    AsyncDynamicConnector   Async proxy. Tool calls return awaitables.
"""

from __future__ import annotations

import warnings
from typing import Any, Callable, Dict, Optional, Tuple

from fastn.exceptions import ToolNotFoundError


def _apply_migrations(
    connector_name: str,
    tool_name: str,
    kwargs: Dict[str, Any],
    tool_migrations: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply migration rules to kwargs and emit deprecation warnings.

    Handles three migration types:
        - deprecated_params: params that were removed — strip them out
        - param_defaults: new required params — fill in defaults
        - type_coercions: params whose type changed — warn the user

    Returns the cleaned kwargs dict (mutated in place for efficiency).
    """
    # 1. Handle deprecated (removed) params — strip and warn
    deprecated = tool_migrations.get("deprecated_params", {})
    for param_name, info in deprecated.items():
        if param_name in kwargs:
            kwargs.pop(param_name)
            warnings.warn(
                info.get("message", f"Parameter '{param_name}' is deprecated."),
                DeprecationWarning,
                stacklevel=4,
            )

    # 2. Handle new required params — fill defaults and warn
    defaults = tool_migrations.get("param_defaults", {})
    for param_name, info in defaults.items():
        if param_name not in kwargs:
            default_val = info.get("default")
            if default_val is not None:
                kwargs[param_name] = default_val
            warnings.warn(
                info.get(
                    "message",
                    f"Parameter '{param_name}' is now required in "
                    f"'{connector_name}.{tool_name}()'.",
                ),
                DeprecationWarning,
                stacklevel=4,
            )

    # 3. Handle type coercions — warn but don't modify the value
    coercions = tool_migrations.get("type_coercions", {})
    for param_name, info in coercions.items():
        if param_name in kwargs:
            warnings.warn(
                info.get(
                    "message",
                    f"Parameter '{param_name}' type has changed in "
                    f"'{connector_name}.{tool_name}()'.",
                ),
                DeprecationWarning,
                stacklevel=4,
            )

    return kwargs


# Type for the result of _resolve_tool_call
_ToolResolution = Tuple[
    str,                    # tool_id
    Dict[str, Any],         # tool_info or dep_info
    Dict[str, Any],         # tool_migrations
    Optional[str],          # connection_id
    str,                    # connector_id
    str,                    # connector_name
    bool,                   # is_deprecated
    str,                    # deprecation_message (empty if not deprecated)
]


class _BaseDynamicConnector:
    """Shared base for sync and async connector proxies.

    Contains all logic except the final closure construction in __getattr__,
    which differs only in sync vs async.
    """

    _class_label = "DynamicConnector"

    def __init__(
        self,
        connector_name: str,
        tools: Dict[str, Dict[str, str]],
        execute_fn: Callable[..., Any],
        connector_id: str = "",
        connection_id: Optional[str] = None,
        migrations: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._connector_name = connector_name
        self._tools = tools
        self._execute_fn = execute_fn
        self._connector_id = connector_id
        self._connection_id = connection_id
        self._migrations = migrations or {}

    def _resolve_tool_call(self, tool_name: str) -> _ToolResolution:
        """Resolve a tool name to its execution metadata.

        Handles exact match, underscore-collapsed fallback, and deprecated
        tool migration lookup.

        Returns a tuple of (tool_id, tool_info, tool_migrations,
        connection_id, connector_id, connector_name, is_deprecated,
        deprecation_message).

        Raises:
            AttributeError: If tool_name starts with ``_``.
            ToolNotFoundError: If the tool is not found in the registry.
        """
        if tool_name.startswith("_"):
            raise AttributeError(tool_name)

        tool_info = self._tools.get(tool_name)

        # Fallback: try matching without underscores (send_message -> sendmessage)
        if tool_info is None and "_" in tool_name:
            collapsed = tool_name.replace("_", "")
            tool_info = self._tools.get(collapsed)

        # Check if this is a deprecated (removed) tool with a migration
        if tool_info is None:
            deprecated_tools = self._migrations.get("deprecated_tools", {})
            if tool_name in deprecated_tools:
                dep_info = deprecated_tools[tool_name]
                message = dep_info.get(
                    "message",
                    f"'{self._connector_name}.{tool_name}()' has been removed.",
                )
                return (
                    dep_info.get("toolId", "") or dep_info.get("actionId", ""),
                    dep_info,
                    {},
                    self._connection_id,
                    self._connector_id,
                    self._connector_name,
                    True,
                    message,
                )

            raise ToolNotFoundError(
                self._connector_name, tool_name, has_tools=bool(self._tools),
            )

        # "toolId" is the server-side identifier for a tool
        tool_migrations = self._migrations.get("tools", {}).get(tool_name, {})
        return (
            tool_info.get("toolId", "") or tool_info.get("actionId", ""),
            tool_info,
            tool_migrations,
            self._connection_id,
            self._connector_id,
            self._connector_name,
            False,
            "",
        )

    def __repr__(self) -> str:
        conn = f", connection='{self._connection_id}'" if self._connection_id else ""
        return (
            f"<{self._class_label} '{self._connector_name}' "
            f"({len(self._tools)} tools){conn}>"
        )

    def __dir__(self) -> list:
        # Include both current tools and deprecated tools
        names = list(self._tools.keys())
        names.extend(self._migrations.get("deprecated_tools", {}).keys())
        return sorted(set(names))


class DynamicConnector(_BaseDynamicConnector):
    """Sync proxy object that resolves tool method calls at runtime."""

    _class_label = "DynamicConnector"

    def __getattr__(self, tool_name: str) -> Callable[..., Any]:
        """Resolve a tool name to a sync callable."""
        (tool_id, tool_info, tool_migrations, connection_id,
         connector_id, connector_name, is_deprecated, dep_message) = \
            self._resolve_tool_call(tool_name)

        if is_deprecated:
            def deprecated_tool_method(**kwargs: Any) -> Any:
                warnings.warn(dep_message, DeprecationWarning, stacklevel=2)
                call_connection_id = kwargs.pop("connection_id", None) or connection_id
                call_tenant_id = kwargs.pop("tenant_id", None)
                return self._execute_fn(
                    tool_id, kwargs, connector_id, tool_info,
                    call_connection_id, call_tenant_id,
                )
            deprecated_tool_method.__name__ = tool_name
            deprecated_tool_method.__qualname__ = f"{connector_name}.{tool_name}"
            return deprecated_tool_method

        def tool_method(**kwargs: Any) -> Any:
            if tool_migrations:
                _apply_migrations(connector_name, tool_name, kwargs, tool_migrations)
            call_connection_id = kwargs.pop("connection_id", None) or connection_id
            call_tenant_id = kwargs.pop("tenant_id", None)
            return self._execute_fn(
                tool_id, kwargs, connector_id, tool_info,
                call_connection_id, call_tenant_id,
            )
        tool_method.__name__ = tool_name
        tool_method.__qualname__ = f"{connector_name}.{tool_name}"
        return tool_method


class AsyncDynamicConnector(_BaseDynamicConnector):
    """Async proxy object that resolves tool method calls at runtime."""

    _class_label = "AsyncDynamicConnector"

    def __getattr__(self, tool_name: str) -> Callable[..., Any]:
        """Resolve a tool name to an async callable."""
        (tool_id, tool_info, tool_migrations, connection_id,
         connector_id, connector_name, is_deprecated, dep_message) = \
            self._resolve_tool_call(tool_name)

        if is_deprecated:
            async def deprecated_tool_method(**kwargs: Any) -> Any:
                warnings.warn(dep_message, DeprecationWarning, stacklevel=2)
                call_connection_id = kwargs.pop("connection_id", None) or connection_id
                call_tenant_id = kwargs.pop("tenant_id", None)
                return await self._execute_fn(
                    tool_id, kwargs, connector_id, tool_info,
                    call_connection_id, call_tenant_id,
                )
            deprecated_tool_method.__name__ = tool_name
            deprecated_tool_method.__qualname__ = f"{connector_name}.{tool_name}"
            return deprecated_tool_method

        async def tool_method(**kwargs: Any) -> Any:
            if tool_migrations:
                _apply_migrations(connector_name, tool_name, kwargs, tool_migrations)
            call_connection_id = kwargs.pop("connection_id", None) or connection_id
            call_tenant_id = kwargs.pop("tenant_id", None)
            return await self._execute_fn(
                tool_id, kwargs, connector_id, tool_info,
                call_connection_id, call_tenant_id,
            )
        tool_method.__name__ = tool_name
        tool_method.__qualname__ = f"{connector_name}.{tool_name}"
        return tool_method
