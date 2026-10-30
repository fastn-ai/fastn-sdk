"""Tests for the Fastn stub generator."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from generator.generate import (
    StubGenerator,
    generate_stubs,
    parse_connector,
    parse_registry,
    _extract_tool_params,
    _sanitize_identifier,
    _to_camel_case,
    _to_pascal_case,
    _map_type,
)


SAMPLE_REGISTRY = {
    "version": "2025.02.14",
    "connectors": {
        "slack": {
            "display_name": "Slack",
            "category": "communication",
            "tools": {
                "send_message": {
                    "toolId": "act_slack_send_message",
                    "description": "Send a message to a Slack channel",
                    "params": {
                        "text": {
                            "type": "string",
                            "required": True,
                            "description": "Message text",
                        },
                        "channel": {
                            "type": "string",
                            "required": True,
                            "description": "Channel name",
                        },
                    },
                },
                "create_channel": {
                    "toolId": "act_slack_create_channel",
                    "description": "Create a new Slack channel",
                    "params": {
                        "name": {
                            "type": "string",
                            "required": True,
                            "description": "Channel name",
                        },
                        "is_private": {
                            "type": "boolean",
                            "required": False,
                            "description": "Private channel",
                        },
                    },
                },
            },
        },
        "jira": {
            "display_name": "Jira",
            "category": "project_management",
            "tools": {
                "create_issue": {
                    "toolId": "act_jira_create_issue",
                    "description": "Create a Jira issue",
                    "params": {
                        "summary": {
                            "type": "string",
                            "required": True,
                            "description": "Issue summary",
                        },
                        "project_key": {
                            "type": "string",
                            "required": True,
                            "description": "Project key",
                        },
                        "issue_type": {
                            "type": "string",
                            "required": False,
                            "description": "Issue type",
                        },
                    },
                },
            },
        },
    },
}


class TestHelpers:
    def test_sanitize_identifier(self) -> None:
        assert _sanitize_identifier("send_message") == "send_message"
        assert _sanitize_identifier("my-tool") == "my_tool"
        assert _sanitize_identifier("123abc") == "_123abc"
        assert _sanitize_identifier("hello world") == "hello_world"

    def test_to_camel_case(self) -> None:
        assert _to_camel_case("send_message") == "sendMessage"
        assert _to_camel_case("create_channel") == "createChannel"
        assert _to_camel_case("name") == "name"

    def test_to_pascal_case(self) -> None:
        assert _to_pascal_case("slack") == "Slack"
        assert _to_pascal_case("google_drive") == "GoogleDrive"

    def test_map_type_python(self) -> None:
        assert _map_type("string", "python") == "str"
        assert _map_type("integer", "python") == "int"
        assert _map_type("boolean", "python") == "bool"
        assert _map_type("array", "python") == "List[Any]"
        assert _map_type("unknown", "python") == "Any"

    def test_only_python_is_supported(self) -> None:
        with pytest.raises(ValueError):
            _map_type("string", "typescript")
        with pytest.raises(ValueError):
            StubGenerator(language="typescript")


class TestParseRegistry:
    def test_parse_basic(self) -> None:
        parsed = parse_registry(SAMPLE_REGISTRY)
        assert parsed["version"] == "2025.02.14"
        assert len(parsed["connectors"]) == 2

    def test_connector_names(self) -> None:
        parsed = parse_registry(SAMPLE_REGISTRY)
        names = [c["name"] for c in parsed["connectors"]]
        assert "jira" in names
        assert "slack" in names

    def test_connector_class_names(self) -> None:
        parsed = parse_registry(SAMPLE_REGISTRY)
        for c in parsed["connectors"]:
            if c["name"] == "slack":
                assert c["class_name"] == "SlackConnector"
            elif c["name"] == "jira":
                assert c["class_name"] == "JiraConnector"

    def test_tool_params_sorted(self) -> None:
        parsed = parse_registry(SAMPLE_REGISTRY)
        slack = next(c for c in parsed["connectors"] if c["name"] == "slack")
        send_msg = next(t for t in slack["tools"] if t["name"] == "send_message")
        # Required params should come first
        required = [p for p in send_msg["params"] if p["required"]]
        optional = [p for p in send_msg["params"] if not p["required"]]
        assert all(p["required"] for p in send_msg["params"][:len(required)])

    def test_empty_registry(self) -> None:
        parsed = parse_registry({"version": "1", "connectors": {}})
        assert parsed["connectors"] == []


class TestParseConnector:
    def test_single_connector(self) -> None:
        connector_data = SAMPLE_REGISTRY["connectors"]["slack"]
        parsed = parse_connector("slack", connector_data)
        assert parsed["name"] == "slack"
        assert parsed["class_name"] == "SlackConnector"
        assert len(parsed["tools"]) == 2


class TestStubGenerator:
    def test_invalid_language(self) -> None:
        with pytest.raises(ValueError, match="Unsupported language"):
            StubGenerator(language="ruby")

    def test_generate_python_connector(self) -> None:
        gen = StubGenerator(language="python")
        parsed = parse_registry(SAMPLE_REGISTRY)
        slack = next(c for c in parsed["connectors"] if c["name"] == "slack")
        result = gen.generate_connector(slack)
        assert "class SlackConnector" in result
        assert "def send_message" in result
        assert "def create_channel" in result
        assert "channel: str" in result

    def test_generate_python_index(self) -> None:
        gen = StubGenerator(language="python")
        parsed = parse_registry(SAMPLE_REGISTRY)
        result = gen.generate_index(parsed["connectors"], ["slack"])
        assert "class Fastn" in result
        assert "class AsyncFastn" in result
        assert "slack" in result
        assert "from .connectors.slack import SlackConnector" in result

    def test_generate_placeholder(self) -> None:
        gen = StubGenerator(language="python")
        parsed = parse_registry(SAMPLE_REGISTRY)
        non_installed = [c for c in parsed["connectors"] if c["name"] != "slack"]
        result = gen.generate_placeholder(non_installed)
        assert "class JiraConnector" in result
        assert "fastn connector add jira" in result

    def test_generate_all_python(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            files = generate_stubs(
                SAMPLE_REGISTRY,
                ["slack"],
                tmpdir,
                language="python",
            )
            assert any("__init__.pyi" in f for f in files)
            assert any("slack.pyi" in f for f in files)
            assert any("_placeholders.pyi" in f for f in files)

            # Verify content
            index_path = Path(tmpdir) / "fastn" / "__init__.pyi"
            assert index_path.exists()
            content = index_path.read_text()
            assert "SlackConnector" in content

    def test_no_placeholders_when_all_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            files = generate_stubs(
                SAMPLE_REGISTRY,
                ["slack", "jira"],
                tmpdir,
                language="python",
            )
            assert not any("_placeholders" in f for f in files)

    def test_zero_tool_connector_has_getattr(self) -> None:
        """Connectors with 0 tools generate a class with __getattr__ fallback."""
        zero_tool_registry = {
            "version": "1.0",
            "connectors": {
                "hubspot": {
                    "display_name": "HubSpot",
                    "category": "crm",
                    "tools": {},
                },
            },
        }
        gen = StubGenerator(language="python")
        parsed = parse_registry(zero_tool_registry)
        hubspot = parsed["connectors"][0]
        result = gen.generate_connector(hubspot)
        assert "class HubspotConnector" in result
        assert "__getattr__" in result
        assert "def send" not in result  # no tool methods

    def test_zero_tool_connector_index_hint(self) -> None:
        """Zero-tool connectors show 'run fastn connector add' hint in index."""
        zero_tool_registry = {
            "version": "1.0",
            "connectors": {
                "hubspot": {
                    "display_name": "HubSpot",
                    "category": "crm",
                    "tools": {},
                },
            },
        }
        gen = StubGenerator(language="python")
        parsed = parse_registry(zero_tool_registry)
        result = gen.generate_index(parsed["connectors"], ["hubspot"])
        assert "fastn connector add hubspot" in result

    def test_populated_connector_no_hint(self) -> None:
        """Connectors with tools do NOT show 'run fastn connector add' hint."""
        gen = StubGenerator(language="python")
        parsed = parse_registry(SAMPLE_REGISTRY)
        result = gen.generate_index(parsed["connectors"], ["slack", "jira"])
        assert "fastn connector add slack" not in result
        assert "fastn connector add jira" not in result

    def test_all_installed_individual_files(self) -> None:
        """When all connectors are installed, each gets its own .pyi file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = generate_stubs(
                SAMPLE_REGISTRY,
                ["slack", "jira"],
                tmpdir,
                language="python",
            )
            assert any("slack.pyi" in f for f in files)
            assert any("jira.pyi" in f for f in files)
            assert not any("_placeholders" in f for f in files)


