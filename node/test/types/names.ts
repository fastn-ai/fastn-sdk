// Compile-time checks for the named values (run by `npm run typecheck` through tsconfig.test.json; never executed).
// 1. the named forms compile; 2. every 0.4 string form still compiles (backward compatible); 3. a misspelt member does not.
import { FastnClient, Apps, Categories, Entities, HubSpotEvents, type HubSpotEvent } from "../../src/index.js";

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
