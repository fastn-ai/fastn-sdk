#!/usr/bin/env python3
# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Generates fastn/platform/_generated/{ops,types,api}.py from node/spec/openapi-*.json.

A port of node/scripts/generate.ts (and the hidden rules of node/scripts/surface.ts): the same operations, the same
input keys (claim order path > query > body > header, header keys camel-cased without the x- prefix, collisions
renamed `bodyId` / `queryId` / ...), the same body kinds and the same idempotent flags, so a Python input dict is
named exactly like the Node SDK input and the Fastn Workspace tool input.

    python3 scripts/generate_platform.py            # write the three files
    python3 scripts/generate_platform.py --check    # exit 1 when the written files would change
    python3 scripts/generate_platform.py --spec=/path/to/openapi-vX.json

Output is deterministic: operations sorted by operationId, areas sorted by tag, fields in spec order.
"""

from __future__ import annotations

import json
import keyword
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
PY_ROOT = os.path.dirname(HERE)
SPEC_DIR = os.path.normpath(os.path.join(PY_ROOT, "..", "node", "spec"))
OUT_DIR = os.path.join(PY_ROOT, "fastn", "platform", "_generated")
METHODS = ["get", "put", "post", "delete", "patch", "head", "options", "trace"]

# What the SDK leaves out (node/scripts/surface.ts): platform-administration areas, and routes marked x-mcp: false
# except the few a partner backend does use.
HIDDEN_TAGS = {"Admin", "Platform Config", "Platform", "Support"}
PUBLIC_INTERNAL = {"createEmbedToken", "getSetupLinkStatus"}
# Operations the platform de-duplicates by Idempotency-Key that the spec does not declare yet (verified live).
IDEMPOTENT_EXTRA = {"createUnifiedRecord"}
# Members FastnClient defines itself; an area with one of these names would shadow them.
RESERVED = {"api", "tools", "customer", "customers", "call", "me", "transport", "base_url", "catalog", "close", "webhooks"}

Json = Dict[str, Any]


def is_hidden(op: Json) -> bool:
    tags = op.get("tags") or []
    tag = tags[0] if tags else ""
    return tag in HIDDEN_TAGS or (op.get("x-mcp") is False and op.get("operationId", "") not in PUBLIC_INTERNAL)


def is_obj(v: Any) -> bool:
    return isinstance(v, dict)


def camel(s: str) -> str:
    out = re.sub(r"[^A-Za-z0-9]+(.)?", lambda m: (m.group(1) or "").upper(), s)
    return out[:1].lower() + out[1:]


def pascal(s: str) -> str:
    c = camel(s)
    return c[:1].upper() + c[1:]


def snake(s: str) -> str:
    """createSetupLink -> create_setup_link; listAPIKeys -> list_api_keys; whoami -> whoami."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
    return s.lower().strip("_")


def tag_name(tag: str) -> str:
    """The client member for a tag: a leading acronym is lower-cased ("API Keys" -> apiKeys), a trailing " API" dropped."""
    t = re.sub(r"\s+API$", "", tag, flags=re.I)
    t = re.sub(r"^[A-Z]{2,}(?=\s|$)", lambda m: m.group(0).lower(), t)
    return camel(t)


def header_input_key(header: str) -> str:
    h = re.sub(r"^x-", "", header, flags=re.I)
    h = h[:1].lower() + h[1:]
    return re.sub(r"-([a-zA-Z0-9])", lambda m: m.group(1).upper(), h)