# ---------------------------------------------------------------------------
# Multi-wrapper inputSchema fixtures
# ---------------------------------------------------------------------------

MULTI_WRAPPER_REGISTRY = {
    "version": "2025.06.01",
    "connectors": {
        "github": {
            "display_name": "GitHub",
            "category": "dev_tools",
            "tools": {
                "create_issue": {
                    "toolId": "act_github_create_issue",
                    "description": "Create an issue",
                    "inputSchema": {
                        "properties": {
                            "body": {
                                "type": "object",
                                "properties": {
                                    "title": {
                                        "type": "string",
                                        "description": "Issue title",
                                    },
                                    "body": {
                                        "type": "string",
                                        "description": "Issue body",
                                    },
                                    "labels": {
                                        "type": "array",
                                        "description": "Labels",
                                    },
                                },
                                "required": ["title", "body"],
                            },
                            "url": {
                                "type": "object",
                                "properties": {
                                    "OWNER": {
                                        "type": "string",
                                        "description": "Repo owner",
                                    },
                                    "REPO": {
                                        "type": "string",
                                        "description": "Repo name",
                                    },
                                },
                                "required": ["OWNER", "REPO"],
                            },
                        },
                        "required": ["body", "url"],
                        "type": "object",
                    },
                },
                "create_commit": {
                    "toolId": "act_github_create_commit",
                    "description": "Create a commit",
                    "inputSchema": {
                        "properties": {
                            "body": {
                                "type": "object",
                                "properties": {
                                    "message": {
                                        "type": "string",
                                        "description": "Commit message",
                                    },
                                    "author": {
                                        "type": "object",
                                        "description": "Author details",
                                        "properties": {
                                            "name": {
                                                "type": "string",
                                                "description": "Author name",
                                            },
                                            "email": {
                                                "type": "string",
                                                "description": "Author email",
                                            },
                                        },
                                        "required": ["name", "email"],
                                    },
                                    "tree": {
                                        "type": "string",
                                        "description": "Tree SHA",
                                    },
                                },
                                "required": ["message", "tree"],
                            },
                        },
                        "required": ["body"],
                        "type": "object",
                    },
                },
            },
        },
    },
}

