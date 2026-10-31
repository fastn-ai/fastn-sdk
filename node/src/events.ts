import type { AppName, EventType } from "./names.js";
import { createHmac, timingSafeEqual } from "node:crypto";
import { withoutInternalIds } from "./tools.js";

/** What fastn puts on every event delivery (POST to your subscription URL). */
export interface EventHeaders {
  /** X-Fastn-Timestamp: unix seconds when the delivery was signed. */
  timestamp: string;
  /** X-Fastn-Signature: "sha256=" + HMAC-SHA256(secret, "<timestamp>.<raw body>"). */
  signature: string;
  /** X-Fastn-Event-Id: stable across retries; drop repeats by id. */
  eventId?: string;
  /** X-Fastn-Redelivery: "true" on a retry. */
  redelivery?: boolean;
}

/** Reads the fastn headers out of any header bag (Node IncomingMessage.headers, Fetch Headers, or a plain object). */
export function readEventHeaders(headers: Record<string, string | string[] | undefined> | Headers): EventHeaders {
  const get = (name: string): string | undefined => {
    if (typeof (headers as Headers).get === "function") return (headers as Headers).get(name) ?? undefined;
    const bag = headers as Record<string, string | string[] | undefined>;
    const v = bag[name] ?? bag[Object.keys(bag).find((k) => k.toLowerCase() === name) ?? ""];
    return Array.isArray(v) ? v[0] : v;
  };
  return {
    timestamp: get("x-fastn-timestamp") ?? "",
    signature: get("x-fastn-signature") ?? "",
    eventId: get("x-fastn-event-id"),
    redelivery: (get("x-fastn-redelivery") ?? "").toLowerCase() === "true",
  };
}

const isEventHeaders = (h: unknown): h is EventHeaders => typeof h === "object" && h !== null && typeof (h as EventHeaders).signature === "string" && typeof (h as EventHeaders).timestamp === "string";

export function signEventBody(secret: string, timestamp: string | number, rawBody: string | Buffer): string {
  return "sha256=" + createHmac("sha256", secret).update(`${timestamp}.`).update(rawBody).digest("hex");
}

export interface VerifyOptions {
  /** Reject deliveries whose timestamp is older or newer than this many seconds (default 300). 0 disables the check. */
  toleranceSeconds?: number;
  /** For tests: the current unix time in seconds. */
  now?: number;
  /** Keep fastn's internal customer id (`endOrgId`) in the parsed event. Default false: partners use `tenantRef`. */
  internalIds?: boolean;
}

/**
 * True when `signature` matches the body as fastn signed it. Pass the RAW request body (string or Buffer),
 * never a re-serialised object: any whitespace change breaks the HMAC.
 */
export function verifyEventSignature(secret: string, headers: EventHeaders | Record<string, string | string[] | undefined> | Headers, rawBody: string | Buffer, opts: VerifyOptions = {}): boolean {
  const h = isEventHeaders(headers) ? headers : readEventHeaders(headers);
  if (!h.signature || !h.timestamp || !secret) return false;
  const tol = opts.toleranceSeconds ?? 300;
  if (tol > 0) {
    const ts = Number(h.timestamp);
    const now = opts.now ?? Math.floor(Date.now() / 1000);
    if (!Number.isFinite(ts) || Math.abs(now - ts) > tol) return false;
  }
  const expected = Buffer.from(signEventBody(secret, h.timestamp, rawBody));
  const given = Buffer.from(h.signature);
  return expected.length === given.length && timingSafeEqual(expected, given);
}

/** A delivered event, as parsed from the request body. Fields beyond `id`/`type` depend on the event. */
export interface FastnEvent {
  id?: string;
  /** Compare with `EventTypes` (`event.type === EventTypes.setupLinkCompleted`); still a plain string underneath. */
  type?: EventType;
  /** The app, for connection and app events; compare with `Apps` (`event.app === Apps.hubspot`). */
  app?: AppName;
  [key: string]: any;
}

/**
 * Verifies and parses one delivery. Throws when the signature is wrong; returns the parsed event otherwise.
 * Usage (Express with `express.raw({ type: "application/json" })`): `const ev = parseEvent(secret, req.headers, req.body)`.
 */
export function parseEvent(secret: string, headers: Record<string, string | string[] | undefined> | Headers, rawBody: string | Buffer, opts?: VerifyOptions): FastnEvent & { headers: EventHeaders } {
  const h = readEventHeaders(headers);
  if (!verifyEventSignature(secret, h, rawBody, opts)) throw new Error("fastn event signature does not match (wrong secret, altered body, or stale timestamp)");
  const parsed = JSON.parse(typeof rawBody === "string" ? rawBody : rawBody.toString("utf8"));
  // The body names the customer by the id the partner chose (tenantRef) and by fastn's internal id (endOrgId);
  // the internal one is left out unless asked for, so partner code never sees two ids for one customer.
  const event = opts?.internalIds ? parsed : withoutInternalIds(parsed);
  return { ...event, headers: h };
}