def ident_ok(s: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", s)) and not keyword.iskeyword(s)


def one_line(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def doc_lines(lines: List[Optional[str]]) -> List[str]:
    return [one_line(x).replace('"""', "'''").replace("\\", "\\\\") for x in lines if x and x.strip()]


class Generator:
    def __init__(self, spec: Json, spec_file: str) -> None:
        self.spec = spec
        self.spec_file = spec_file
        self.type_blocks: List[str] = []
        self.type_names: Set[str] = set()
        self.component_names: Dict[str, str] = {}
        for name in self.spec.get("components", {}).get("schemas", {}):
            self.component_names[name] = self.unique_name(pascal(name))

    # ── spec helpers ──
    def pointer(self, ref: str) -> Json:
        node: Any = self.spec
        for raw in ref[2:].split("/"):
            node = node.get(raw.replace("~1", "/").replace("~0", "~")) if isinstance(node, dict) else None
        if node is None:
            raise RuntimeError(f"unresolvable $ref {ref}")
        return node

    def resolve_param(self, p: Json) -> Json:
        if isinstance(p.get("$ref"), str):
            merged = dict(self.pointer(p["$ref"]))
            merged.update({k: v for k, v in p.items() if k != "$ref"})
            return merged
        return p

    def unique_name(self, base: str) -> str:
        name, n = base, 1
        while name in self.type_names:
            n += 1
            name = f"{base}{n}"
        self.type_names.add(name)
        return name

    # ── JSON schema -> Python type expression ──
    def py(self, schema: Optional[Json], name_hint: str) -> str:
        if not is_obj(schema) or not schema:
            return "Any"
        assert schema is not None
        ref = schema.get("$ref")
        if isinstance(ref, str):
            return self.component_names.get(ref.split("/")[-1], "Any")
        if "const" in schema:
            return f"Literal[{json.dumps(schema['const'])!s}]".replace("null", "None").replace("true", "True").replace("false", "False") if not isinstance(schema["const"], str) else f"Literal[{schema['const']!r}]"
        if isinstance(schema.get("enum"), list):
            return self.literal(schema["enum"])
        for k in ("oneOf", "anyOf"):
            if isinstance(schema.get(k), list):
                return self.union([self.py(s, name_hint) for s in schema[k]])
        if isinstance(schema.get("allOf"), list):
            parts = [self.deref(s) for s in schema["allOf"]]
            if all(is_obj(p) and is_obj(p.get("properties")) for p in parts):
                merged: Json = {"type": "object", "properties": {}, "required": []}
                for p in parts:
                    merged["properties"].update(p.get("properties") or {})
                    merged["required"] += p.get("required") or []
                return self.py(merged, name_hint)
            return "Any"
        nullable = schema.get("nullable") is True
        types: List[str] = schema["type"] if isinstance(schema.get("type"), list) else ([schema["type"]] if schema.get("type") else [])
        if not types:
            types = ["object" if (schema.get("properties") or "additionalProperties" in schema) else ("array" if schema.get("items") else "any")]
        parts_py: List[str] = []
        for t in types:
            if t == "string":
                parts_py.append("str")
            elif t in ("number",):
                parts_py.append("float")
            elif t == "integer":
                parts_py.append("int")
            elif t == "boolean":
                parts_py.append("bool")
            elif t == "null":
                parts_py.append("None")
            elif t == "array":
                parts_py.append(f"List[{self.py(schema.get('items'), name_hint + 'Item')}]")
            elif t == "object":
                parts_py.append(self.object_py(schema, name_hint))
            else:
                parts_py.append("Any")
        if nullable:
            parts_py.append("None")
        return self.union(parts_py)

    def deref(self, s: Any) -> Any:
        return self.pointer(s["$ref"]) if is_obj(s) and isinstance(s.get("$ref"), str) else s

    @staticmethod
    def literal(values: List[Any]) -> str:
        items = []
        for v in values:
            if isinstance(v, (str, bool, int, float)) or v is None:
                items.append(repr(v))
            else:
                return "Any"
        return f"Literal[{', '.join(items)}]" if items else "Any"

    @staticmethod
    def union(parts: List[str]) -> str:
        seen: List[str] = []
        for p in parts:
            if p not in seen:
                seen.append(p)
        if not seen:
            return "Any"
        if "Any" in seen:
            return "Any"
        if len(seen) == 1:
            return seen[0]
        if "None" in seen:
            rest = [p for p in seen if p != "None"]
            inner = rest[0] if len(rest) == 1 else f"Union[{', '.join(rest)}]"
            return f"Optional[{inner}]"
        return f"Union[{', '.join(seen)}]"

    def object_py(self, schema: Json, name_hint: str) -> str:
        props = schema.get("properties") if is_obj(schema.get("properties")) else {}
        ap = schema.get("additionalProperties")
        if not props:
            if is_obj(ap) and ap:
                return f"Dict[str, {self.py(ap, name_hint + 'Value')}]"
            return "Dict[str, Any]"
        return self.typed_dict(name_hint, schema)

    def typed_dict(self, name_hint: str, schema: Json, description: Optional[str] = None) -> str:
        """Emits one TypedDict (nested ones first) and returns its name."""
        name = self.unique_name(name_hint)
        props: Json = schema.get("properties") if is_obj(schema.get("properties")) else {}
        required = set(schema.get("required") or []) if isinstance(schema.get("required"), list) else set()
        fields: List[Tuple[str, str, str]] = []
        for key, sub in props.items():
            t = self.py(sub if is_obj(sub) else None, name + pascal(key))
            fields.append((key, f"Required[{t}]" if key in required else t, one_line(sub.get("description") if is_obj(sub) else "")))
        lines: List[str] = []
        desc = doc_lines([description or schema.get("description")])
        if all(ident_ok(k) for k, _, _ in fields):
            lines.append(f"class {name}(TypedDict, total=False):")
            if desc:
                lines.append(f'    """{desc[0]}"""')
            for key, t, d in fields:
                lines.append(f"    {key}: {t}" + (f"  # {d[:160].rstrip()}" if d else ""))
            if not fields:
                lines.append("    pass")
        else:
            lines.append(f"{name} = TypedDict(")
            lines.append(f"    {name!r},")
            lines.append("    {")
            for key, t, d in fields:
                lines.append(f"        {key!r}: {t!r}," + (f"  # {d[:160].rstrip()}" if d else ""))
            lines.append("    },")
            lines.append("    total=False,")
            lines.append(")")
            if desc:
                lines.append(f'"""{desc[0]}"""')
        self.type_blocks.append("\n".join(lines))
        return name

    # ── operations ──
    def operations(self) -> Tuple[List[Json], int]:
        ops: List[Json] = []
        hidden = 0
        for path, raw_item in self.spec["paths"].items():
            shared = [self.resolve_param(p) for p in (raw_item.get("parameters") or [])]
            for m in METHODS:
                op = raw_item.get(m)
                if not is_obj(op) or not isinstance(op.get("operationId"), str):
                    continue
                if is_hidden(op):
                    hidden += 1
                    continue
                own = [self.resolve_param(p) for p in (op.get("parameters") or [])]
                all_params = [s for s in shared if not any(o.get("name") == s.get("name") and o.get("in") == s.get("in") for o in own)] + own
                idempotent = any(x.get("in") == "header" and re.match(r"^idempotency-key$", str(x.get("name")), re.I) for x in all_params) or op["operationId"] in IDEMPOTENT_EXTRA
                params = [x for x in all_params if x.get("in") != "cookie" and not (x.get("in") == "header" and re.match(r"^idempotency-key$", str(x.get("name")), re.I))]
                ops.append(self.build_op(op, m.upper(), path, params, idempotent))
        ids = [o["id"] for o in ops]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise RuntimeError(f"duplicate operationIds: {', '.join(dupes)}")
        ops.sort(key=lambda o: o["id"])
        return ops, hidden

    def build_op(self, op: Json, method: str, path: str, params: List[Json], idempotent: bool) -> Json:
        oid = op["operationId"]
        claimed: Set[str] = set()
        defs: List[Json] = []
        fields: List[Tuple[str, str, bool, str]] = []  # key, type, required, doc
        input_required = False

        def claim(name: str, where: str) -> str:
            if name not in claimed:
                claimed.add(name)
                return name
            alt = f"{where}{name[:1].upper()}{name[1:]}"
            if alt in claimed:
                raise RuntimeError(f"{oid}: input {name} collides twice ({where})")
            claimed.add(alt)
            return alt

        def add_param(prm: Json) -> None:
            nonlocal input_required
            where = str(prm.get("in"))
            key = claim(header_input_key(prm["name"]) if where == "header" else prm["name"], where)
            req = where == "path" or prm.get("required") is True
            if req:
                input_required = True
            d = doc_lines([
                f'The {where} {"header" if where == "header" else "parameter"} "{prm["name"]}".' if key != prm["name"] else None,
                prm.get("description"),
                "Partner-backend attestation header; not an MCP tool input." if prm.get("x-mcp") is False and where == "header" else None,
            ])
            t = self.py(prm.get("schema") or {"type": "string"}, pascal(oid) + "Input" + pascal(key))
            fields.append((key, t, req, " ".join(d)))
            defn: Json = {"key": key, "name": prm["name"], "in": where}
            if req:
                defn["required"] = True
            defs.append(defn)

        for prm in [x for x in params if x.get("in") != "header"]:
            add_param(prm)
        body: Optional[Json] = None
        rb = op.get("requestBody") if is_obj(op.get("requestBody")) else None
        if rb:
            content = rb.get("content") or {}
            content_type = next(iter(content), "application/json")
            schema = (content.get(content_type) or {}).get("schema")
            body_props: Json = schema.get("properties") if is_obj(schema) and is_obj(schema.get("properties")) else {}
            body_required = rb.get("required") is not False
            if content_type == "application/json" and body_props:
                keys: Dict[str, str] = {}
                required_keys: List[str] = []
                req_set = set(schema.get("required") or []) if isinstance(schema.get("required"), list) else set()
                for name, sub in body_props.items():
                    key = claim(name, "body")
                    keys[key] = name
                    req = body_required and name in req_set
                    if req:
                        input_required = True
                        required_keys.append(key)
                    d = doc_lines([f'The body field "{name}".' if key != name else None, sub.get("description") if is_obj(sub) else None])
                    fields.append((key, self.py(sub if is_obj(sub) else None, pascal(oid) + "Input" + pascal(key)), req, " ".join(d)))
                ap = schema.get("additionalProperties")
                open_ = ap is True or (is_obj(ap) and not ap)
                body = {"kind": "fields", "keys": keys, "contentType": content_type}
                if open_:
                    body["open"] = True
                if required_keys:
                    body["requiredKeys"] = required_keys
            else:
                key = claim(op["x-mcp-body-input"] if isinstance(op.get("x-mcp-body-input"), str) else "body", "request")
                if body_required:
                    input_required = True
                d = doc_lines([f"The whole request body ({content_type}).", schema.get("description") if is_obj(schema) else None])
                t = self.py(schema, pascal(oid) + "Input" + pascal(key)) if content_type == "application/json" else "Union[Dict[str, Any], str]"
                fields.append((key, t, body_required, " ".join(d)))
                body = {"kind": "whole", "key": key, "required": body_required, "contentType": content_type}
        for prm in [x for x in params if x.get("in") == "header"]:
            add_param(prm)
        responses = op.get("responses") if is_obj(op.get("responses")) else {}
        ok_codes = sorted(c for c in responses if re.match(r"^2(\d\d|XX)$", c, re.I))
        out_schema = None
        for c in ok_codes:
            sc = ((responses[c].get("content") or {}).get("application/json") or {}).get("schema") if is_obj(responses[c]) else None
            if is_obj(sc):
                out_schema = sc
                break
        return {
            "id": oid, "method": method, "path": path, "tag": (op.get("tags") or ["Untagged"])[0], "summary": op.get("summary"),
            "description": op.get("description"), "params": defs, "body": body, "fields": fields, "outSchema": out_schema,
            "inputRequired": input_required, "deprecated": op.get("deprecated") is True, "idempotent": idempotent,
            "open": bool(body and body.get("open")),
        }

    # ── emit ──
    def emit(self) -> Dict[str, str]:
        ops, hidden = self.operations()
        header = f"# GENERATED by scripts/generate_platform.py from node/spec/{self.spec_file} - do not edit.\n# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)\n"
        spec_version = re.match(r"^openapi-v(.+)\.json$", self.spec_file)
        version = spec_version.group(1) if spec_version else str(self.spec.get("info", {}).get("version", ""))

        # types.py: component schemas + one Input/Output TypedDict per operation (nested objects as their own TypedDicts).
        for name, schema in self.spec.get("components", {}).get("schemas", {}).items():
            py_name = self.component_names[name]
            self.type_names.discard(py_name)
            if is_obj(schema) and is_obj(schema.get("properties")):
                self.typed_dict(py_name, schema)
            else:
                self.type_names.add(py_name)
                self.type_blocks.append(f"{py_name} = {self.py(schema, py_name)}" + (f'\n"""{doc_lines([schema.get("description")])[0]}"""' if doc_lines([schema.get("description")]) else ""))
        op_types: Dict[str, Tuple[str, str]] = {}
        for o in ops:
            in_name = self.unique_name(pascal(o["id"]) + "Input")
            lines = []
            if all(ident_ok(k) for k, _, _, _ in o["fields"]):
                lines.append(f"class {in_name}(TypedDict, total=False):")
                lines.append(f'    """Input of {o["id"]} ({o["method"]} {o["path"]})."""')
                for key, t, req, d in o["fields"]:
                    lines.append(f"    {key}: {f'Required[{t}]' if req else t}" + (f"  # {d[:160].rstrip()}" if d else ""))
                if o["open"]:
                    lines.append("    # The spec allows fields it does not list; they are sent as given.")
            else:
                lines.append(f"{in_name} = TypedDict(")
                lines.append(f"    {in_name!r},")
                lines.append("    {")
                for key, t, req, d in o["fields"]:
                    lines.append(f"        {key!r}: {(f'Required[{t}]' if req else t)!r}," + (f"  # {d[:160].rstrip()}" if d else ""))
                lines.append("    },")
                lines.append("    total=False,")
                lines.append(")")
                lines.append(f'"""Input of {o["id"]} ({o["method"]} {o["path"]})."""')
            self.type_blocks.append("\n".join(lines))
            out_name_hint = pascal(o["id"]) + "Output"
            if is_obj(o["outSchema"]) and is_obj(o["outSchema"].get("properties")):
                out_name = self.typed_dict(out_name_hint, o["outSchema"], f"Output of {o['id']}.")
            elif o["outSchema"] is not None:
                out_name = self.unique_name(out_name_hint)
                self.type_blocks.append(f"{out_name} = {self.py(o['outSchema'], out_name)}\n\"\"\"Output of {o['id']}.\"\"\"")
            else:
                out_name = "JsonObject"
            op_types[o["id"]] = (in_name, out_name)

        types_out = [
            header,
            '"""One Input and one Output type per operation, named after the operationId, plus the spec\'s named schemas."""',
            "",
            "from __future__ import annotations",
            "",
            "from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, TypedDict, Union",
            "",
            "if TYPE_CHECKING:",
            "    from typing_extensions import Required",
            "",
            "#: A JSON answer the spec does not describe in detail; shaped exactly as the REST API returns it (usually {\"data\": ...}).",
            "JsonObject = Dict[str, Any]",
            "",
            "__all__ = [",
            *[f"    {n!r}," for n in sorted(["JsonObject", *self.type_names])],
            "]",
            "",
            "",
            *[b + "\n\n" for b in self.type_blocks],
        ]
        types_src = "\n".join(types_out).rstrip() + "\n"

        # ops.py: the wire manifest the transport runs on.
        ops_out = [
            header,
            '"""The wire manifest: one OpDef per operation (no compatibility promise; see fastn.platform.unstable)."""',
            "",
            "from __future__ import annotations",
            "",
            "from typing import Dict",
            "",
            "from .._transport import BodyDef, OpDef, ParamDef",
            "",
            f"SPEC_VERSION = {version!r}",
            f"SPEC_FILE = {self.spec_file!r}",
            "",
            "OPS: Dict[str, OpDef] = {",
        ]
        for o in ops:
            params = ", ".join(
                f"ParamDef(key={p['key']!r}, name={p['name']!r}, location={p['in']!r}" + (", required=True" if p.get("required") else "") + ")"
                for p in o["params"]
            )
            body = ""
            if o["body"]:
                b = o["body"]
                if b["kind"] == "fields":
                    body = f", body=BodyDef(kind='fields', keys={b['keys']!r}, content_type={b['contentType']!r}" + (", open=True" if b.get("open") else "") + (f", required_keys={tuple(b['requiredKeys'])!r}" if b.get("requiredKeys") else "") + ")"
                else:
                    body = f", body=BodyDef(kind='whole', key={b['key']!r}, required={b['required']!r}, content_type={b['contentType']!r})"
            idem = ", idempotent=True" if o["idempotent"] else ""
            ops_out.append(f"    {o['id']!r}: OpDef(id={o['id']!r}, method={o['method']!r}, path={o['path']!r}, params=({params}{',' if len(o['params']) == 1 else ''}){body}{idem}),")
        ops_out.append("}")
        ops_src = "\n".join(ops_out) + "\n"

        # api.py: one class per tag, one method per operation (snake_case, with the operationId as an alias).
        by_tag: Dict[str, List[Json]] = {}
        for o in ops:
            by_tag.setdefault(o["tag"], []).append(o)
        groups: List[Tuple[str, str, str, str, int]] = []  # snake prop, camel prop, class, tag, count
        api_out = [
            header,
            '"""Every API area, keyed by its OpenAPI tag: one class per tag, one method per operation."""',
            "",
            "from __future__ import annotations",
            "",
            "from typing import TYPE_CHECKING, Any, Mapping, Optional, cast",
            "",
            "from .ops import OPS",
            "",
            "if TYPE_CHECKING:",
            "    from typing_extensions import Unpack",
            "",
            "    from .._transport import RequestOptions, Transport",
            "    from . import types as T",
            "",
            "",
        ]
        used_methods: Dict[str, str] = {}
        for tag in sorted(by_tag):
            prop = tag_name(tag)
            sprop = snake(prop)
            cls = f"{pascal(prop)}Api"
            if sprop in RESERVED or prop in RESERVED:
                raise RuntimeError(f'tag "{tag}" would become client member "{sprop}", which FastnClient reserves; rename the tag in the spec')
            groups.append((sprop, prop, cls, tag, len(by_tag[tag])))
            tag_desc = next((t.get("description") for t in (self.spec.get("tags") or []) if t.get("name") == tag), None)
            api_out.append(f"class {cls}:")
            api_out.append(f'    """{tag}: {one_line(tag_desc)}"""')
            api_out.append("")
            api_out.append("    def __init__(self, transport: Transport) -> None:")
            api_out.append("        self._t = transport")
            for o in by_tag[tag]:
                name = snake(o["id"])
                if name in used_methods and used_methods[name] != o["id"]:
                    raise RuntimeError(f"{o['id']} and {used_methods[name]} both become {name}()")
                used_methods[name] = o["id"]
                in_t, out_t = op_types[o["id"]]
                in_ann = f"T.{in_t}"
                arg = f"input: {in_ann}" if o["inputRequired"] else f"input: Optional[{in_ann}] = None"
                ret = f"T.{out_t}"
                lines = doc_lines([
                    o["summary"], o["description"], f"{o['method']} {o['path']}",
                    "Honours Idempotency-Key: pass idempotency_key= and a retry after a lost answer cannot act twice." if o["idempotent"] else None,
                    "Deprecated." if o["deprecated"] else None,
                ])
                api_out.append("")
                api_out.append(f"    def {name}(self, {arg}, **opts: Unpack[RequestOptions]) -> {ret}:")
                if lines:
                    api_out.append('        """' + lines[0] + ("" if len(lines) == 1 else "\n\n" + "\n".join(f"        {ln}" for ln in lines[1:])) + '\n        """')
                api_out.append(f"        return cast({ret!r}, self._t.call(OPS[{o['id']!r}], input or {{}}, cast(Mapping[str, Any], opts)))")
                if o["id"] != name:
                    api_out.append("")
                    api_out.append(f"    {o['id']} = {name}")
            api_out.append("")
            api_out.append("")
        api_out.append("class FastnApis:")
        api_out.append('    """Every API area, keyed by its OpenAPI tag (snake_case, with the Node SDK\'s camelCase name as an alias)."""')
        api_out.append("")
        api_out.append("    def __init__(self, transport: Transport) -> None:")
        for sprop, prop, cls, tag, count in groups:
            api_out.append(f"        #: {tag} ({count} operations)")
            api_out.append(f"        self.{sprop} = {cls}(transport)")
            if prop != sprop:
                api_out.append(f"        self.{prop} = self.{sprop}")
        api_out.append("")
        api_out.append("")
        api_out.append("#: The client members, snake_case (the camelCase alias is listed after it when it differs).")
        api_out.append("API_GROUPS = (")
        for sprop, prop, _cls, _tag, _count in groups:
            api_out.append(f"    ({sprop!r}, {prop!r}),")
        api_out.append(")")
        api_out.append("")
        api_out.append("")
        api_out.append("def build_apis(transport: Transport) -> FastnApis:")
        api_out.append("    return FastnApis(transport)")
        api_src = "\n".join(api_out) + "\n"

        init_src = header + '"""Generated from the fastn OpenAPI spec; see scripts/generate_platform.py."""\n'
        self.summary = f"generated {len(ops)} operations in {len(groups)} areas from {self.spec_file} ({hidden} platform-admin/backend-only routes left out, {sum(1 for o in ops if op_types[o['id']][1] != 'JsonObject')} with typed output)"
        return {"ops.py": ops_src, "types.py": types_src, "api.py": api_src, "__init__.py": init_src}


def main(argv: List[str]) -> int:
    check_only = "--check" in argv
    spec_arg = next((a[len("--spec="):] for a in argv if a.startswith("--spec=")), None)
    if spec_arg:
        spec_path = os.path.abspath(spec_arg)
    else:
        files = sorted(f for f in os.listdir(SPEC_DIR) if re.match(r"^openapi-v.*\.json$", f))
        if not files:
            print(f"no openapi-v*.json in {SPEC_DIR}", file=sys.stderr)
            return 2
        spec_path = os.path.join(SPEC_DIR, files[-1])
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    gen = Generator(spec, os.path.basename(spec_path))
    files_out = gen.emit()
    changed: List[str] = []
    for name, src in files_out.items():
        target = os.path.join(OUT_DIR, name)
        current = None
        if os.path.exists(target):
            with open(target, encoding="utf-8") as f:
                current = f.read()
        if current != src:
            changed.append(name)
    if check_only:
        if changed:
            print(f"{', '.join(changed)} would change; run scripts/generate_platform.py")
            return 1
        print(f"up to date: {gen.summary}")
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, src in files_out.items():
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
            f.write(src)
    print(gen.summary + (f"; wrote {', '.join(changed)}" if changed else "; nothing changed"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