# Tool with the same param name in two wrappers (name conflict)
CONFLICT_TOOL_DATA = {
    "toolId": "act_conflict",
    "description": "Tool with conflicting param names",
    "inputSchema": {
        "properties": {
            "body": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "Kind in body",
                    },
                },
                "required": ["kind"],
            },
            "param": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "Kind in param",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Limit",
                    },
                },
                "required": [],
            },
        },
        "required": ["body"],
        "type": "object",
    },
}


class TestMultiWrapper:
    """Tests for multi-wrapper inputSchema extraction."""

    def test_all_wrappers_extracted(self) -> None:
        """Params from all wrappers (body + url) appear in the flat list."""
        parsed = parse_registry(MULTI_WRAPPER_REGISTRY)
        gh = next(c for c in parsed["connectors"] if c["name"] == "github")
        create_issue = next(t for t in gh["tools"] if t["name"] == "create_issue")
        param_names = {p["name"] for p in create_issue["params"]}
        # body wrapper fields
        assert "title" in param_names
        assert "body" in param_names
        assert "labels" in param_names
        # url wrapper fields
        assert "OWNER" in param_names
        assert "REPO" in param_names

    def test_required_flags_from_inner_wrappers(self) -> None:
        """Required status comes from each wrapper's own required list."""
        parsed = parse_registry(MULTI_WRAPPER_REGISTRY)
        gh = next(c for c in parsed["connectors"] if c["name"] == "github")
        create_issue = next(t for t in gh["tools"] if t["name"] == "create_issue")
        params_by_name = {p["name"]: p for p in create_issue["params"]}
        assert params_by_name["title"]["required"] is True
        assert params_by_name["OWNER"]["required"] is True
        assert params_by_name["labels"]["required"] is False

    def test_dedup_across_wrappers(self) -> None:
        """Duplicate param names across wrappers: first wrapper wins."""
        params = _extract_tool_params(CONFLICT_TOOL_DATA, tool_name="conflict")
        kind_params = [p for p in params if p["name"] == "kind"]
        assert len(kind_params) == 1
        # First occurrence is from "body" (sorted alphabetically)
        assert kind_params[0]["required"] is True  # body.kind is required

    def test_non_conflict_params_all_present(self) -> None:
        """Non-conflicting params from second wrapper still appear."""
        params = _extract_tool_params(CONFLICT_TOOL_DATA, tool_name="conflict")
        param_names = {p["name"] for p in params}
        assert "limit" in param_names

    def test_stub_contains_all_wrapper_params(self) -> None:
        """Generated Python stub includes params from all wrappers."""
        gen = StubGenerator(language="python")
        parsed = parse_registry(MULTI_WRAPPER_REGISTRY)
        gh = next(c for c in parsed["connectors"] if c["name"] == "github")
        result = gen.generate_connector(gh)
        assert "OWNER: str" in result
        assert "REPO: str" in result
        assert "title: str" in result


