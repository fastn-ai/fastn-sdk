# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Every partner-facing spec operation is in the SDK, nothing else, and the manifest equals the Node SDK's (a port of
node/test/unit/coverage.test.ts plus a structural parity check against node/src/generated/ops.ts)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastn.platform import SPEC_FILE, VERSION, FastnClient
from fastn.platform._generated.api import API_GROUPS, FastnApis, build_apis
from fastn.platform.unstable import OPS, OpDef

PY_ROOT = Path(__file__).resolve().parents[2]
NODE = PY_ROOT.parent / "node"
METHODS = ["get", "put", "post", "delete", "patch", "head", "options", "trace"]
HIDDEN_TAGS = {"Admin", "Platform Config", "Platform", "Support"}
PUBLIC_INTERNAL = {"createEmbedToken", "getSetupLinkStatus"}


def is_hidden(op: Dict[str, Any]) -> bool:
    tag = (op.get("tags") or [""])[0]
    return tag in HIDDEN_TAGS or (op.get("x-mcp") is False and op.get("operationId") not in PUBLIC_INTERNAL)


def spec_ops() -> Tuple[List[Dict[str, str]], List[str]]:
    spec = json.loads((NODE / "spec" / SPEC_FILE).read_text())
    visible: List[Dict[str, str]] = []
    hidden: List[str] = []
    for p, item in spec["paths"].items():
        for m in METHODS:
            op = item.get(m)
            if isinstance(op, dict) and op.get("operationId"):
                if is_hidden(op):
                    hidden.append(op["operationId"])
                else:
                    visible.append({"id": op["operationId"], "method": m.upper(), "path": p})
    return visible, hidden


def node_ops() -> Dict[str, Dict[str, Any]]:
    """The Node manifest, parsed out of ops.ts (`  <id>: {...} as OpDef,`)."""
    out = {}
    for m in re.finditer(r'^\s+(\w+): (\{"id":.*\}) as OpDef,$', (NODE / "src" / "generated" / "ops.ts").read_text(), re.M):
        out[m.group(1)] = json.loads(m.group(2))
    return out


def node_shape(op: OpDef) -> Dict[str, Any]:
    """A Python OpDef in the JSON shape ops.ts uses."""
    d: Dict[str, Any] = {"id": op.id, "method": op.method, "path": op.path, "params": [{"key": p.key, "name": p.name, "in": p.location, **({"required": True} if p.required else {})} for p in op.params]}
    if op.body is not None:
        b = op.body
        if b.kind == "fields":
            d["body"] = {"kind": "fields", "keys": dict(b.keys or {}), **({"open": True} if b.open else {}), **({"requiredKeys": list(b.required_keys)} if b.required_keys else {}), "contentType": b.content_type}
        else:
            d["body"] = {"kind": "whole", "key": b.key, "required": b.required, "contentType": b.content_type}
    if op.idempotent:
        d["idempotent"] = True
    return d


def test_same_operation_set_and_wire_shape_as_the_node_sdk() -> None:
    node = node_ops()
    assert len(node) == 461
    assert sorted(OPS) == sorted(node)
    for oid, expected in node.items():
        assert node_shape(OPS[oid]) == expected, oid


def test_has_the_same_count_as_the_visible_spec_operations() -> None:
    visible, _ = spec_ops()
    assert len(OPS) == len(visible)
    assert len(visible) > 400


def test_leaves_platform_admin_and_backend_only_routes_out() -> None:
    _, hidden = spec_ops()
    assert len(hidden) > 150
    for oid in hidden:
        assert oid not in OPS, oid
    for oid in ["listPlatformConfig", "getAuthProviderCredentials", "oauthCallback", "listTeams"]:
        assert oid in hidden
    assert "createEmbedToken" in OPS and "getSetupLinkStatus" in OPS


def test_matches_method_and_path_for_each_operation_id() -> None:
    visible, _ = spec_ops()
    for s in visible:
        o = OPS[s["id"]]
        assert f"{o.method} {o.path}" == f"{s['method']} {s['path']}", s["id"]


def test_exposes_each_operation_as_a_method_on_its_area_in_snake_case_and_camel_case() -> None:
    calls: List[str] = []

    class T:
        def call(self, op: OpDef, input: Any, opts: Any) -> Any:
            calls.append(op.id)
            return {}

    apis = build_apis(T())
    methods: Dict[str, Any] = {}
    for snake, camel in API_GROUPS:
        area = getattr(apis, snake)
        assert getattr(apis, camel) is area
        for name in dir(type(area)):
            if not name.startswith("_"):
                methods[name] = getattr(area, name)
    visible, _ = spec_ops()
    for s in visible:
        oid = s["id"]
        snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", oid).lower()
        assert oid in methods, oid
        assert snake in methods, snake
        assert methods[oid] == methods[snake]
    # every area method is one of the operations, under either spelling
    ids = {s["id"] for s in visible}
    for name in methods:
        assert name in ids or re.sub(r"_(.)", lambda m: m.group(1).upper(), name) in ids, name


def test_every_api_group_is_on_the_client_and_under_api() -> None:
    fastn = FastnClient(api_key="k")
    assert isinstance(fastn.api, FastnApis)
    for snake, camel in API_GROUPS:
        assert getattr(fastn, snake) is getattr(fastn.api, snake)
        assert getattr(fastn, camel) is getattr(fastn.api, snake)
    assert fastn.api_keys is fastn.apiKeys


def test_every_path_parameter_has_an_input() -> None:
    for o in OPS.values():
        for m in re.finditer(r"\{([^}]+)\}", o.path):
            assert any(p.location == "path" and p.name == m.group(1) for p in o.params), f"{o.id} {m.group(1)}"


def test_generated_files_are_up_to_date() -> None:
    r = subprocess.run([sys.executable, str(PY_ROOT / "scripts" / "generate_platform.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_version_matches_pyproject() -> None:
    m = re.search(r'^version = "([^"]+)"', (PY_ROOT / "pyproject.toml").read_text(), re.M)
    assert m and m.group(1) == VERSION
