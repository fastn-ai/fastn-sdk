"""Flow management namespace — generate, run, list, update, delete, get, schema."""

from __future__ import annotations

import json as _json
import re
import uuid as _uuid
from typing import Any, Dict, List, Optional, Set

from fastn._constants import (
    DEPLOY_FLOW_MUTATION,
    FLOW_BUILDER_SPACE_ID,
    FLOW_BUILDER_URL,
    FLOWS_API_URL,
    FLOW_RUN_API_URL,
    GET_FLOW_QUERY,
    LIST_FLOWS_QUERY,
)
from fastn._http import _api_call_sync, _api_call_async, _gql_call_sync, _gql_call_async
from fastn.exceptions import FlowNotFoundError


# ---------------------------------------------------------------------------
# Generic recursive tree walker
# ---------------------------------------------------------------------------

def _walk_tree(obj: Any, visitor) -> None:
    """Recursively walk any dict/list/str tree, calling *visitor* on every node."""
    visitor(obj)
    if isinstance(obj, dict):
        for value in obj.values():
            _walk_tree(value, visitor)
    elif isinstance(obj, list):
        for item in obj:
            _walk_tree(item, visitor)


# ---------------------------------------------------------------------------
# Input schema discovery — scan every string for input references
# ---------------------------------------------------------------------------

# Regex patterns for input references across languages:
_INPUT_PATTERNS = [
    # ── Jinja / template engines ──
    # {{input.name}}, {{input.user.name}}, {{ input.field_name }}
    re.compile(r"\{\{\s*input\.(\w+(?:\.\w+)*)\s*\}\}"),

    # ── JavaScript / TypeScript ──
    # params.data.input.fieldName or params.data.input.user.name
    re.compile(r"params\.data\.input\.(\w+(?:\.\w+)*)"),
    # params["data"]["input"]["fieldName"]["sub"] ...
    re.compile(r'params\[["\']data["\']\]\[["\']input["\']\]\[["\'](\w+)["\']\]'),

    # ── Python ──
    # input["fieldName"]["sub"] ...
    re.compile(r"(?<!\w)input\[['\"](\w+)['\"]\]"),
    # input.get("fieldName").get("sub") ...
    re.compile(r"(?<!\w)input\.get\(\s*['\"](\w+)['\"]\s*(?:,\s*[^)]*)?\)"),
    # data["input"]["fieldName"]["sub"] ...
    re.compile(r'data\[["\']input["\']\]\[["\'](\w+)["\']\]'),

    # ── Ruby ──
    # input[:fieldName][:sub] ...
    re.compile(r"(?<!\w)input\[:(\w+)\]"),
    # params[:data][:input][:fieldName][:sub] ...
    re.compile(r"params\[:data\]\[:input\]\[:(\w+)\]"),

    # ── PHP ──
    # $input['fieldName']['sub'] ...
    re.compile(r"\$input\[['\"](\w+)['\"]\]"),
    # $params['data']['input']['fieldName']['sub'] ...
    re.compile(r"\$params\[['\"]data['\"]\]\[['\"]input['\"]\]\[['\"](\w+)['\"]\]"),

    # ── Generic (any language) ──
    # input.fieldName.sub — dot access (JS, Python attr, Go, etc.)
    # Negative lookahead excludes function calls like input.toString()
    re.compile(r"(?<!\w)input\.(\w+(?:\.\w+)*)(?!\w*\()"),
]

# Continuation patterns for extending field paths after the initial match.
_BRACKET_CONT_RE = re.compile(r'\[[\'"](\w+)[\'"]\]')
_SYMBOL_CONT_RE = re.compile(r'\[:(\w+)\]')
_GET_CONT_RE = re.compile(r'\.get\(\s*[\'"](\w+)[\'"]\s*(?:,\s*[^)]*)?\)')


