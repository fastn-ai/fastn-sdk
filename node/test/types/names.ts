// Compile-time checks for the named values (run by `npm run typecheck` through tsconfig.test.json; never executed).
// 1. the named forms compile; 2. every 0.4 string form still compiles (backward compatible); 3. a misspelt member does not.
import { FastnClient, ToolsClient, Apps, Categories, Entities, HubSpotEvents, EventTypes, UnifiedActions, parseEvent, type HubSpotEvent, type FastnEvent } from "../../src/index.js";

declare const events: string[];
declare const app: string;
const fastn = new FastnClient({ apiKey: "k" });
const c = fastn.customer("x");
const meeting = { title: "t", start_time: "2026-01-01T00:00:00Z", end_time: "2026-01-01T00:30:00Z" };

export async function namedForms(): Promise<void> {
  await c.connect(Apps.googleCalendar);
  await c.watch(Apps.hubspot, [HubSpotEvents.contactCreated, HubSpotEvents.dealStageChanged]);
  await c.watches(Apps.hubspot);
  await c.unwatch(Apps.hubspot);
  await c.watchableEvents(Apps.hubspot);
  await c.calendar.book(meeting, { provider: Apps.googleCalendar });
  await fastn.catalog.fields(Categories.crm, Entities.contact);
  const typed: HubSpotEvent[] = [HubSpotEvents.dealUpdated];
  await c.watch(Apps.hubspot, typed);
}

export async function stringFormsFrom04(): Promise<void> {
  await c.connect("googleCalendar");
  await c.connect(app);
  await c.watch("hubspot", ["contact.created", "deal.stageChanged"]);
  await c.watch("hubspot", events);
  await c.watch(app, events);
  await c.watches("hubspot");
  await c.unwatch("hubspot");
  await c.watchableEvents("hubspot");
  await c.calendar.book(meeting, { provider: "googleCalendar" });
  await fastn.catalog.fields("crm", "contact");
  await c.records({ category: "crm", entity: "contact", provider: "hubspot" }).list();
}

export async function misspeltMembers(): Promise<void> {
  // @ts-expect-error not a member of Apps
  await c.connect(Apps.googleCalender);
  // @ts-expect-error not a member of HubSpotEvents
  await c.watch(Apps.hubspot, [HubSpotEvents.contactCraeted]);
  // @ts-expect-error not a member of Categories
  await fastn.catalog.fields(Categories.crmm, Entities.contact);
}

export function eventNames(event: FastnEvent): string {
  // named: compiles and narrows nothing away
  switch (event.type) {
    case EventTypes.setupLinkCompleted: return "link";
    case EventTypes.connectionConnected: return event.app === Apps.hubspot ? "hubspot" : "other";
    case EventTypes.unifiedEvent: return event.action === UnifiedActions.created ? "new" : "changed";
    default: return "x";
  }
}

export function eventStringsFrom04(event: FastnEvent): boolean {
  const e = parseEvent("whsec", {}, "{}");
  return event.type === "setup_link.completed" || event.app === "hubspot" || e.type === "connection.connected" || event.type === "some.future.event";
}

export async function webhooksAndActions(): Promise<void> {
  await fastn.webhooks.create({ url: "https://x", eventTypes: [EventTypes.connectionConnected, EventTypes.setupLinkCompleted, EventTypes.connectorEvent, EventTypes.unifiedEvent] });
  await fastn.webhooks.create({ url: "https://x", eventTypes: ["connection.connected"] });
  await c.runAction({ connector: Apps.hubspot, action: "getContact", input: {} });
  await c.runAction({ connector: "hubspot", action: "getContact" });
  const t = new ToolsClient({ key: "k", url: "https://mcp.fastn.dev/w" });
  await t.toolsOf(Apps.googleCalendar);
  await t.toolsOf("googleCalendar");
}

export function misspeltEventMember(): void {
  // @ts-expect-error not a member of EventTypes
  void EventTypes.setupLinkComplete;
}
