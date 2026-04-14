// Custom data source integration for the Agents Toolkit template
//
// [Customization point] Replace the fetchSourceItems() function with your
// actual data source logic (REST API, database query, file reader, etc.).
//
// In the scaffolded Agents Toolkit project, this lives in src/custom/dataSource.ts.
// The template provides a GitHub Issues sample — swap it out for your source.
//
// Scenario: Contoso IT Helpdesk tickets fetched from a REST API.

import { schema } from "./connector-config";

// ---------------------------------------------------------------------------
// Source data model
// ---------------------------------------------------------------------------

/** Raw ticket record as returned by the Contoso Helpdesk API. */
export interface HelpdeskTicket {
  id: string;
  title: string;
  description: string;
  status: "Open" | "In Progress" | "Resolved" | "Closed";
  priority: number; // 1 = Critical, 2 = High, 3 = Medium, 4 = Low
  assignedTo: string;
  createdDate: string; // ISO 8601
  lastModifiedDate: string; // ISO 8601
  tags: string[];
  isResolved: boolean;
  estimatedHours: number;
  rootCause?: string;
  resolution?: string;
  comments?: Array<{
    author: string;
    date: string;
    text: string;
  }>;
}

// ---------------------------------------------------------------------------
// External item payload (Microsoft Graph format)
// ---------------------------------------------------------------------------

/** ACL entry for an external item. */
export interface AclEntry {
  type: "everyone" | "everyoneExceptGuests" | "user" | "group" | "externalGroup";
  value: string;
  accessType: "grant" | "deny";
}

/** Payload for PUT /external/connections/{connectionId}/items/{itemId}. */
export interface ExternalItemPayload {
  id: string;
  acl: AclEntry[];
  properties: Record<string, unknown>;
  content: {
    value: string;
    type: "text" | "html";
  };
}

// ---------------------------------------------------------------------------
// Fetch from external data source
// ---------------------------------------------------------------------------

/**
 * Fetch all active tickets from the Contoso Helpdesk API.
 *
 * [Customization point] Replace this with your actual data source calls.
 * Handle pagination, authentication, and error handling as needed.
 */
export async function fetchSourceItems(): Promise<HelpdeskTicket[]> {
  const baseUrl = process.env.DATA_SOURCE_URL || "https://api.contoso.com";
  const apiKey = process.env.DATA_SOURCE_API_KEY || "";

  const allTickets: HelpdeskTicket[] = [];
  let page = 1;
  let hasMore = true;

  while (hasMore) {
    const response = await fetch(
      `${baseUrl}/api/tickets?status=active&page=${page}&pageSize=100`,
      {
        headers: {
          Authorization: `Bearer ${apiKey}`,
          Accept: "application/json",
        },
      }
    );

    if (!response.ok) {
      throw new Error(
        `Helpdesk API returned ${response.status}: ${response.statusText}`
      );
    }

    const data = (await response.json()) as {
      tickets: HelpdeskTicket[];
      hasNextPage: boolean;
    };

    allTickets.push(...data.tickets);
    hasMore = data.hasNextPage;
    page++;
  }

  return allTickets;
}

// ---------------------------------------------------------------------------
// Transform to Microsoft Graph external item
// ---------------------------------------------------------------------------

/**
 * Transform a source ticket into a Microsoft Graph external item payload.
 *
 * Key considerations:
 *  - Item ID must be URL-safe (no #, ?, &, / characters)
 *  - Properties must match the registered schema exactly
 *  - Content should be rich, concatenated text for Copilot summarization
 *  - ACLs must use Entra object IDs for user/group types
 */
