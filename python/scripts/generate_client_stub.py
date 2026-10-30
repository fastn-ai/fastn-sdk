#!/usr/bin/env python3
"""Generate fastn/__init__.pyi: the typed surface of FastnClient / AsyncFastnClient.

Type checkers and IDEs read this stub instead of fastn/__init__.py, so it must
declare everything the package exports, plus one property per connector stub
in fastn/connectors/*.pyi.

Usage:
    python3 scripts/generate_client_stub.py          # write the stub
    python3 scripts/generate_client_stub.py --check  # fail if it is out of date
"""
from __future__ import annotations

import keyword
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "fastn"
CONNECTORS = PKG / "connectors"
OUT = PKG / "__init__.pyi"

CLASS_RE = re.compile(r"^class (\w+Connector):", re.M)


def _connectors() -> list:
    found = []
    for path in sorted(CONNECTORS.glob("*.pyi")):
        name = path.stem
        if name.startswith("_") or keyword.iskeyword(name):
            continue
        m = CLASS_RE.search(path.read_text(encoding="utf-8"))
        if m:
            found.append((name, m.group(1)))
    return found


def _version() -> str:
    m = re.search(r'^__version__ = "([^"]+)"', (PKG / "__init__.py").read_text(), re.M)
    assert m, "__version__ not found in fastn/__init__.py"
    return m.group(1)


HEADER = '''"""Type stubs for the fastn package (generated, do not edit).

Regenerate with: python3 scripts/generate_client_stub.py
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from ._auth_ns import _AuthAsync, _AuthSync
from ._catalog import _ConnectorCatalog, _ConnectorCatalogAsync
from ._flows import _FlowsAsync, _FlowsSync
from ._kit import _KitAsync, _KitSync
from ._projects import _ProjectsAsync, _ProjectsSync
from ._skills import _SkillsAsync, _SkillsSync
from .exceptions import (
    APIError as APIError,
    AuthError as AuthError,
    ConfigError as ConfigError,
    ConnectionNotFoundError as ConnectionNotFoundError,
    ConnectorNotFoundError as ConnectorNotFoundError,
    FastnError as FastnError,
    FlowNotFoundError as FlowNotFoundError,
    OAuthError as OAuthError,
    RegistryError as RegistryError,
    RunNotFoundError as RunNotFoundError,
    ToolNotFoundError as ToolNotFoundError,
)
'''

INIT = '''    def __init__(
        self,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        timeout: Optional[float] = None,
        config_path: Optional[str] = None,
        auth_token: Optional[str] = None,
        agent_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        stage: Optional[str] = None,
        max_retries: int = 3,
        verbose: bool = False,
    ) -> None: ...
'''

SYNC_BODY = '''    connectors: _ConnectorCatalog
    flows: _FlowsSync
    auth: _AuthSync
    projects: _ProjectsSync
    skills: _SkillsSync
    kit: _KitSync

    def connect(self, connection_id: str) -> Any: ...
    def get_tools(self, connector_name: str) -> List[Dict[str, Any]]: ...
    def get_tool(self, connector_name: str, tool_name: str) -> Dict[str, Any]: ...
    def execute(
        self,
        tool: str,
        params: Dict[str, Any],
        connection_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Any: ...
    def run(self, prompt: str, connection_id: Optional[str] = None) -> Dict[str, Any]: ...
    def get_tools_for(
        self,
        prompt: str,
        *,
        format: str = "openai",
        limit: int = 5,
        connector: Union[str, List[str], None] = None,
    ) -> List[Dict[str, Any]]: ...
    def close(self) -> None: ...
    def __enter__(self) -> FastnClient: ...
    def __exit__(self, *args: Any) -> None: ...
    def __getattr__(self, name: str) -> Any: ...
'''

ASYNC_BODY = '''    connectors: _ConnectorCatalogAsync
    flows: _FlowsAsync
    auth: _AuthAsync
    projects: _ProjectsAsync
    skills: _SkillsAsync
    kit: _KitAsync

    def connect(self, connection_id: str) -> Any: ...
    def get_tools(self, connector_name: str) -> List[Dict[str, Any]]: ...
    def get_tool(self, connector_name: str, tool_name: str) -> Dict[str, Any]: ...
    async def execute(
        self,
        tool: str,
        params: Dict[str, Any],
        connection_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Any: ...
    async def run(self, prompt: str, connection_id: Optional[str] = None) -> Dict[str, Any]: ...
    async def get_tools_for(
        self,
        prompt: str,
        *,
        format: str = "openai",
        limit: int = 5,
        connector: Union[str, List[str], None] = None,
    ) -> List[Dict[str, Any]]: ...
    async def close(self) -> None: ...
    async def __aenter__(self) -> AsyncFastnClient: ...
    async def __aexit__(self, *args: Any) -> None: ...
    def __getattr__(self, name: str) -> Any: ...
'''


def render() -> str:
    conns = _connectors()
    out = [HEADER]
    for name, cls in conns:
        out.append(f"from .connectors.{name} import {cls}\n")
    out.append(f'\n__version__: str = "{_version()}"\n')
    for client, doc, body in (
        ("FastnClient", "Synchronous fastn client with typed connector access.", SYNC_BODY),
        ("AsyncFastnClient", "Async fastn client. Connector calls return awaitables.", ASYNC_BODY),
    ):
        out.append(f"\n\nclass {client}:\n    \"\"\"{doc}\"\"\"\n\n{INIT}\n{body}")
        for name, cls in conns:
            out.append(f"    @property\n    def {name}(self) -> {cls}: ...\n")
    return "".join(out)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("fastn/__init__.pyi is out of date: run python3 scripts/generate_client_stub.py")
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(_connectors())} connectors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