def _extend_field_path(text: str, pos: int, field: str) -> str:
    """Extend a field path by scanning for chained access after *pos*."""
    segments = field.split(".")

    while pos < len(text):
        m = _BRACKET_CONT_RE.match(text, pos)
        if m:
            segments.append(m.group(1))
            pos = m.end()
            continue
        m = _SYMBOL_CONT_RE.match(text, pos)
        if m:
            segments.append(m.group(1))
            pos = m.end()
            continue
        m = _GET_CONT_RE.match(text, pos)
        if m:
            segments.append(m.group(1))
            pos = m.end()
            continue
        break

    return ".".join(segments)


def _scan_string_for_inputs(text: str, found: Set[str]) -> None:
    """Scan a single string for input references and add field names to *found*."""
    for pattern in _INPUT_PATTERNS:
        for match in pattern.finditer(text):
            field = match.group(1)
            if not field:
                continue
            field = _extend_field_path(text, match.end(), field)
            if field:
                found.add(field)


def _build_nested_schema(fields: Set[str]) -> Dict[str, Any]:
    """Build a nested JSON Schema from a set of dot-path field names.

    Example::

        Input:  {"user.name", "user.email", "simple"}
        Output: {
            "type": "object",
            "properties": {
                "simple": {"type": "string"},
                "user": {"type": "object", "properties": {"name": …, "email": …}}
            },
            "required": ["simple", "user"]
        }
    """
    root: Dict[str, Any] = {}

    for field_path in sorted(fields):
        parts = field_path.split(".")
        current = root
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                if part not in current:
                    current[part] = {"type": "string"}
            else:
                if part not in current:
                    current[part] = {"type": "object", "properties": {}}
                elif "properties" not in current[part]:
                    current[part] = {"type": "object", "properties": {}}
                current = current[part]["properties"]

    return {
        "type": "object",
        "properties": root,
        "required": sorted(root.keys()),
    }


