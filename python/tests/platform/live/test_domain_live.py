# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""The typed calendar and CRM methods, the catalog and connect(app), end to end on a customer that has Google Calendar
and HubSpot connected. Everything created here is removed at the end. A port of node/test/live/domain.test.ts.
Env: LIVE=1, FASTN_API_KEY, FASTN_TEST_CUSTOMER; FASTN_BASE_URL (default https://api.fastn-test.dev); LIVE_PROD=1 for production.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, Iterator

import pytest

from fastn.platform import Customer, FastnApiError, FastnClient
from fastn.platform.domain import parse_iso_ms

from ._shared import BASE_URL, E2E, evidence, guard_production, hours_from_now, live, run, wait

guard_production()
pytestmark = live
ev = evidence("domain")
state: Dict[str, str] = {"meeting": "", "meeting2": "", "contact": "", "note": "", "task": "", "probe": "", "deal": ""}


@pytest.fixture(scope="module")
def fastn() -> Iterator[FastnClient]:
    client = FastnClient(api_key=os.environ["FASTN_API_KEY"], base_url=BASE_URL)
    yield client
    client.close()


@pytest.fixture(scope="module")
def customer(fastn: FastnClient) -> Iterator[Customer]:
    c = fastn.customer(E2E)
    yield c

    def drop(what: str, f: Callable[[], Any]) -> None:
        try:
            ev(f"cleanup {what}", f())
        except Exception as e:  # noqa: BLE001
            ev(f"cleanup {what} failed", str(e))

    if state["meeting"]:
        drop("meeting", lambda: c.calendar.cancel(state["meeting"]))
    if state["meeting2"]:
        drop("meeting2 (idempotent replay made a second one)", lambda: c.calendar.cancel(state["meeting2"]))
    if state["deal"]:
        drop("deal", lambda: c.crm.deals.delete(state["deal"]))
    if state["probe"]:
        drop("probe task", lambda: c.crm.tasks.delete(state["probe"]))
    if state["task"]:
        drop("task", lambda: c.crm.tasks.delete(state["task"]))
    if state["note"]:
        drop("note", lambda: c.crm.notes.delete(state["note"]))
    if state["contact"]:
        drop("contact", lambda: c.crm.contacts.delete(state["contact"]))


def test_catalog_lists_categories_entities_and_fields_and_the_customers_providers(fastn: FastnClient, customer: Customer) -> None:
    cats = fastn.catalog.categories()
    slugs = [c["slug"] for c in cats]
    assert "crm" in slugs and "scheduling" in slugs
    contact = fastn.catalog.entity("crm", "contact")
    assert "create" in contact["operations"] and "search" in contact["operations"]
    assert sorted(f["field"] for f in fastn.catalog.fields("scheduling", "meeting") if f.get("required")) == ["start_time", "title"]
    providers = customer.catalog.providers("crm", "contact")
    assert next(p for p in providers if p["connectorSlug"] == "hubspot")["connected"] is True
    with pytest.raises(FastnApiError) as ei:
        fastn.catalog.entity("crm", "unicorn")
    assert ei.value.code == "NOT_FOUND"
    ev("catalog", {"categories": [f"{c['slug']}({len(c['entities'])})" for c in cats], "providers": [p["connectorSlug"] for p in providers if p["connected"]]})


def test_connect_app_makes_a_setup_link_by_connector_slug_reads_it_and_cancels_it(customer: Customer) -> None:
    link = customer.connect("googleCalendar", expires_in_minutes=30)
    assert link["url"].startswith("https:") and link["status"] == "pending" and re.match(r"^wgt_", link["widgetId"])
    assert "endOrgId" not in link
    assert customer.links.get(link["setupId"])["status"] == "pending"
    assert customer.links.cancel(link["setupId"])["status"] == "revoked"
    with pytest.raises(FastnApiError) as ei:
        customer.connect("no-such-connector")
    assert ei.value.code == "WIDGET_NOT_FOUND"
    ev("connect", {"setupId": link["setupId"], "widgetId": link["widgetId"]})


def test_calendar_free_slots_book_idempotent_get_find_list_reschedule_cancel(customer: Customer) -> None:
    free = customer.calendar.free_slots({"start_time": hours_from_now(24), "end_time": hours_from_now(32), "timezone": "UTC", "slot_minutes": 30})
    assert free["provider"] == "googleCalendar" and len(free["free"]) + len(free["busy"]) > 0 and len(free["slots"]) > 0
    meeting = {"title": f"SDK live py {run}", "start_time": hours_from_now(26), "end_time": hours_from_now(26.5), "timezone": "UTC"}
    a = customer.calendar.book(meeting, idempotency_key=f"py{run}_book")
    b = customer.calendar.book(meeting, idempotency_key=f"py{run}_book")
    state["meeting"] = a["id"]
    if b["id"] != a["id"]:
        state["meeting2"] = b["id"]
    assert b["id"] == a["id"] and a["data"]["title"] == meeting["title"]
    assert customer.calendar.get(a["id"])["data"]["status"] == "confirmed"
    found = customer.calendar.find({"start_time": hours_from_now(0), "end_time": hours_from_now(48)})
    assert any(r["id"] == a["id"] for r in found["records"])
    assert len(customer.calendar.list(page_size=1)["records"]) == 1
    moved = customer.calendar.reschedule(a["id"], {"start_time": hours_from_now(27), "end_time": hours_from_now(27.5)})
    assert (parse_iso_ms(moved["data"]["start_time"]) or 0) > (parse_iso_ms(a["data"]["start_time"]) or 0)
    gone = customer.calendar.cancel(a["id"], idempotency_key=f"py{run}_cancel")
    state["meeting"] = ""
    assert gone["id"] == a["id"] and gone["provider"] == "googleCalendar" and gone["deleted"] is True
    ev("calendar", {"id": a["id"], "slots": len(free["slots"]), "moved": moved["data"]["start_time"]})


def test_crm_contacts_notes_tasks_deals_with_stages(customer: Customer) -> None:
    email = f"sdk.py.{run}@example.com"
    c = customer.crm.contacts.create({"first_name": "Jane", "last_name": "Doe", "email": email}, idempotency_key=f"py{run}_contact")
    state["contact"] = c["id"]
    assert customer.crm.contacts.get(c["id"])["data"]["email"] == email
    assert customer.crm.contacts.update(c["id"], {"last_name": "Doe-Smith"})["data"]["last_name"] == "Doe-Smith"
    found = customer.crm.contacts.find({"email": email})
    for _ in range(4):  # HubSpot indexes a new contact with a 9 to 12 s lag
        if found["records"]:
            break
        wait(5)
        found = customer.crm.contacts.find({"email": email})
    assert any(r["id"] == c["id"] for r in found["records"])
    assert len(customer.crm.contacts.list(page_size=1)["records"]) == 1

    note = customer.crm.notes.add({"body": f"SDK live py {run}", "parent_id": c["id"], "parent_type": "contact"}, idempotency_key=f"py{run}_note")
    state["note"] = note["id"]
    assert note["id"]
    customer.crm.notes.update(note["id"], {"body": f"SDK live py {run} (edited)"})

    task = customer.crm.tasks.add({"subject": f"SDK live py {run}", "due_date": hours_from_now(33)}, idempotency_key=f"py{run}_task")
    state["task"] = task["id"]
    assert task["data"]["status"] == "NOT_STARTED"
    assert customer.crm.tasks.update(task["id"], {"status": "COMPLETED"})["data"]["status"] == "COMPLETED"
    probe = customer.crm.tasks.add({"subject": f"SDK warning probe py {run}", "due_date": hours_from_now(34), "contact_id": c["id"]})
    state["probe"] = probe["id"]
    customer.crm.tasks.delete(probe["id"])
    state["probe"] = ""
    assert any(re.search("contact_id", w) for w in probe.get("warnings") or [])  # a field the provider does not map is reported, not silently dropped

    stages = customer.crm.deals.stages()
    assert len(stages["records"]) > 1
    deal = customer.crm.deals.create({"name": f"SDK live py {run}", "amount": 1200}, idempotency_key=f"py{run}_deal")
    state["deal"] = deal["id"]
    target = stages["records"][1]["id"]
    customer.crm.deals.move_stage(deal["id"], target)
    assert customer.crm.deals.get(deal["id"])["data"]["stage"] == target
    ev("crm", {"contact": c["id"], "note": note["id"], "task": task["id"], "deal": deal["id"], "stage": target, "warnings": probe.get("warnings")})


def test_errors_unknown_customer_404_unconnected_provider_validation(fastn: FastnClient, customer: Customer) -> None:
    with pytest.raises(FastnApiError) as e0:
        fastn.customer(f"no_such_customer_py_{run}").crm.contacts.list()
    assert e0.value.status == 404
    with pytest.raises(FastnApiError) as e1:
        customer.crm.contacts.list(provider="pipedrive")
    assert re.search("PROVIDER", e1.value.code or "")
    with pytest.raises(FastnApiError) as e2:
        customer.calendar.book({"title": "no time"})
    assert e2.value.code == "UNIFIED_VALIDATION_FAILED"
    ev("errors", {"unknown": e0.value.code, "unconnected": e1.value.code, "validation": e2.value.code})
