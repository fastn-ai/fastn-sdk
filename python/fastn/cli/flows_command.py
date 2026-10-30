"""CLI commands: fastn flow - manage integration flows."""

from __future__ import annotations

import json
import uuid

import click

from fastn.cli import cli, OrderedGroup, GRAPHQL_URL
from fastn.cli._helpers import _ensure_fresh_token, _handle_401, _verbose_post
from fastn.config import load_config
from fastn._constants import DEPLOY_FLOW_MUTATION, FLOW_BUILDER_SPACE_ID, FLOW_BUILDER_URL, FLOW_RUN_API_URL, FLOWS_API_URL, LIST_FLOWS_QUERY, GET_FLOW_QUERY
from fastn._flows import _extract_flow_input_fields as _extract_input_fields, _extract_output_fields


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse_model_schema(model: dict | None) -> dict | None:
    """Parse a jsonSchema from a flow's inputModel or outputModel.

    The ``model`` dict (from the GraphQL ``api`` query) has the shape::

        {"id": "...", "name": "...", "jsonSchema": "<JSON string or dict>"}

    Returns the parsed JSON Schema dict, or ``None`` if the model is
    missing or has no schema.
    """
    if not model or not isinstance(model, dict):
        return None
    raw = model.get("jsonSchema")
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
    if isinstance(raw, dict):
        return raw
    return None


def _require_auth():
    """Load config, check auth, refresh token, return (config, headers, project_id)."""
    config = load_config()
    if not config.auth_token and not config.api_key:
        raise click.ClickException("Not authenticated. Run `fastn login` first.")

    _ensure_fresh_token(config)

    project_id = config.resolve_project_id()
    if not project_id:
        raise click.ClickException("No project configured. Run `fastn login` first.")

    return config, config.get_headers(), project_id


def _flows_api_post(headers, endpoint, payload):
    """POST to the flows REST API and handle common errors."""
    url = f"{FLOWS_API_URL}/{endpoint}"
    resp = _verbose_post(url, headers=headers, payload=payload)

    if resp.status_code == 401:
        _handle_401(resp)

    body = None
    try:
        body = resp.json()
    except (ValueError, RuntimeError):
        pass

    if resp.status_code >= 400:
        error_code = (body or {}).get("error", "")
        if error_code == "FLOW_NOT_FOUND":
            raise click.ClickException(
                "Flow not found. Run `fastn flow ls` to see available flows."
            )
        if error_code == "RUN_NOT_FOUND":
            raise click.ClickException(
                "Run not found. Check the run_id and try again."
            )
        raise click.ClickException(f"API error ({resp.status_code}): {resp.text[:200]}")

    # Unwrap {body: ...} envelope
    if isinstance(body, dict) and "body" in body:
        return body["body"]
    return body


def _gql_post(headers, query, variables):
    """POST to the GraphQL API and handle common errors."""
    payload = {"query": query, "variables": variables}
    resp = _verbose_post(GRAPHQL_URL, headers=headers, payload=payload)

    if resp.status_code == 401:
        _handle_401(resp)
    if resp.status_code >= 400:
        raise click.ClickException(f"API error ({resp.status_code}): {resp.text[:200]}")

    data = resp.json().get("data", {})
    errors = resp.json().get("errors")
    if errors:
        raise click.ClickException(
            f"GraphQL error: {errors[0].get('message', 'Unknown error')}"
        )

    return data


# ---------------------------------------------------------------------------
# fastn flow  (group)
# ---------------------------------------------------------------------------

