"""Tests for helper functions in agent_command."""

from __future__ import annotations

import pytest

from fastn.cli.agent_command import (
    _build_action_map,
    _estimate_cost,
    _extract_tool_list,
    _format_bytes,
    _format_cost,
    _format_duration,
    _format_tokens,
)


# ---------------------------------------------------------------------------
# _extract_tool_list
# ---------------------------------------------------------------------------

class TestExtractToolList:
    def test_plain_list(self) -> None:
        data = [{"toolId": "a1"}, {"toolId": "a2"}]
        assert _extract_tool_list(data) == data

    def test_tools_wrapper(self) -> None:
        data = {"tools": [{"toolId": "a1"}]}
        assert _extract_tool_list(data) == [{"toolId": "a1"}]

    def test_data_wrapper(self) -> None:
        data = {"data": [{"toolId": "a1"}]}
        assert _extract_tool_list(data) == [{"toolId": "a1"}]

    def test_body_list(self) -> None:
        data = {"body": [{"toolId": "a1"}]}
        assert _extract_tool_list(data) == [{"toolId": "a1"}]

    def test_body_dict_with_tools(self) -> None:
        data = {"body": {"tools": [{"toolId": "a1"}]}}
        assert _extract_tool_list(data) == [{"toolId": "a1"}]

    def test_body_single_tool(self) -> None:
        data = {"body": {"toolId": "a1", "function": {}}}
        assert _extract_tool_list(data) == [{"toolId": "a1", "function": {}}]

    def test_single_tool_at_top(self) -> None:
        data = {"toolId": "a1", "function": {"name": "foo"}}
        assert _extract_tool_list(data) == [data]

    def test_non_dict_non_list(self) -> None:
        assert _extract_tool_list(42) == []

    def test_empty_dict(self) -> None:
        assert _extract_tool_list({}) == []


# ---------------------------------------------------------------------------
# _build_action_map
# ---------------------------------------------------------------------------

class TestBuildActionMap:
    def test_basic_mapping(self) -> None:
        tool_list = [
            {
                "toolId": "act_slack_send",
                "function": {"name": "send_message", "parameters": {}},
            },
        ]
        registry = {"connectors": {}}

        result = _build_action_map(tool_list, registry)
        assert "send_message" in result
        assert result["send_message"]["toolId"] == "act_slack_send"

    def test_multiple_tools(self) -> None:
        tool_list = [
            {"toolId": "act_a", "function": {"name": "tool_a", "parameters": {}}},
            {"toolId": "act_b", "function": {"name": "tool_b", "parameters": {}}},
        ]
        registry = {"connectors": {}}

        result = _build_action_map(tool_list, registry)
        assert len(result) == 2
        assert "tool_a" in result
        assert "tool_b" in result


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

class TestFormatBytes:
    def test_bytes(self) -> None:
        assert _format_bytes(512) == "512 B"

    def test_kilobytes(self) -> None:
        assert _format_bytes(2048) == "2.0 KB"

    def test_megabytes(self) -> None:
        assert _format_bytes(2 * 1024 * 1024) == "2.0 MB"


class TestFormatDuration:
    def test_milliseconds(self) -> None:
        assert _format_duration(0.25) == "250ms"

    def test_seconds(self) -> None:
        assert _format_duration(3.5) == "3.5s"


class TestFormatTokens:
    def test_small_number(self) -> None:
        assert _format_tokens(500) == "500"

    def test_large_number(self) -> None:
        assert _format_tokens(15000) == "15.0K"


class TestFormatCost:
    def test_tiny_cost(self) -> None:
        assert _format_cost(0.0001) == "$0.0001"

    def test_small_cost(self) -> None:
        assert _format_cost(0.005) == "$0.005"

    def test_normal_cost(self) -> None:
        assert _format_cost(1.25) == "$1.25"


# ---------------------------------------------------------------------------
# _estimate_cost
# ---------------------------------------------------------------------------

class TestEstimateCost:
    def test_known_model(self) -> None:
        cost = _estimate_cost("gpt-4o", 1_000_000, 1_000_000)
        # gpt-4o: $2.50/M in + $10.00/M out = $12.50
        assert cost == pytest.approx(12.50, abs=0.01)

    def test_known_model_prefix_match(self) -> None:
        cost = _estimate_cost("gpt-4o-mini-2024-07-18", 1_000_000, 0)
        # gpt-4o-mini: $0.15/M in
        assert cost == pytest.approx(0.15, abs=0.01)

    def test_unknown_model_uses_default(self) -> None:
        cost = _estimate_cost("totally-unknown-model", 1_000_000, 1_000_000)
        # Falls back to gpt-4o-mini pricing: $0.15/M in + $0.60/M out = $0.75
        assert cost == pytest.approx(0.75, abs=0.01)