def _extract_flow_input_fields(flow_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract input field names by walking the entire flow response tree.

    Scans every string value anywhere in *flow_data* for input references
    like ``{{input.name}}``, ``params.data.input.x``, etc.  Does not
    assume a rigid structure — works regardless of how the API response
    is shaped.
    """
    found: Set[str] = set()

    def _visitor(node: Any) -> None:
        if isinstance(node, str):
            _scan_string_for_inputs(node, found)

    _walk_tree(flow_data, _visitor)

    return {
        "fields": sorted(found),
        "schema": _build_nested_schema(found),
    }


# ---------------------------------------------------------------------------
# Output schema discovery — find hasResponse nodes and extract output fields
# ---------------------------------------------------------------------------

# Type mapping from whatever targetType / type strings we encounter.
_TYPE_MAP = {
    "string": "string",
    "number": "number",
    "integer": "integer",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
    "float": "number",
    "int": "integer",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}

# Regex for extracting JSON-like keys from code/templates.
# Matches "someKey": (with optional whitespace)
_JSON_KEY_RE = re.compile(r'"(\w+)"\s*:')
# Matches JS shorthand return { key1, key2, key3 }
_JS_RETURN_RE = re.compile(r'return\s*\{([^}]+)\}')


def _normalize_type(raw: Any) -> str:
    """Map a type string to a JSON Schema type, defaulting to 'string'."""
    if not isinstance(raw, str):
        return "string"
    return _TYPE_MAP.get(raw.lower(), "string")


def _extract_schema_from_target(target: Any, target_type: str = "") -> Dict[str, Any]:
    """Recursively build a JSON Schema from a ``target`` structure.

    The *target* can be:
    - a dict whose keys are output field names (each value describes the field)
    - a string (leaf value, not fields)
    - a list (array items)
    """
    if not isinstance(target, dict):
        return {"type": _normalize_type(target_type) if target_type else "string"}

    # Check if this dict looks like field definitions (keys are field names)
    # vs. a single field descriptor (has "targetType" / "actionType" etc.)
    if "targetType" in target or "actionType" in target:
        # This is a single field descriptor, not a fields map
        inner_type = _normalize_type(target.get("targetType", ""))
        if inner_type == "object":
            inner_target = target.get("target")
            if isinstance(inner_target, dict) and "targetType" not in inner_target:
                # inner_target's keys are child field names
                return _extract_schema_from_fields_map(inner_target)
        return {"type": inner_type}

    # Keys are field names
    return _extract_schema_from_fields_map(target)


def _extract_schema_from_fields_map(fields_map: Dict[str, Any]) -> Dict[str, Any]:
    """Build JSON Schema from a dict whose keys are field names."""
    properties: Dict[str, Any] = {}
    for key, val in fields_map.items():
        if not isinstance(key, str) or not key:
            continue
        if isinstance(val, dict):
            child_type = _normalize_type(val.get("targetType", val.get("type", "")))
            child_target = val.get("target")
            if child_type == "object" and isinstance(child_target, dict):
                # Recurse — child_target's keys might be nested field names
                if "targetType" not in child_target:
                    properties[key] = _extract_schema_from_fields_map(child_target)
                else:
                    properties[key] = _extract_schema_from_target(child_target, child_type)
            elif child_type == "array":
                properties[key] = {"type": "array"}
            else:
                properties[key] = {"type": child_type or "string"}
        else:
            properties[key] = {"type": "string"}

    if not properties:
        return {"type": "object", "properties": {}}

    return {
        "type": "object",
        "properties": properties,
        "required": sorted(properties.keys()),
    }


def _parse_uicode_for_output(raw: str) -> Optional[Dict[str, Any]]:
    """Try to parse a uiCode string and extract output schema from it.

    Looks for ``target`` dicts and ``targetType`` values anywhere in
    the parsed structure.
    """
    try:
        parsed = _json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return None

    if not isinstance(parsed, dict):
        return None

    # Look for a "target" dict — that's where field names live
    target = parsed.get("target")
    target_type = parsed.get("targetType", "")

    if isinstance(target, dict) and target:
        schema = _extract_schema_from_target(target, target_type)
        if schema.get("properties"):
            return schema

    return None


def _parse_code_for_output(code: str) -> Optional[Dict[str, Any]]:
    """Try to extract output field names from code strings (Jinja/JS/JSON).

    Uses pattern matching to find JSON keys or JS return statements.
    """
    if not code or not isinstance(code, str):
        return None

    # Strategy 1: Strip Jinja tags and try to find JSON keys
    cleaned = re.sub(r'\{%.*?%\}', '""', code)
    cleaned = re.sub(r'\{\{.*?\}\}', '""', cleaned)
    cleaned = cleaned.strip()

    fields: Set[str] = set()

    # Try to parse as JSON directly
    try:
        parsed = _json.loads(cleaned)
        if isinstance(parsed, dict):
            fields.update(parsed.keys())
    except (ValueError, TypeError):
        pass

    # Strategy 2: Regex for "key": patterns
    if not fields:
        for m in _JSON_KEY_RE.finditer(cleaned):
            fields.add(m.group(1))

    # Strategy 3: JS return { key1, key2, ... }
    if not fields:
        m = _JS_RETURN_RE.search(code)
        if m:
            body = m.group(1)
            for token in re.split(r'[,\s]+', body):
                token = token.strip().split(":")[0].strip()
                if re.match(r'^\w+$', token):
                    fields.add(token)

    if not fields:
        return None

    properties = {f: {"type": "string"} for f in sorted(fields)}
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(properties.keys()),
    }


def _extract_output_fields(flow_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract output schema by finding nodes with ``hasResponse: true``.

    Walks the entire *flow_data* tree.  When a dict contains
    ``hasResponse: true``, it examines the whole node for output signals:
    - ``uiCode`` JSON with ``target`` keys and ``targetType`` values
    - ``code`` strings with JSON key patterns or return statements
    - Any ``outputSchema`` dict attached to the node

    Returns the same shape as ``_extract_flow_input_fields``:
    ``{"fields": [...], "schema": {...}}``.
    """
    collected_schemas: List[Dict[str, Any]] = []

    def _visitor(node: Any) -> None:
        if not isinstance(node, dict):
            return
        # Signal: hasResponse is truthy
        if not node.get("hasResponse"):
            return

        # Try every signal in the node to extract output schema
        # 1. Direct outputSchema on the node
        out_schema = node.get("outputSchema")
        if isinstance(out_schema, dict) and out_schema.get("properties"):
            collected_schemas.append(out_schema)
            return

        # 2. Parse uiCode for structured target/targetType
        ui_code = node.get("uiCode")
        if ui_code:
            schema = _parse_uicode_for_output(ui_code)
            if schema and schema.get("properties"):
                collected_schemas.append(schema)
                return

        # 3. Parse code for JSON keys / return patterns
        code = node.get("code")
        if code:
            schema = _parse_code_for_output(code)
            if schema and schema.get("properties"):
                collected_schemas.append(schema)

    _walk_tree(flow_data, _visitor)

    # Merge all discovered schemas (multiple response nodes possible)
    if not collected_schemas:
        return {
            "fields": [],
            "schema": {"type": "object", "properties": {}, "required": []},
        }

    merged_props: Dict[str, Any] = {}
    for schema in collected_schemas:
        merged_props.update(schema.get("properties", {}))

    fields = sorted(merged_props.keys())
    return {
        "fields": fields,
        "schema": {
            "type": "object",
            "properties": merged_props,
            "required": sorted(merged_props.keys()),
        },
    }


# ---------------------------------------------------------------------------
# Flow listing helpers
# ---------------------------------------------------------------------------

def _build_flows_query_variables(client: Any) -> Dict[str, Any]:
    """Build the GraphQL variables for the ``apis`` query."""
    workspace_id = client._config.resolve_project_id()
    return {
        "input": {
            "clientId": workspace_id,
            "first": 500,
            "after": None,
            "query": '{"input":{"limit":500,"offset":0,"sort":"desc","query":"","filter":{}}}',
        }
    }


def _parse_flows_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse the ``apis`` GraphQL response into a list of flow dicts."""
    result = data.get("apis") or {}
    edges = result.get("edges") or []

    flows: List[Dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        node = edge.get("node") or {}
        if not isinstance(node, dict):
            continue

        flow: Dict[str, Any] = {
            "flow_id": node.get("id", ""),
            "name": node.get("name", ""),
            "description": node.get("description", ""),
            "status": node.get("status", ""),
            "version": node.get("version", ""),
            "updatedAt": node.get("updatedAt", ""),
            "deployedAt": node.get("deployedAt", ""),
        }

        meta = node.get("metaData") or {}
        if meta:
            flow["flowType"] = meta.get("flowType", "")
            flow["architecture"] = meta.get("architecture", "")
            flow["isAsync"] = meta.get("isAsync", False)

        flows.append(flow)

    return flows


def _fetch_flows_sync(client: Any) -> List[Dict[str, Any]]:
    """Fetch all flows from the workspace using the ``apis`` GraphQL query (sync)."""
    variables = _build_flows_query_variables(client)
    data = _gql_call_sync(client, LIST_FLOWS_QUERY, variables)
    return _parse_flows_response(data)


async def _fetch_flows_async(client: Any) -> List[Dict[str, Any]]:
    """Fetch all flows from the workspace using the ``apis`` GraphQL query (async)."""
    variables = _build_flows_query_variables(client)
    data = await _gql_call_async(client, LIST_FLOWS_QUERY, variables)
    return _parse_flows_response(data)


# ---------------------------------------------------------------------------
# Flow get helpers
# ---------------------------------------------------------------------------

def _build_get_flow_variables(client: Any, flow_name: str) -> Dict[str, Any]:
    """Build the GraphQL variables for the ``api`` (single flow) query."""
    workspace_id = client._config.resolve_project_id()
    return {
        "input": {
            "clientId": workspace_id,
            "id": flow_name,
        }
    }


def _build_flow_run_headers(
    stage: Optional[str] = None,
) -> Dict[str, str]:
    """Build extra headers required for the v1 flow run endpoint."""
    headers: Dict[str, str] = {
        "x-fastn-custom-auth": "true",
    }
    if stage:
        headers["stage"] = stage.upper()
    return headers


# ---------------------------------------------------------------------------
# Name -> ID resolution helpers
# ---------------------------------------------------------------------------

def _resolve_flow_id_sync(client: Any, name_or_id: str) -> str:
    """Resolve a flow name to its base flow_id by listing flows.

    Raises FlowNotFoundError if no match is found.
    """
    flows = _fetch_flows_sync(client)
    for flow in flows:
        if flow.get("name") == name_or_id:
            return flow["flow_id"]
    raise FlowNotFoundError(name_or_id)


async def _resolve_flow_id_async(client: Any, name_or_id: str) -> str:
    """Resolve a flow name to its base flow_id by listing flows (async).

    Raises FlowNotFoundError if no match is found.
    """
    flows = await _fetch_flows_async(client)
    for flow in flows:
        if flow.get("name") == name_or_id:
            return flow["flow_id"]
    raise FlowNotFoundError(name_or_id)


class _FlowsSync:
    """Flow management namespace (sync): ``fastn.flows.*``

    Provides operations for Fastn integration flows.

    Usage::

        fastn = FastnClient(api_key="...", project_id="...")

        # List all flows
        flows = fastn.flows.list()

        # Trigger a flow run
        result = fastn.flows.run("testflow", input_data={"name": "hello"})

        # Get flow definition
        flow = fastn.flows.get("testflow")

        # Discover input schema
        schema = fastn.flows.schema("testflow")

        # Check run status
        status = fastn.flows.get_run(run_id="run_xyz")
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def generate(
        self,
        prompt: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate an integration flow via the flow builder agent.

        Sends a chat message to the flow builder agent which generates the
        flow definition through a conversational interface.

        Args:
            prompt: Plain English description or follow-up message.
            session_id: Session ID for multi-turn conversations.  If not
                provided, a new UUID is generated.

        Returns:
            The agent response dict.
        """
        sid = session_id or str(_uuid.uuid4())
        project_id = self._client._config.resolve_project_id()
        payload: Dict[str, Any] = {
            "input": {
                "chatInput": prompt,
                "sessionID": sid,
                "projectId": project_id,
            }
        }
        extra = {
            "x-fastn-custom-auth": "true",
            "x-fastn-space-id": FLOW_BUILDER_SPACE_ID,
            "x-fastn-space-tenantid": project_id,
            "stage": "DRAFT",
        }
        return _api_call_sync(self._client, "POST", FLOW_BUILDER_URL, payload, extra_headers=extra)

    # Backward-compatible alias
    create = generate

    def delete(self, flow_id: str) -> Dict[str, Any]:
        """Delete a flow.

        Accepts either the base flow ID (e.g. ``"testflow"``) or a versioned
        name (e.g. ``"testflow_v1"``).  If the given identifier is not found
        directly, the method lists all flows and resolves the name to the
        correct base flow ID before retrying.

        Args:
            flow_id: The base flow ID or versioned flow name.

        Returns:
            Confirmation dict.

        Raises:
            FlowNotFoundError: If the flow cannot be found by ID or name.
        """
        try:
            return _api_call_sync(
                self._client, "POST", f"{FLOWS_API_URL}/delete", {"flow_id": flow_id}
            )
        except FlowNotFoundError:
            # The given string may be a versioned name -- resolve to base ID.
            resolved_id = _resolve_flow_id_sync(self._client, flow_id)
            return _api_call_sync(
                self._client, "POST", f"{FLOWS_API_URL}/delete", {"flow_id": resolved_id}
            )

    def run(
        self,
        flow_name: str,
        input_data: Optional[Dict[str, Any]] = None,
        stage: Optional[str] = None,
    ) -> Any:
        """Run a flow via the v1 REST API.

        Args:
            flow_name: The flow name (used as the URL path segment).
            input_data: Input data to pass to the flow.
            stage: Deployment stage — ``"DRAFT"`` or ``"LIVE"``.

        Returns:
            The flow execution response (shape depends on the flow).
        """
        url = f"{FLOW_RUN_API_URL}/{flow_name}"
        payload: Dict[str, Any] = {"input": input_data or {}}
        extra = _build_flow_run_headers(stage)
        return _api_call_sync(self._client, "POST", url, payload, extra_headers=extra)

    def deploy(
        self,
        flow_name: str,
        stage: str = "LIVE",
        comment: str = "",
    ) -> Dict[str, Any]:
        """Deploy a flow to a stage.

        Uses the ``deployApiToStage`` GraphQL mutation.

        Args:
            flow_name: The flow name (ID).
            stage: Target stage — ``"DRAFT"`` or ``"LIVE"``.
            comment: Optional deployment comment.

        Returns:
            The mutation response with ``id`` and ``__typename``.
        """
        workspace_id = self._client._config.resolve_project_id()
        variables = {
            "input": {
                "clientId": workspace_id,
                "env": stage.upper(),
                "id": flow_name,
                "comment": comment,
            }
        }
        data = _gql_call_sync(self._client, DEPLOY_FLOW_MUTATION, variables)
        return data.get("deployApiToStage", data)

    def get(self, flow_name: str) -> Dict[str, Any]:
        """Fetch the full definition of a flow.

        Uses the ``api`` GraphQL query to retrieve the flow including its
        resolver steps.

        Args:
            flow_name: The flow name.

        Returns:
            The full flow definition dict.
        """
        variables = _build_get_flow_variables(self._client, flow_name)
        data = _gql_call_sync(self._client, GET_FLOW_QUERY, variables)
        flow = data.get("api")
        if not flow:
            raise FlowNotFoundError(flow_name)
        return flow

    def schema(self, flow_name: str) -> Dict[str, Any]:
        """Discover the input schema of a flow by parsing its steps.

        Scans all steps recursively for input references like
        ``{{input.name}}``, ``params.data.input.name``, etc.

        Args:
            flow_name: The flow name.

        Returns:
            A dict with ``fields`` (list of field names) and ``schema``
            (JSON-Schema-style object).
        """
        flow_data = self.get(flow_name)
        return _extract_flow_input_fields(flow_data)

    def get_run(self, run_id: str) -> Dict[str, Any]:
        """Get the status of a flow run.

        Args:
            run_id: The ID of the run to check.

        Returns:
            A dict with ``run_id``, ``status``, ``steps``, ``started_at``,
            ``completed_at``, and ``result`` or ``error``.

        Raises:
            RunNotFoundError: If the run_id does not exist.
        """
        return _api_call_sync(
            self._client, "POST", f"{FLOWS_API_URL}/get_run", {"run_id": run_id}
        )

    def list(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List flows in the project.

        Fetches flows from the workspace via the ``apis`` GraphQL query.

        Args:
            status: Optional filter -- ``"DEPLOYED"``, ``"DRAFT"``, etc.
                or ``None`` for all.  Case-insensitive.

        Returns:
            A list of flow summary dicts with ``flow_id``, ``name``,
            ``description``, ``status``, ``version``, ``updatedAt``,
            and ``deployedAt``.
        """
        flows = _fetch_flows_sync(self._client)

        if status:
            wanted = status.upper()
            flows = [f for f in flows if str(f.get("status") or "").upper() == wanted]

        return flows

    def update(
        self,
        flow_id: str,
        prompt: Optional[str] = None,
        schedule: Optional[str] = None,
        enabled: Optional[bool] = None,
        answers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update an existing flow.

        Args:
            flow_id: The ID of the flow to update.
            prompt: New prompt to regenerate the flow definition.
            schedule: New cron schedule (e.g. ``"0 9 * * MON-FRI"``).
            enabled: Enable or disable the flow.
            answers: Answers to questions from a regeneration.

        Returns:
            Updated flow dict.

        Raises:
            FlowNotFoundError: If the flow_id does not exist.
        """
        payload: Dict[str, Any] = {"flow_id": flow_id}
        if prompt is not None:
            payload["prompt"] = prompt
        if schedule is not None:
            payload["schedule"] = schedule
        if enabled is not None:
            payload["enabled"] = enabled
        if answers is not None:
            payload["answers"] = answers
        return _api_call_sync(
            self._client, "POST", f"{FLOWS_API_URL}/update", payload
        )


class _FlowsAsync:
    """Flow management namespace (async): ``fastn.flows.*``

    Async equivalent of :class:`_FlowsSync`. See its docstring for full
    method documentation.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    async def generate(
        self,
        prompt: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate an integration flow via the flow builder agent (async)."""
        sid = session_id or str(_uuid.uuid4())
        project_id = self._client._config.resolve_project_id()
        payload: Dict[str, Any] = {
            "input": {
                "chatInput": prompt,
                "sessionID": sid,
                "projectId": project_id,
            }
        }
        extra = {
            "x-fastn-custom-auth": "true",
            "x-fastn-space-id": FLOW_BUILDER_SPACE_ID,
            "x-fastn-space-tenantid": project_id,
            "stage": "DRAFT",
        }
        return await _api_call_async(
            self._client, "POST", FLOW_BUILDER_URL, payload, extra_headers=extra
        )

    # Backward-compatible alias
    create = generate

    async def delete(self, flow_id: str) -> Dict[str, Any]:
        """Delete a flow (async).

        Accepts either the base flow ID or a versioned name.  Resolves
        automatically if the initial ID is not found.
        """
        try:
            return await _api_call_async(
                self._client, "POST", f"{FLOWS_API_URL}/delete", {"flow_id": flow_id}
            )
        except FlowNotFoundError:
            resolved_id = await _resolve_flow_id_async(self._client, flow_id)
            return await _api_call_async(
                self._client, "POST", f"{FLOWS_API_URL}/delete", {"flow_id": resolved_id}
            )

    async def run(
        self,
        flow_name: str,
        input_data: Optional[Dict[str, Any]] = None,
        stage: Optional[str] = None,
    ) -> Any:
        """Run a flow via the v1 REST API (async)."""
        url = f"{FLOW_RUN_API_URL}/{flow_name}"
        payload: Dict[str, Any] = {"input": input_data or {}}
        extra = _build_flow_run_headers(stage)
        return await _api_call_async(
            self._client, "POST", url, payload, extra_headers=extra
        )

    async def deploy(
        self,
        flow_name: str,
        stage: str = "LIVE",
        comment: str = "",
    ) -> Dict[str, Any]:
        """Deploy a flow to a stage (async)."""
        workspace_id = self._client._config.resolve_project_id()
        variables = {
            "input": {
                "clientId": workspace_id,
                "env": stage.upper(),
                "id": flow_name,
                "comment": comment,
            }
        }
        data = await _gql_call_async(self._client, DEPLOY_FLOW_MUTATION, variables)
        return data.get("deployApiToStage", data)

    async def get(self, flow_name: str) -> Dict[str, Any]:
        """Fetch the full definition of a flow (async)."""
        variables = _build_get_flow_variables(self._client, flow_name)
        data = await _gql_call_async(self._client, GET_FLOW_QUERY, variables)
        flow = data.get("api")
        if not flow:
            raise FlowNotFoundError(flow_name)
        return flow

    async def schema(self, flow_name: str) -> Dict[str, Any]:
        """Discover the input schema of a flow (async)."""
        flow_data = await self.get(flow_name)
        return _extract_flow_input_fields(flow_data)

    async def get_run(self, run_id: str) -> Dict[str, Any]:
        """Get the status of a flow run (async)."""
        return await _api_call_async(
            self._client, "POST", f"{FLOWS_API_URL}/get_run", {"run_id": run_id}
        )

    async def list(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List flows in the project (async).

        Fetches flows from the workspace via the ``apis`` GraphQL query.
        """
        flows = await _fetch_flows_async(self._client)

        if status:
            wanted = status.upper()
            flows = [f for f in flows if str(f.get("status") or "").upper() == wanted]

        return flows

    async def update(
        self,
        flow_id: str,
        prompt: Optional[str] = None,
        schedule: Optional[str] = None,
        enabled: Optional[bool] = None,
        answers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update an existing flow (async)."""
        payload: Dict[str, Any] = {"flow_id": flow_id}
        if prompt is not None:
            payload["prompt"] = prompt
        if schedule is not None:
            payload["schedule"] = schedule
        if enabled is not None:
            payload["enabled"] = enabled
        if answers is not None:
            payload["answers"] = answers
        return await _api_call_async(
            self._client, "POST", f"{FLOWS_API_URL}/update", payload
        )
