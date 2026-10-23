import { describe, it, expect } from "vitest";
import { createHmac } from "node:crypto";
import { verifyEventSignature, parseEvent, signEventBody, readEventHeaders } from "../../src/index.js";

const secret = "whsec_test_secret"; const body = '{"id":"evt_1","type":"unified.event","data":{"a":1}}'; const ts = "1760000000";
const sig = "sha256=" + createHmac("sha256", secret).update(`${ts}.${body}`).digest("hex");

describe("event signatures", () => {
  it("matches the platform format sha256=HMAC(secret, '<ts>.<body>')", () => { expect(signEventBody(secret, ts, body)).toBe(sig); });
  it("verifies a good delivery from Node headers and from Fetch Headers", () => {
    expect(verifyEventSignature(secret, { "x-fastn-timestamp": ts, "x-fastn-signature": sig }, body, { now: 1760000010 })).toBe(true);
    expect(verifyEventSignature(secret, new Headers({ "X-Fastn-Timestamp": ts, "X-Fastn-Signature": sig }), Buffer.from(body), { now: 1760000010 })).toBe(true);
  });
  it("rejects a changed body, wrong secret, stale timestamp, missing header", () => {
    expect(verifyEventSignature(secret, { "x-fastn-timestamp": ts, "x-fastn-signature": sig }, body + " ", { now: 1760000010 })).toBe(false);
    expect(verifyEventSignature("other", { "x-fastn-timestamp": ts, "x-fastn-signature": sig }, body, { now: 1760000010 })).toBe(false);
    expect(verifyEventSignature(secret, { "x-fastn-timestamp": ts, "x-fastn-signature": sig }, body, { now: 1760001000 })).toBe(false);
    expect(verifyEventSignature(secret, { "x-fastn-timestamp": ts, "x-fastn-signature": sig }, body, { now: 1760001000, toleranceSeconds: 0 })).toBe(true);
    expect(verifyEventSignature(secret, { "x-fastn-timestamp": ts }, body)).toBe(false);
  });
  it("parseEvent returns the event and headers, throws on a bad signature", () => {
    const ev = parseEvent(secret, { "x-fastn-timestamp": ts, "x-fastn-signature": sig, "x-fastn-event-id": "evt_1", "x-fastn-redelivery": "true" }, body, { now: 1760000010 });
    expect(ev.id).toBe("evt_1"); expect(ev.headers.eventId).toBe("evt_1"); expect(ev.headers.redelivery).toBe(true);
    expect(() => parseEvent(secret, { "x-fastn-timestamp": ts, "x-fastn-signature": "sha256=00" }, body, { now: 1760000010 })).toThrow(/signature/);
  });
  it("readEventHeaders handles arrays and case", () => {
    expect(readEventHeaders({ "X-Fastn-Timestamp": ["1"], "x-fastn-signature": "s" })).toEqual({ timestamp: "1", signature: "s", eventId: undefined, redelivery: false });
  });
});
