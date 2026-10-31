"""Agent-tool names (fastn.ToolFormats, Stages, FlowStatus, Connectors) match what the client accepts."""

from __future__ import annotations

import glob
import os

import fastn
from fastn import Connectors, FlowStatus, Stages, ToolFormats
from fastn._constants import _SUPPORTED_FORMATS


def _values(cls: type) -> set:
    return {v for k, v in vars(cls).items() if not k.startswith("_") and isinstance(v, str)}


def test_tool_formats_are_exactly_the_supported_formats() -> None:
    assert _values(ToolFormats) == set(_SUPPORTED_FORMATS)


def test_connectors_are_exactly_the_shipped_connector_stubs() -> None:
    here = os.path.dirname(fastn.__file__)
    stubs = {os.path.basename(f)[:-4] for f in glob.glob(os.path.join(here, "connectors", "*.pyi"))} - {"__init__"}
    assert _values(Connectors) == stubs
    assert Connectors.slack == "slack" and Connectors.github == "github" and Connectors.jira == "jira"


def test_stage_and_flow_status_values() -> None:
    assert (Stages.live, Stages.staging, Stages.dev, Stages.draft) == ("LIVE", "STAGING", "DEV", "DRAFT")
    assert (FlowStatus.deployed, FlowStatus.draft) == ("DEPLOYED", "DRAFT")


def test_the_names_work_as_the_strings_did() -> None:
    client = fastn.FastnClient(api_key="k", project_id="p", stage=Stages.dev)
    assert client is not None
