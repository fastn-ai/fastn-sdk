import { describe, it, expect } from "vitest";
import { Apps, Categories, Entities, HubSpotEvents, EVENT_ALIASES, FastnClient } from "../../src/index.js";
import { mockFetch } from "../helpers.js";

describe("named apps, categories, entities and events", () => {
  it("each name is the exact string the API takes, so the string form and the named form send the same request", () => {
    expect(Apps.googleCalendar).toBe("googleCalendar");
    expect(Apps.hubspot).toBe("hubspot");
    expect(Categories.knowledgeBase).toBe("knowledge_base");
    expect(Entities.engagementType).toBe("engagement_type");
    for (const [k, v] of Object.entries(Apps)) expect(k).toBe(v);
  });

  it("HubSpotEvents lists exactly the plain names the SDK maps to HubSpot's event ids", () => {
    expect(new Set(Object.values(HubSpotEvents))).toEqual(new Set(Object.keys(EVENT_ALIASES.hubspot!)));
  });

  it("catalog.fields(Categories.crm, Entities.contact) calls the same route as the strings", async () => {
    const entity = { slug: "contact", operations: [], createFields: [{ field: "email", label: "Email", type: "string", required: false }] };
    const m = mockFetch((url) => url.includes("/unified/categories") ? { body: { data: [{ slug: "crm", entities: [entity] }] } } : { status: 404, body: {} });
    const fastn = new FastnClient({ apiKey: "k", fetch: m.fetch, retries: 0 });
    const named = await fastn.catalog.fields(Categories.crm, Entities.contact);
    const plain = await fastn.catalog.fields("crm", "contact");
    expect(named).toEqual(plain);
    expect(named[0]!.field).toBe("email");
  });
});
