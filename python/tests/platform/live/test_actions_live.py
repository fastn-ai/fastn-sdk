# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""watch / watches / unwatch, rename_account, update, call_log and fastn.webhooks, live on a customer that has
HubSpot and Google Calendar connected. Everything created (a watch, a webhook subscription) is removed at the end;
disconnect() is never called here (it would remove a real account).
Env: LIVE=1, FASTN_API_KEY, FASTN_TEST_CUSTOMER, FASTN_HUBSPOT_ACCOUNT_ID (the HubSpot portal id); FASTN_BASE_URL; LIVE_PROD=1 for production.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterator

import pytest

from fastn.platform import Customer, FastnApiError, FastnClient

from ._shared import BASE_URL, E2E, evidence, guard_production, live, run

guard_production()
pytestmark = live
ev = evidence("actions")
state: Dict[str, Any] = {"watch_ids": [], "hook": None}
HOOK_URL = "https://hooks.example.com/py-040"


@pytest.fixture(scope="module")
def fastn() -> Iterator[FastnClient]:
    client = FastnClient(api_key=os.environ["FASTN_API_KEY"], base_url=BASE_URL)
    yield client
    for wid in list(state["watch_ids"]):
        try:
            ev("cleanup watch", client.customer(E2E).unwatch(wid))
        except Exception as e:  # noqa: BLE001
            ev("cleanup watch failed", str(e))
    if state["hook"]:
        try:
            ev("cleanup webhook", client.webhooks.delete(state["hook"]))
        except Exception as e:  # noqa: BLE001
            ev("cleanup webhook failed", str(e))
    client.close()


@pytest.fixture(scope="module")
def customer(fastn: FastnClient) -> Customer:
    return fastn.customer(E2E)


def test_watchable_events_watch_watches_unwatch(customer: Customer) -> None:
    account_id = os.environ.get("FASTN_HUBSPOT_ACCOUNT_ID")
    if not account_id:
        pytest.skip("FASTN_HUBSPOT_ACCOUNT_ID (the HubSpot portal id) is not set")
    catalog = customer.watchable_events("hubspot")
    ids = [e["id"] for e in catalog]
    assert "contact.creation" in ids and "deal.propertyChange" in ids
    ev("watchable_events", {"count": len(ids), "ids": ids})
    before = customer.watches("hubspot")
    ev("watches before", [w["id"] for w in before])
    w = customer.watch("hubspot", ["contact.created", "deal.stageChanged"], account_id=account_id)
    state["watch_ids"].append(w["id"])
    assert w["app"] == "hubspot" and w["events"] == ["contact.creation", "deal.propertyChange"] and "endOrgId" not in w and "appTrigger" not in w
    assert w.get("accountId") == account_id and w.get("connectorId")
    ev("watch", w)
    listed = customer.watches("hubspot")
    mine = next((x for x in listed if x["id"] == w["id"]), None)
    assert mine is not None and mine["events"] == ["contact.creation", "deal.propertyChange"] and "endOrgId" not in mine and "appTrigger" not in mine
    with pytest.raises(FastnApiError) as ei:
        customer.watch("hubspot", ["contact.exploded"])
    assert ei.value.code == "EVENT_NOT_FOUND"
    removed = customer.unwatch("hubspot")
    assert w["id"] in removed
    state["watch_ids"] = [x for x in state["watch_ids"] if x not in removed]
    after = customer.watches("hubspot")
    ev("unwatch", {"removed": removed, "after": [x["id"] for x in after]})
    assert all(x["id"] != w["id"] for x in after)
    assert after == [] or len(after) == len(before)  # nothing of ours is left; pre-existing watches (if any) untouched


def test_rename_account_update_and_call_log(customer: Customer) -> None:
    conns = [c for c in customer.connections().get("data") or [] if (c.get("connectorSlug") or (c.get("connector") or {}).get("slug")) == "googleCalendar"]
    assert conns, "the e2e customer has no Google Calendar account"
    acc = conns[0]
    renamed = customer.rename_account(acc["id"], acc["name"])  # same name: no visible change
    ev("rename_account", {"id": acc["id"], "name": renamed.get("name") if isinstance(renamed, dict) else renamed})
    assert isinstance(renamed, dict) and "endOrgId" not in renamed or renamed is not None
    org = customer.get()
    current = (org.get("data") or org).get("name")
    row = customer.update({"name": current})
    ev("update", {"name": row.get("name") if isinstance(row, dict) else row})
    assert isinstance(row, dict) and row.get("name") == current
    log = customer.call_log("wire_corr")
    ev("call_log", {"n": len(log), "sample": log[:2]})
    assert isinstance(log, list) and all("endOrgId" not in x and "end_org_id" not in x for x in log)
    with pytest.raises(TypeError):
        customer.call_log("")


def test_webhooks_create_list_get_update_test_deliveries_rotate_replay_delete(fastn: FastnClient) -> None:
    hook = fastn.webhooks.create({"url": HOOK_URL, "eventTypes": ["connection.connected"], "description": f"py sdk 0.4.0 live {run}"})
    state["hook"] = hook["id"]
    assert hook["id"] and hook.get("secret")
    ev("webhook create", {"id": hook["id"], "hasSecret": bool(hook.get("secret"))})
    assert any(s["id"] == hook["id"] for s in fastn.webhooks.list())
    assert fastn.webhooks.get(hook["id"])["url"] == HOOK_URL
    upd = fastn.webhooks.update(hook["id"], {"description": f"py sdk 0.4.0 live {run} (edited)"})
    ev("webhook update", {"description": upd.get("description")})
    tested = fastn.webhooks.test(hook["id"])
    ev("webhook test", tested)
    deliveries = fastn.webhooks.deliveries(hook["id"], limit=5)
    ev("webhook deliveries", {"n": len(deliveries), "first": deliveries[0] if deliveries else None})
    assert isinstance(deliveries, list)
    rotated = fastn.webhooks.rotate_secret(hook["id"])
    ev("webhook rotate", {"hasSecret": bool(rotated.get("secret"))})
    assert rotated.get("secret") and rotated["secret"] != hook["secret"]
    if deliveries:
        try:
            ev("webhook replay", fastn.webhooks.replay(deliveries[0]["id"]))
        except FastnApiError as e:
            ev("webhook replay refused", {"status": e.status, "code": e.code, "message": e.message})
            assert e.status < 500
    deleted = fastn.webhooks.delete(hook["id"])
    state["hook"] = None
    ev("webhook delete", deleted)
    assert not any(s["id"] == hook["id"] for s in fastn.webhooks.list())
