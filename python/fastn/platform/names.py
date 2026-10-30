"""Named values for apps, unified categories and entities, and app events, so calls are written with names your editor
completes instead of typed-in strings:

    customer.connect(Apps.googleCalendar)
    customer.watch(Apps.hubspot, [HubSpotEvents.contactCreated])
    fastn.catalog.fields(Categories.crm, Entities.contact)

Each value is the exact string the API takes (they are plain ``str``), so the string form keeps working and nothing
changes on the wire. The apps, categories and entities are those in fastn's unified catalog on production as of 0.5.0 (the catalog can
grow, and an org can add its own); anything outside these lists can still be passed as a string. The same names exist in the Node SDK (``import { Apps } from "@fastn-ai/sdk"``).
"""

from __future__ import annotations

from typing import Final


class Apps:
    """Apps mapped in fastn's unified catalog, by connector slug."""

    asana: Final = "asana"
    bmcHelixItsm: Final = "bmcHelixItsm"
    calcom: Final = "calcom"
    calendly: Final = "calendly"
    capsulecrm: Final = "capsulecrm"
    clickup: Final = "clickup"
    close: Final = "close"
    coda: Final = "coda"
    confluence: Final = "confluence"
    copper: Final = "copper"
    facebook: Final = "facebook"
    freshservice: Final = "freshservice"
    googleCalendar: Final = "googleCalendar"
    googleDocs: Final = "googleDocs"
    hubspot: Final = "hubspot"
    insightly: Final = "insightly"
    intercom: Final = "intercom"
    jira: Final = "jira"
    keap: Final = "keap"
    linear: Final = "linear"
    manageEngineServiceDeskPlus: Final = "manageEngineServiceDeskPlus"
    microsoftOutlookCalendar: Final = "microsoftOutlookCalendar"
    microsoftTeams: Final = "microsoftTeams"
    monday: Final = "monday"
    notion: Final = "notion"
    nutshell: Final = "nutshell"
    pipedrive: Final = "pipedrive"
    salesflare: Final = "salesflare"
    salesforce: Final = "salesforce"
    servicenow: Final = "servicenow"
    slack: Final = "slack"
    trello: Final = "trello"
    vtiger: Final = "vtiger"
    zendeskSupport: Final = "zendeskSupport"
    zohoCrm: Final = "zohoCrm"
    zoom: Final = "zoom"


class Categories:
    """Unified API categories."""

    crm: Final = "crm"
    documents: Final = "documents"
    knowledgeBase: Final = "knowledge_base"
    messaging: Final = "messaging"
    projectManagement: Final = "project_management"
    scheduling: Final = "scheduling"


class Entities:
    """Unified API entities (each belongs to one category, see the catalog)."""

    account: Final = "account"
    contact: Final = "contact"
    engagement: Final = "engagement"
    engagementType: Final = "engagement_type"
    lead: Final = "lead"
    note: Final = "note"
    opportunity: Final = "opportunity"
    stage: Final = "stage"
    task: Final = "task"
    user: Final = "user"
    document: Final = "document"
    documentContent: Final = "document_content"
    article: Final = "article"
    channelMessage: Final = "channel_message"
    directMessage: Final = "direct_message"
    ticketing: Final = "ticketing"
    availability: Final = "availability"
    meeting: Final = "meeting"


class HubSpotEvents:
    """HubSpot change events for ``customer.watch(Apps.hubspot, [...])``, in plain words (mapped to HubSpot's own ids)."""

    contactCreated: Final = "contact.created"
    contactUpdated: Final = "contact.updated"
    contactDeleted: Final = "contact.deleted"
    companyCreated: Final = "company.created"
    companyUpdated: Final = "company.updated"
    companyDeleted: Final = "company.deleted"
    dealCreated: Final = "deal.created"
    dealUpdated: Final = "deal.updated"
    dealDeleted: Final = "deal.deleted"
    #: HubSpot has no stage-only event: this subscribes to deal.propertyChange, so every deal property change arrives
    #: (amount, owner, close date, ...). Keep only stage moves by checking propertyName == "dealstage" in the event.
    dealStageChanged: Final = "deal.stageChanged"
    ticketCreated: Final = "ticket.created"
    ticketUpdated: Final = "ticket.updated"
    ticketDeleted: Final = "ticket.deleted"


__all__ = ["Apps", "Categories", "Entities", "HubSpotEvents"]
