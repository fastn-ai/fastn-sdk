# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Shared by every live suite: the target environment and its production guard, the LIVE switches, and the evidence
writer (one place for `mask`, so a new secret prefix is redacted in every suite at once). A port of
node/test/live/_shared.ts.

Env: LIVE=1, FASTN_API_KEY, FASTN_TEST_CUSTOMER (a customer org with Google Calendar and HubSpot connected);
FASTN_BASE_URL (default https://api.fastn-test.dev); LIVE_PROD=1 to allow https://api.fastn.dev.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

#: Target: FASTN_BASE_URL, default https://api.fastn-test.dev (the development environment).
BASE_URL = os.environ.get("FASTN_BASE_URL", "https://api.fastn-test.dev")
IS_PROD = bool(re.search(r"api\.fastn\.dev", BASE_URL))
#: The partner API suites need LIVE=1, FASTN_API_KEY and FASTN_TEST_CUSTOMER.
LIVE_API = os.environ.get("LIVE") == "1" and bool(os.environ.get("FASTN_API_KEY")) and bool(os.environ.get("FASTN_TEST_CUSTOMER"))
#: The ref of a customer org that has Google Calendar and HubSpot connected.
E2E = os.environ.get("FASTN_TEST_CUSTOMER", "")
#: A per-run suffix for everything a suite creates.
run = datetime.now(timezone.utc).strftime("%H%M%S")
EVIDENCE_FILE = Path(__file__).with_name("evidence.jsonl")

live = pytest.mark.skipif(not LIVE_API, reason="set LIVE=1, FASTN_API_KEY and FASTN_TEST_CUSTOMER to run the live suite")
#: Suites that create connectors or throw-away orgs never run on production.
not_on_prod = pytest.mark.skipif(IS_PROD, reason="this suite creates connectors / throw-away orgs; not on production")


def guard_production(base_url: str = BASE_URL) -> None:
    """https://api.fastn.dev only with LIVE_PROD=1: the suites create and delete real bookings and CRM records."""
    if LIVE_API and re.search(r"api\.fastn\.dev", base_url) and os.environ.get("LIVE_PROD") != "1":
        raise RuntimeError("FASTN_BASE_URL points at production; set LIVE_PROD=1 to run the live suite there")


def mask(s: str) -> str:
    """Redacts keys and long tokens before anything is written to the evidence file."""
    s = re.sub(r"(emb_|ucl_|fsk_[a-z]+_|whsec_|stp_tok_|sk_)[A-Za-z0-9_\-]{6,}", r"\1***", s)
    return re.sub(r"[A-Za-z0-9_-]{48,}", "<tok>", s)


def evidence(suite: Optional[str] = None) -> Callable[[str, Any], None]:
    """An evidence writer for one suite: `ev("step", data)` appends one masked line."""

    def ev(step: str, data: Any) -> None:
        line = json.dumps({"at": datetime.now(timezone.utc).isoformat(), "step": f"{suite} {step}" if suite else step, "data": data}, default=str)
        with open(EVIDENCE_FILE, "a", encoding="utf-8") as f:
            f.write(mask(line)[:2500] + "\n")

    return ev


def data_of(r: Any) -> Any:
    return r.get("data") if isinstance(r, dict) and r.get("data") is not None else r


def hours_from_now(h: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def day_from_now(n: int) -> str:
    """YYYY-MM-DD, n days from now."""
    return (datetime.now(timezone.utc) + timedelta(days=n)).strftime("%Y-%m-%d")


def wait(seconds: float) -> None:
    time.sleep(seconds)
