/**
 * Named values for apps, unified categories and entities, and app events, so calls are written with names your editor
 * completes and checks instead of typed-in strings:
 *
 *   customer.connect(Apps.googleCalendar)
 *   customer.watch(Apps.hubspot, [HubSpotEvents.contactCreated])
 *   fastn.catalog.fields(Categories.crm, Entities.contact)
 *
 * Each value is the exact string the API takes, so the plain string form keeps working and nothing changes on the wire.
 * The apps, categories and entities are those in fastn's unified catalog on production as of 0.5.0 (the catalog can grow,
 * and an org can add its own); anything outside these lists can still be passed as a string.
 */

/** Apps mapped in fastn's unified catalog on production as of 0.5.0, by connector slug. */
export const Apps = {
  asana: "asana",
  bmcHelixItsm: "bmcHelixItsm",
  calcom: "calcom",
  calendly: "calendly",
  capsulecrm: "capsulecrm",
  clickup: "clickup",
  close: "close",
  coda: "coda",
  confluence: "confluence",
  copper: "copper",
  facebook: "facebook",
  freshservice: "freshservice",
  googleCalendar: "googleCalendar",
  googleDocs: "googleDocs",
  hubspot: "hubspot",
  insightly: "insightly",
  intercom: "intercom",
  jira: "jira",
  keap: "keap",
  linear: "linear",
  manageEngineServiceDeskPlus: "manageEngineServiceDeskPlus",
  microsoftOutlookCalendar: "microsoftOutlookCalendar",
  microsoftTeams: "microsoftTeams",
  monday: "monday",
  notion: "notion",
  nutshell: "nutshell",
  pipedrive: "pipedrive",
  salesflare: "salesflare",
  salesforce: "salesforce",
  servicenow: "servicenow",
  slack: "slack",
  trello: "trello",
  vtiger: "vtiger",
  zendeskSupport: "zendeskSupport",
  zohoCrm: "zohoCrm",
  zoom: "zoom",
} as const;

/** One of the apps in `Apps`. */
export type KnownApp = (typeof Apps)[keyof typeof Apps];
/** An app's connector slug: one of `Apps` (completed by the editor), or any other connector slug. */
export type AppName = KnownApp | (string & {});

/** Unified API categories. */
export const Categories = {
  crm: "crm",
  documents: "documents",
  knowledgeBase: "knowledge_base",
  messaging: "messaging",
  projectManagement: "project_management",
  scheduling: "scheduling",
} as const;

/** Unified API entities (each belongs to one category, see the catalog). */
export const Entities = {
  // crm
  account: "account",
  contact: "contact",
  engagement: "engagement",
  engagementType: "engagement_type",
  lead: "lead",
  note: "note",
  opportunity: "opportunity",
  stage: "stage",
  task: "task", // crm/task
  user: "user",
  // documents
  document: "document",
  documentContent: "document_content",
  // knowledge_base
  article: "article",
  // messaging
  channelMessage: "channel_message",
  directMessage: "direct_message",
  // project_management
  ticketing: "ticketing",
  // scheduling
  availability: "availability",
  meeting: "meeting",
} as const;

/** HubSpot change events for `customer.watch(Apps.hubspot, [...])`, in plain words (mapped to HubSpot's own ids). */
export const HubSpotEvents = {
  contactCreated: "contact.created",
  contactUpdated: "contact.updated",
  contactDeleted: "contact.deleted",
  companyCreated: "company.created",
  companyUpdated: "company.updated",
  companyDeleted: "company.deleted",
  dealCreated: "deal.created",
  dealUpdated: "deal.updated",
  dealDeleted: "deal.deleted",
  /** HubSpot has no stage-only event: this subscribes to deal.propertyChange, so EVERY deal property change arrives
   *  (amount, owner, close date, ...). Keep only stage moves by checking propertyName === "dealstage" in the event. */
  dealStageChanged: "deal.stageChanged",
  ticketCreated: "ticket.created",
  ticketUpdated: "ticket.updated",
  ticketDeleted: "ticket.deleted",
} as const;

/** The events Fastn sends to your webhook (`event.type`), and the values `fastn.webhooks.create({ eventTypes })` takes. */
export const EventTypes = {
  connectionConnected: "connection.connected",
  connectionRevoked: "connection.revoked",
  connectionExpired: "connection.expired",
  setupLinkCompleted: "setup_link.completed",
  setupLinkExpired: "setup_link.expired",
  /** A change in a customer's app, as the app sent it (after `customer.watch`). */
  connectorEvent: "connector.event",
  /** The same change as a unified record (after `customer.watch`). */
  unifiedEvent: "unified.event",
  /** Sent by `fastn.webhooks.test(id)`; never subscribed to. */
  endpointTest: "endpoint.test",
} as const;

/** One of `EventTypes`. */
export type KnownEventType = (typeof EventTypes)[keyof typeof EventTypes];
/** An event type: one of `EventTypes` (completed by the editor), or any other string (new types keep working). */
export type EventType = KnownEventType | (string & {});

/** What a `unified.event` says happened to the record (`event.action`). */
export const UnifiedActions = { created: "created", updated: "updated", deleted: "deleted" } as const;

/** Fastn plans for a customer (`customer.register({ plan })`). */
export const Plans = {
  launch: "launch",
  scale: "scale",
  enterprise: "enterprise",
  growth: "growth",
  free: "free",
} as const;

/** A customer's status (`customer.update({ status })`, `customer.get()`). */
export const CustomerStatus = {
  active: "active",
  suspended: "suspended",
  pendingReview: "pending_review",
  blocked: "blocked",
} as const;

/** Kinds of org (`fastn.orgs.listOrgs({ type: OrgTypes.endOrg })`: your customers). */
export const OrgTypes = {
  company: "company",
  partner: "partner",
  endOrg: "end_org",
  personal: "personal",
  account: "account",
} as const;

/** What happened to a received event (`fastn.events.listEvents({ outcome })`). */
export const EventOutcomes = {
  received: "received",
  firstAttempt: "first_attempt",
  recovered: "recovered",
  notProcessed: "not_processed",
  inProgress: "in_progress",
  replayed: "replayed",
  replaySucceeded: "replay_succeeded",
  replayFailed: "replay_failed",
  replayedFromDlq: "replayed_from_dlq",
  rerunByHand: "rerun_by_hand",
  eventReplay: "event_replay",
  afterDlq: "after_dlq",
  recoveredByRetry: "recovered_by_retry",
  sentToDlq: "sent_to_dlq",
} as const;

/**
 * Checks a name before it is used: a misspelt member in plain JavaScript (`Apps.googleCalender`) is `undefined`, which
 * would otherwise reach the API as a confusing error, or, for `unwatch`, read as "no app" and remove every watch.
 */
export function requireName(value: unknown, what: string): string {
  if (typeof value === "string" && value !== "") return value;
  throw new TypeError(`${what}: got ${value === "" ? "an empty string" : String(value)}; pass a name such as Apps.googleCalendar or "googleCalendar" (a misspelt Apps / Categories / Entities member is undefined)`);
}