export function transformToExternalItem(
  ticket: HelpdeskTicket
): ExternalItemPayload {
  return {
    id: ticket.id,

    // ACL: grant access to all tenant users
    // [Customization point] Replace with user/group ACLs if your data is restricted
    acl: [
      {
        type: "everyone",
        value: "everyone",
        accessType: "grant",
      },
    ],

    // Structured properties — must match the schema registered in connector-config.ts
    properties: {
      ticketId: ticket.id,
      title: ticket.title,
      description: ticket.description,
      status: ticket.status,
      priority: ticket.priority,
      assignedTo: ticket.assignedTo,
      createdDate: ticket.createdDate,
      lastModifiedDate: ticket.lastModifiedDate,
      itemUrl: `https://helpdesk.contoso.com/tickets/${ticket.id}`,
      iconUrl: "https://helpdesk.contoso.com/icons/ticket.png",
      // StringCollection requires @odata.type annotation in the Graph API payload
      "tags@odata.type": "Collection(Edm.String)",
      tags: ticket.tags,
      isResolved: ticket.isResolved,
      estimatedHours: ticket.estimatedHours,
    },

    // Unstructured content for full-text search and Copilot summarization
    content: {
      value: buildContentString(ticket),
      type: "text",
    },
  };
}

// ---------------------------------------------------------------------------
// Content builder
// ---------------------------------------------------------------------------

/**
 * Build a rich, concatenated content string from multiple source fields.
 *
 * Best practices:
 *  - Lead with the most important information (title, status, priority)
 *  - Include all fields that users might search for or ask Copilot about
 *  - Use clear labels so Copilot can interpret the structure
 *  - Concatenate related fields (description + root cause + resolution + comments)
 */
function buildContentString(ticket: HelpdeskTicket): string {
  const sections: string[] = [
    `Title: ${ticket.title}`,
    `Status: ${ticket.status} | Priority: P${ticket.priority}`,
    `Assigned to: ${ticket.assignedTo}`,
    `Tags: ${ticket.tags.join(", ")}`,
    "",
    `Description: ${ticket.description}`,
  ];

  if (ticket.rootCause) {
    sections.push("", `Root Cause: ${ticket.rootCause}`);
  }

  if (ticket.resolution) {
    sections.push("", `Resolution: ${ticket.resolution}`);
  }

  if (ticket.comments && ticket.comments.length > 0) {
    sections.push("", "Comments:");
    for (const comment of ticket.comments) {
      sections.push(`  [${comment.author} - ${comment.date}]: ${comment.text}`);
    }
  }

  return sections.join("\n");
}

// ---------------------------------------------------------------------------
// Batch ingestion helper
// ---------------------------------------------------------------------------

/**
 * Fetch all items and transform them into external item payloads.
 *
 * Use this in your Azure Function crawl trigger:
 *
 * ```typescript
 * import { getExternalItems } from "./custom/dataSource";
 * import { graphService } from "./services/graphService";
 *
 * const items = await getExternalItems();
 * for (const item of items) {
 *   await graphService.putItem(connectionId, item);
 * }
 * ```
 */
export async function getExternalItems(): Promise<ExternalItemPayload[]> {
  const sourceItems = await fetchSourceItems();
  return sourceItems.map(transformToExternalItem);
}

// ---------------------------------------------------------------------------
// Incremental sync support
// ---------------------------------------------------------------------------

/**
 * Fetch only items modified since a given timestamp.
 *
 * [Customization point] Implement incremental sync if your data source
 * supports filtering by modification date. This reduces API calls and
 * Graph ingestion load on subsequent crawls.
 */
export async function fetchModifiedSince(
  since: Date
): Promise<HelpdeskTicket[]> {
  const baseUrl = process.env.DATA_SOURCE_URL || "https://api.contoso.com";
  const apiKey = process.env.DATA_SOURCE_API_KEY || "";

  const response = await fetch(
    `${baseUrl}/api/tickets?modifiedSince=${since.toISOString()}&pageSize=100`,
    {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: "application/json",
      },
    }
  );

  if (!response.ok) {
    throw new Error(
      `Helpdesk API returned ${response.status}: ${response.statusText}`
    );
  }

  const data = (await response.json()) as { tickets: HelpdeskTicket[] };
  return data.tickets;
}
