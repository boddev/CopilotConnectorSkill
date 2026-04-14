// Connector configuration for the Agents Toolkit template
// Defines the connection metadata, schema, and URL resolver for a Copilot Connector.
//
// In an Agents Toolkit project, these values are typically split across:
//   - src/models/connection.ts   → connectionId, connectionName, connectionDescription
//   - src/references/schema.ts   → schema properties, types, labels, aliases
//
// This file consolidates them for reference. Adapt to your data source.
//
// Scenario: Contoso IT Helpdesk — matches the schema used in the C# and REST samples.

// ---------------------------------------------------------------------------
// Connection metadata
// ---------------------------------------------------------------------------

export const connectionId = "contosohelpdesk"; // 3-128 alphanumeric chars, unique per tenant
export const connectionName = "Contoso Helpdesk";

// Rich description — tells Copilot what content this connection has and when to use it.
// A detailed description significantly improves Copilot's ability to surface relevant results.
export const connectionDescription =
  "Internal IT helpdesk tickets from the Contoso Helpdesk system. " +
  "Contains incident reports, service requests, and change requests. " +
  "Used by IT support staff and employees to track and resolve technical issues.";

// ---------------------------------------------------------------------------
// Schema definition
// ---------------------------------------------------------------------------

/**
 * Schema property definition matching the Microsoft Graph externalConnectors API.
 * See: https://learn.microsoft.com/graph/connecting-external-content-manage-schema
 */
export interface SchemaProperty {
  name: string;
  type: "String" | "Int64" | "Double" | "DateTime" | "Boolean" | "StringCollection";
  isSearchable?: boolean;
  isQueryable?: boolean;
  isRetrievable?: boolean;
  isRefinable?: boolean;
  isExactMatchRequired?: boolean;
  labels?: string[];
  aliases?: string[];
}

/**
 * Complete schema for the Contoso Helpdesk connector.
 *
 * Key design rules enforced here:
 *  - searchable and refinable are mutually exclusive
 *  - refinable must be set in the initial schema (cannot be added later)
 *  - properties with semantic labels must be retrievable
 *  - isExactMatchRequired only on non-searchable properties
 */
export const schema = {
  baseType: "microsoft.graph.externalItem" as const,
  properties: [
    // --- Identifier ---
    {
      name: "ticketId",
      type: "String",
      isSearchable: false,
      isQueryable: true,
      isRetrievable: true,
      isExactMatchRequired: true,      // Exact-match only (IDs should not be tokenized)
      aliases: ["ID", "incidentNumber"],
    },

    // --- Core text fields ---
    {
      name: "title",
      type: "String",
      isSearchable: true,              // Full-text search
      isQueryable: true,
      isRetrievable: true,
      labels: ["title"],               // Semantic label — most important for Copilot
    },
    {
      name: "description",
      type: "String",
      isSearchable: true,              // Full-text search (long text)
      isQueryable: false,
      isRetrievable: false,            // Not returned in search results (too large)
    },

    // --- Categorical / filterable fields ---
    {
      name: "status",
      type: "String",
      isSearchable: false,             // Refinable — mutually exclusive with searchable
      isQueryable: true,
      isRetrievable: true,
      isRefinable: true,               // Appears as filter control in Search UI
      aliases: ["state"],
    },
    {
      name: "priority",
      type: "Int64",
      isQueryable: true,
      isRetrievable: true,
      isRefinable: true,
    },

    // --- People fields ---
    {
      name: "assignedTo",
      type: "String",
      isSearchable: true,              // "Find tickets assigned to Jane"
      isQueryable: true,
      isRetrievable: true,
      aliases: ["assignee", "owner"],
    },

    // --- Dates ---
    {
      name: "createdDate",
      type: "DateTime",
      isQueryable: true,
      isRetrievable: true,
      isRefinable: true,
      labels: ["createdDateTime"],
    },
    {
      name: "lastModifiedDate",
      type: "DateTime",
      isQueryable: true,
      isRetrievable: true,
      labels: ["lastModifiedDateTime"],
    },

    // --- URLs (critical for Copilot surfacing) ---
    {
      name: "itemUrl",
      type: "String",
      isRetrievable: true,
      labels: ["url"],                 // Copilot uses this to link citations back to source
    },
    {
      name: "iconUrl",
      type: "String",
      isRetrievable: true,
      labels: ["iconUrl"],             // Visual identifier in search results
    },

    // --- Multi-value / tags ---
    {
      name: "tags",
      type: "StringCollection",
      isQueryable: true,
      isRetrievable: true,
      isRefinable: true,
      isExactMatchRequired: true,
      aliases: ["labels", "categories"],
    },

    // --- Boolean flag ---
    {
      name: "isResolved",
      type: "Boolean",
      isQueryable: true,
      isRetrievable: true,
    },

    // --- Numeric estimate ---
    {
      name: "estimatedHours",
      type: "Double",
      isQueryable: true,
      isRetrievable: true,
    },
  ] satisfies SchemaProperty[],
};

// ---------------------------------------------------------------------------
// URL-to-item resolver
// ---------------------------------------------------------------------------

/**
 * Maps URLs pasted by users to items in this connector.
 * When a user pastes a helpdesk URL in Copilot or Teams, Microsoft 365
 * can resolve it to the corresponding external item and show a rich preview.
 */
export const urlToItemResolver = {
  "@odata.type": "#microsoft.graph.externalConnectors.itemIdResolver" as const,
  urlMatchInfo: {
    baseUrls: ["https://helpdesk.contoso.com"],
    urlPattern: "/tickets/(?<itemId>[A-Za-z0-9-]+)",
  },
};

// ---------------------------------------------------------------------------
// Full connection payload (for reference / manual provisioning)
// ---------------------------------------------------------------------------

/**
 * Assembled connection payload ready for Microsoft Graph API.
 * In the Agents Toolkit, this is typically handled by the provisioning lifecycle,
 * but you can use this for manual Graph calls or testing.
 */
export const connectionPayload = {
  id: connectionId,
  name: connectionName,
  description: connectionDescription,
  activitySettings: {
    urlToItemResolvers: [urlToItemResolver],
  },
};
