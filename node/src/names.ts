/**
 * Named values for apps, unified categories and entities, and app events, so calls are written with names your editor
 * completes and checks instead of typed-in strings:
 *
 *   customer.connect(Apps.googleCalendar)
 *   customer.watch(Apps.hubspot, [HubSpotEvents.contactCreated])
 *   fastn.catalog.fields(Categories.crm, Entities.contact)
 *
 * Each value is the exact string the API takes, so the plain string form keeps working and nothing changes on the wire.
 * The apps are the ones mapped in fastn's unified catalog; an app outside this list can still be passed by its slug.
 */

/** Apps mapped in fastn's unified catalog, by connector slug. */
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
  task: "task",
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
  /** HubSpot has no stage-only event: this arrives as deal.propertyChange with propertyName "dealstage". */
  dealStageChanged: "deal.stageChanged",
  ticketCreated: "ticket.created",
  ticketUpdated: "ticket.updated",
  ticketDeleted: "ticket.deleted",
} as const;