@cli.group(
    cls=OrderedGroup,
    command_order=["ls", "generate", "run", "deploy", "schema", "update", "delete"],
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Show API calls (cURL) and responses")
@click.pass_context
def flow(ctx, verbose):
    """Build and run automated workflows between your connected apps.

    \b
    Usage:
      fastn flow ls                  List all flows
      fastn flow ls --status deployed  List only deployed flows
      fastn flow generate             Generate a new flow
      fastn flow run <flow_name>     Run a flow
      fastn flow schema <flow_name>  Discover flow input schema
      fastn flow delete <flow_id>    Delete a flow
      fastn flow update <flow_id>    Update a flow
    """
    if verbose:
        ctx.ensure_object(dict)
        ctx.obj["verbose"] = True


@flow.command(name="ls")
@click.option("--status", "-s", default=None,
              help="Filter flows by status (e.g. deployed, pending)")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Show API calls (cURL) and responses")
@click.pass_context
def flow_ls(ctx, status, verbose):
    """List all flows in the current project."""
    if verbose:
        ctx.ensure_object(dict)
        ctx.obj["verbose"] = True
    _list_flows(status)


def _list_flows(status):
    """Fetch and display flows."""
    config, headers, project_id = _require_auth()

    variables = {
        "input": {
            "clientId": project_id,
            "first": 500,
            "after": None,
            "query": '{"input":{"limit":500,"offset":0,"sort":"desc","query":"","filter":{}}}',
        }
    }

    data = _gql_post(headers, LIST_FLOWS_QUERY, variables)

    edges = (data.get("apis") or {}).get("edges") or []

    items = []
    for edge in edges:
        node = (edge or {}).get("node") or {}
        items.append(node)

    # Client-side status filter (case-insensitive, accepts friendly labels too)
    _LABEL_TO_RAW = {"PENDING": "CONNECT", "DEPLOYED": "DEPLOYED"}
    _VALID_STATUSES = {"CONNECT", "DEPLOYED", "PENDING"}
    if status:
        status_upper = status.upper()
        if status_upper not in _VALID_STATUSES:
            valid_list = ", ".join(sorted(_VALID_STATUSES))
            raise click.ClickException(
                f"Invalid status '{status}'. Valid statuses: {valid_list}"
            )
        # Map friendly label back to raw API value
        raw_match = _LABEL_TO_RAW.get(status_upper, status_upper)
        items = [f for f in items if (f.get("status") or "").upper() == raw_match]

    if not items:
        click.echo("No flows found in this project.")
        return

    click.echo()
    click.echo(f"  {'Name':<25} {'Status':<10} {'Version':<10} {'ID'}")
    click.echo(f"  {'─' * 25} {'─' * 10} {'─' * 10} {'─' * 36}")
    for f in items:
        name = (f.get("name") or "")[:25]
        raw_status = f.get("status") or ""
        # Map internal API statuses to user-friendly labels
        _STATUS_LABELS = {
            "CONNECT": "Pending",
            "DEPLOYED": "Deployed",
        }
        fstatus = _STATUS_LABELS.get(raw_status, raw_status)[:10]
        version = (f.get("version") or "")[:10]
        fid = f.get("id", "")
        click.echo(f"  {name:<25} {fstatus:<10} {version:<10} {fid}")
    click.echo()
    click.echo(f"  {len(items)} flow(s) found.")


# ---------------------------------------------------------------------------
# fastn flow generate
# ---------------------------------------------------------------------------

@flow.command()
@click.option("--prompt", "-p", required=True, help="Plain-English description of the flow to generate")
def generate(prompt):
    """Generate an integration flow via the flow builder agent.

    Starts a conversational session with the Fastn flow builder.
    The agent may ask clarifying questions - answer them interactively
    until the flow is generated.  Press Ctrl+C or enter an empty line to
    exit early.

    \b
    Examples:
      fastn flow generate -p "When a Jira ticket is created, post to Slack"
      fastn flow generate --prompt "Sync new Hubspot contacts to Salesforce daily"
    """
    config, headers, _project_id = _require_auth()

    session_id = str(uuid.uuid4())
    create_headers = dict(headers)
    create_headers["x-fastn-custom-auth"] = "true"
    create_headers["x-fastn-space-id"] = FLOW_BUILDER_SPACE_ID
    create_headers["x-fastn-space-tenantid"] = _project_id
    create_headers["stage"] = "DRAFT"

    click.echo()
    click.echo("  \u2728 Starting flow builder session...")
    click.echo("  Type your response or press Enter to exit.")
    click.echo()

    chat_input = prompt
    last_options = []
    while True:
        payload = {
            "input": {
                "chatInput": chat_input,
                "sessionID": session_id,
                "projectId": _project_id,
            }
        }

        # Show progress spinner with rotating status messages
        import threading
        import sys

        stop_spinner = threading.Event()

        def _spinner():
            frames = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]
            stages = [
                "Analyzing requirements",
                "Checking available connectors",
                "Planning workflow steps",
                "Designing integration logic",
                "Evaluating trigger conditions",
                "Mapping data fields",
                "Optimizing flow structure",
                "Preparing response",
            ]
            i = 0
            stage_idx = 0
            stage_ticks = 0
            while not stop_spinner.is_set():
                msg = stages[stage_idx]
                dots = "." * ((stage_ticks // 5) % 4)
                line = f"\r  {frames[i % len(frames)]} {msg}{dots}"
                sys.stderr.write(line.ljust(60))
                sys.stderr.flush()
                i += 1
                stage_ticks += 1
                # Advance to next stage every ~3 seconds
                if stage_ticks >= 30 and stage_idx < len(stages) - 1:
                    stage_idx += 1
                    stage_ticks = 0
                stop_spinner.wait(0.1)
            sys.stderr.write("\r" + " " * 60 + "\r")
            sys.stderr.flush()

        spinner_thread = threading.Thread(target=_spinner, daemon=True)
        spinner_thread.start()

        try:
            resp = _verbose_post(
                FLOW_BUILDER_URL, headers=create_headers,
                payload=payload, timeout=config.timeout,
            )
        finally:
            stop_spinner.set()
            spinner_thread.join(timeout=1)

        if resp.status_code == 401:
            _handle_401(resp, config=config)
        if resp.status_code >= 400:
            raise click.ClickException(f"API error ({resp.status_code}): {resp.text[:200]}")

        body = None
        try:
            body = resp.json()
        except (ValueError, RuntimeError):
            pass

        # Unwrap {body: ...} envelope - body may be a JSON string
        result = body
        if isinstance(body, dict) and "body" in body:
            result = body["body"]
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, ValueError):
                pass

        # Unwrap nested envelope: {message: <agent_dict>} or {output: <agent_dict>}
        if isinstance(result, dict):
            for _key in ("message", "output", "response"):
                _inner = result.get(_key)
                if isinstance(_inner, str):
                    try:
                        _inner = json.loads(_inner)
                    except (json.JSONDecodeError, ValueError):
                        pass
                if isinstance(_inner, dict) and ("signal" in _inner or "options" in _inner):
                    result = _inner
                    break

        # Display the agent response
        click.echo()
        if isinstance(result, dict):
            # Check if a flow was created
            flow_id = result.get("flow_id") or result.get("flowId") or result.get("id") or ""
            if flow_id:
                flow_name = result.get("name") or result.get("flow_name") or flow_id
                click.echo("  \u2705 Flow generated successfully!")
                click.echo(f"     ID:   {flow_id}")
                if flow_name != flow_id:
                    click.echo(f"     Name: {flow_name}")
                click.echo()
                click.echo("  Next steps:")
                click.echo(f"    fastn flow deploy {flow_id}    Deploy to LIVE")
                click.echo(f"    fastn flow run {flow_id}       Test run the flow")
                click.echo(f"    fastn flow schema {flow_id}    View input/output schema")
                return

            # Show the agent's message
            message = result.get("message") or result.get("output") or result.get("response") or ""
            if message:
                click.echo(f"  \U0001f916 {message}")

            # Show options as a numbered list
            last_options = result.get("options") or []
            if last_options:
                click.echo()
                for i, opt in enumerate(last_options, 1):
                    title = opt.get("title") or opt.get("label") or f"Option {i}"
                    desc = opt.get("description") or ""
                    click.echo(f"    {i}. {title}")
                    if desc:
                        click.echo(f"       {desc}")

            if not message and not last_options:
                click.echo(json.dumps(result, indent=2))
        else:
            click.echo(str(result) if result else "  (no response)")

        # Prompt for follow-up input
        click.echo()
        try:
            chat_input = click.prompt("  \u2192 You", default="", show_default=False)
        except (click.Abort, EOFError):
            click.echo("\n  \U0001f44b Session ended.")
            return

        if not chat_input.strip():
            click.echo("  \U0001f44b Session ended.")
            return

        # Allow picking an option by number
        if last_options and chat_input.strip().isdigit():
            idx = int(chat_input.strip()) - 1
            if 0 <= idx < len(last_options):
                picked = last_options[idx]
                chat_input = picked.get("title") or picked.get("label") or chat_input


# ---------------------------------------------------------------------------
# fastn flow run
# ---------------------------------------------------------------------------

def _discover_input_fields(headers, project_id, flow_name):
    """Fetch the flow definition and discover input fields.

    Returns (fields_list, schema_dict) where fields_list is a sorted
    list of dot-path field names and schema_dict is the JSON Schema.
    Returns ([], {}) if no fields are discovered.
    """
    variables = {
        "input": {
            "clientId": project_id,
            "id": flow_name,
        }
    }
    data = _gql_post(headers, GET_FLOW_QUERY, variables)
    flow_data = data.get("api")
    if not flow_data:
        return [], {}

    # Prefer inputModel.jsonSchema, fall back to step scanning
    input_schema = _parse_model_schema(flow_data.get("inputModel"))
    if input_schema and input_schema.get("properties"):
        fields = sorted(input_schema["properties"].keys())
        return fields, input_schema

    discovered = _extract_input_fields(flow_data)
    return discovered["fields"], discovered["schema"]


def _prompt_for_fields(fields):
    """Prompt the user for each discovered input field and build the input dict.

    Supports nested fields (dot-path like ``user.name``) by building
    a nested dict structure.
    """
    click.echo()
    click.echo("  Input fields discovered:")
    for f in fields:
        click.echo(f"    - {f}")
    click.echo()

    input_data = {}
    for field_path in fields:
        value = click.prompt(f"  {field_path}")
        # Try to parse as JSON for non-string values
        try:
            parsed = json.loads(value)
            value = parsed
        except (json.JSONDecodeError, ValueError):
            pass  # keep as string

        # Build nested dict from dot-path
        parts = field_path.split(".")
        current = input_data
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                current[part] = value
            else:
                if part not in current or not isinstance(current[part], dict):
                    current[part] = {}
                current = current[part]

    return input_data


@flow.command()
@click.argument("flow_name")
@click.option("--stage", "-s", default=None, type=click.Choice(["DRAFT", "LIVE"], case_sensitive=False),
              help="Deployment stage (DRAFT or LIVE)")
@click.option("--input", "-d", "input_json", default=None,
              help='Input data as JSON string (e.g. \'{"name": "test"}\')')
def run(flow_name, stage, input_json):
    """Run a flow via the v1 API.

    Automatically discovers the flow's input schema and prompts for
    each required field.  Use --input/-d to provide input as JSON and
    skip the interactive prompts.

    \b
    Examples:
      fastn flow run testflow
      fastn flow run testflow --stage DRAFT
      fastn flow run testflow -s LIVE -d '{"name": "hello"}'
    """
    config, headers, project_id = _require_auth()

    # Parse explicit input JSON if provided
    input_data = None
    if input_json:
        try:
            input_data = json.loads(input_json)
        except json.JSONDecodeError as e:
            raise click.ClickException(f"Invalid JSON for --input: {e}")

    # Auto-discover schema and prompt when no explicit input
    if input_data is None:
        fields, schema = _discover_input_fields(headers, project_id, flow_name)
        if fields:
            input_data = _prompt_for_fields(fields)
        else:
            input_data = {}

    # Call the v1 flow run endpoint (requires x-fastn-custom-auth: true)
    run_headers = dict(headers)
    run_headers["x-fastn-custom-auth"] = "true"
    if stage:
        run_headers["stage"] = stage.upper()

    url = f"{FLOW_RUN_API_URL}/{flow_name}"
    payload = {"input": input_data or {}}
    resp = _verbose_post(url, headers=run_headers, payload=payload, timeout=config.timeout)

    if resp.status_code == 401:
        _handle_401(resp, config=config)

    body = None
    try:
        body = resp.json()
    except (ValueError, RuntimeError):
        pass

    if resp.status_code >= 400:
        error_code = (body or {}).get("error", "")
        if error_code == "FLOW_NOT_FOUND":
            raise click.ClickException(
                "Flow not found. Run `fastn flow ls` to see available flows."
            )
        raise click.ClickException(f"API error ({resp.status_code}): {resp.text[:200]}")

    # Unwrap {body: ...} envelope
    result = body
    if isinstance(body, dict) and "body" in body:
        result = body["body"]

    click.echo()
    if isinstance(result, dict):
        click.echo(f"  \u2713 Flow '{flow_name}' executed successfully.")
        click.echo()
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(str(result))


# ---------------------------------------------------------------------------
# fastn flow deploy
# ---------------------------------------------------------------------------

@flow.command()
@click.argument("flow_name")
@click.option("--stage", "-s", default="LIVE",
              type=click.Choice(["DRAFT", "LIVE"], case_sensitive=False),
              help="Target stage (default: LIVE)")
@click.option("--comment", "-m", default="", help="Deployment comment")
def deploy(flow_name, stage, comment):
    """Deploy a flow to a stage (DRAFT or LIVE).

    \b
    Examples:
      fastn flow deploy testflow
      fastn flow deploy testflow --stage DRAFT
      fastn flow deploy testflow -s LIVE -m "Production release"
    """
    _config, headers, project_id = _require_auth()

    variables = {
        "input": {
            "clientId": project_id,
            "env": stage.upper(),
            "id": flow_name,
            "comment": comment,
        }
    }

    data = _gql_post(headers, DEPLOY_FLOW_MUTATION, variables)
    result = data.get("deployApiToStage", data)

    click.echo()
    click.echo(f"  \u2713 Flow '{flow_name}' deployed to {stage.upper()}.")
    if result and isinstance(result, dict):
        click.echo(f"    id: {result.get('id', 'N/A')}")


# ---------------------------------------------------------------------------
# fastn flow schema
# ---------------------------------------------------------------------------

@flow.command()
@click.argument("flow_name")
def schema(flow_name):
    """Show the input/output schema of a flow in AI tool format.

    Returns a JSON object with name, description, toolId, inputSchema,
    and outputSchema - ready for use with LLM tool calling.

    Uses the flow's defined inputModel/outputModel when available,
    falling back to step scanning for input discovery.

    \b
    Examples:
      fastn flow schema testflow
    """
    config, headers, project_id = _require_auth()

    # Fetch the full flow definition
    variables = {
        "input": {
            "clientId": project_id,
            "id": flow_name,
        }
    }

    data = _gql_post(headers, GET_FLOW_QUERY, variables)

    flow_data = data.get("api")
    if not flow_data:
        raise click.ClickException(
            f"Flow '{flow_name}' not found. Run `fastn flow ls` to see available flows."
        )

    # Build input schema - prefer inputModel.jsonSchema, fall back to step scanning
    input_schema = _parse_model_schema(flow_data.get("inputModel"))
    if not input_schema or not input_schema.get("properties"):
        discovered = _extract_input_fields(flow_data)
        if discovered["fields"]:
            input_schema = discovered["schema"]

    # Build output schema - prefer outputModel.jsonSchema, fall back to hasResponse scanning
    output_schema = _parse_model_schema(flow_data.get("outputModel"))
    if not output_schema or not output_schema.get("properties"):
        discovered_output = _extract_output_fields(flow_data)
        if discovered_output["fields"]:
            output_schema = discovered_output["schema"]

    # Emit AI tool format
    tool = {
        "name": flow_data.get("name", flow_name),
        "description": flow_data.get("description", ""),
        "toolId": flow_data.get("id", flow_name),
        "inputSchema": input_schema or {"type": "object", "properties": {}, "required": []},
        "outputSchema": output_schema or {"type": "object", "properties": {}, "required": []},
    }

    click.echo(json.dumps(tool, indent=2))


# ---------------------------------------------------------------------------
# fastn flow delete
# ---------------------------------------------------------------------------

@flow.command()
@click.argument("flow_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def delete(flow_id, yes):
    """Delete a flow.

    \b
    Examples:
      fastn flow delete testflow
      fastn flow delete testflow -y
    """
    _config, headers, _project_id = _require_auth()

    if not yes:
        if not click.confirm(f"  Delete flow '{flow_id}'?"):
            click.echo("  Cancelled.")
            return

    result = _flows_api_post(headers, "delete", {"flow_id": flow_id})

    click.echo()
    click.echo(f"  \u2713 Flow '{flow_id}' deleted.")


# ---------------------------------------------------------------------------
# fastn flow update
# ---------------------------------------------------------------------------

@flow.command()
@click.argument("flow_id")
@click.option("--prompt", "-p", default=None, help="New prompt to regenerate the flow")
@click.option("--schedule", default=None, help='Cron schedule (e.g. "0 9 * * MON-FRI")')
@click.option("--enabled/--disabled", default=None, help="Enable or disable the flow")
def update(flow_id, prompt, schedule, enabled):
    """Update an existing flow.

    \b
    Examples:
      fastn flow update testflow --schedule "0 9 * * MON-FRI"
      fastn flow update testflow --disabled
      fastn flow update testflow -p "Also send a summary email"
    """
    _config, headers, _project_id = _require_auth()

    payload = {"flow_id": flow_id}
    if prompt is not None:
        payload["prompt"] = prompt
    if schedule is not None:
        payload["schedule"] = schedule
    if enabled is not None:
        payload["enabled"] = enabled

    if len(payload) == 1:
        raise click.ClickException(
            "Nothing to update. Pass --prompt, --schedule, or --enabled/--disabled."
        )

    result = _flows_api_post(headers, "update", payload)

    click.echo()
    click.echo(f"  \u2713 Flow '{flow_id}' updated.")
    if isinstance(result, dict):
        if result.get("questions"):
            click.echo()
            click.echo("  Fastn needs more information:")
            for q in result["questions"]:
                click.echo(f"    - {q}")