class TestTypedDictGeneration:
    """Tests for TypedDict generation from nested object params."""

    def test_typed_dict_name_attached(self) -> None:
        """Nested object params get a typed_dict_name."""
        parsed = parse_registry(MULTI_WRAPPER_REGISTRY)
        gh = next(c for c in parsed["connectors"] if c["name"] == "github")
        create_commit = next(t for t in gh["tools"] if t["name"] == "create_commit")
        author = next(p for p in create_commit["params"] if p["name"] == "author")
        assert author["typed_dict_name"] == "_CreateCommitAuthor"
        assert author["sub_params"] is not None
        sub_names = {sp["name"] for sp in author["sub_params"]}
        assert "name" in sub_names
        assert "email" in sub_names

    def test_typed_dicts_on_tool(self) -> None:
        """Tool dict includes typed_dicts list for TypedDict rendering."""
        parsed = parse_registry(MULTI_WRAPPER_REGISTRY)
        gh = next(c for c in parsed["connectors"] if c["name"] == "github")
        create_commit = next(t for t in gh["tools"] if t["name"] == "create_commit")
        assert len(create_commit["typed_dicts"]) == 1
        td = create_commit["typed_dicts"][0]
        assert td["name"] == "_CreateCommitAuthor"
        assert len(td["fields"]) == 2

    def test_no_typed_dict_for_simple_params(self) -> None:
        """Params with primitive types have typed_dict_name=None."""
        parsed = parse_registry(MULTI_WRAPPER_REGISTRY)
        gh = next(c for c in parsed["connectors"] if c["name"] == "github")
        create_commit = next(t for t in gh["tools"] if t["name"] == "create_commit")
        message = next(p for p in create_commit["params"] if p["name"] == "message")
        assert message["typed_dict_name"] is None

    def test_stub_renders_typed_dict_class(self) -> None:
        """Generated stub contains TypedDict class definition."""
        gen = StubGenerator(language="python")
        parsed = parse_registry(MULTI_WRAPPER_REGISTRY)
        gh = next(c for c in parsed["connectors"] if c["name"] == "github")
        result = gen.generate_connector(gh)
        assert "class _CreateCommitAuthor(TypedDict" in result
        assert "name: str" in result
        assert "email: str" in result

    def test_stub_uses_typed_dict_in_signature(self) -> None:
        """Method signature references the TypedDict name, not Dict[str, Any]."""
        gen = StubGenerator(language="python")
        parsed = parse_registry(MULTI_WRAPPER_REGISTRY)
        gh = next(c for c in parsed["connectors"] if c["name"] == "github")
        result = gen.generate_connector(gh)
        assert "_CreateCommitAuthor" in result
        # author is optional (not in body.required), so it should have Optional
        assert "author: Optional[_CreateCommitAuthor]" in result

    def test_tool_without_nested_objects_has_no_typed_dicts(self) -> None:
        """Tools with only primitive params have empty typed_dicts list."""
        parsed = parse_registry(MULTI_WRAPPER_REGISTRY)
        gh = next(c for c in parsed["connectors"] if c["name"] == "github")
        create_issue = next(t for t in gh["tools"] if t["name"] == "create_issue")
        assert create_issue["typed_dicts"] == []
