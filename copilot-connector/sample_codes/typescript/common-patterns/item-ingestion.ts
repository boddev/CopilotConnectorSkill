// Item ingestion patterns: single items, content building, HTML, delete, and activities
//
// Prerequisites: npm install @microsoft/microsoft-graph-client @azure/identity

import { Client } from "@microsoft/microsoft-graph-client";

/** ACL entry controlling who can see an item. */
interface AclEntry {
  type: "everyone" | "everyoneExceptGuests" | "user" | "group" | "externalGroup";
  value: string;
  accessType: "grant" | "deny";
}

/** An external item to ingest into the Microsoft Graph index. */
interface ExternalItem {
  acl: AclEntry[];
  properties: Record<string, unknown>;
  content: {
    value: string;
    type: "text" | "html";
  };
}

/** A comment attached to a helpdesk ticket. */
interface TicketComment {
  author: string;
  date: Date;
  text: string;
}

/**
 * Handles item ingestion for an external connection.
 */
class ItemIngestion {
  constructor(
    private readonly graphClient: Client,
    private readonly connectionId: string
  ) {}

  /**
   * Ingest a single item with text content and everyone ACL.
   */
  async ingestSimpleItem(): Promise<void> {
    const item: ExternalItem = {
      acl: [
        {
          type: "everyone",
          value: "everyone",
          accessType: "grant",
        },
      ],
      properties: {
        ticketId: "TICKET-001",
        title: "Payment Gateway Timeout",
        status: "Open",
        priority: 1,
        assignedTo: "john.doe@contoso.com",
        createdDate: "2026-03-15T10:30:00Z",
        lastModifiedDate: new Date().toISOString(),
        itemUrl: "https://helpdesk.contoso.com/tickets/TICKET-001",
        iconUrl: "https://helpdesk.contoso.com/icons/ticket.png",
        // StringCollection requires @odata.type annotation
        "tags@odata.type": "Collection(Edm.String)",
        tags: ["payments", "infrastructure", "P1"],
      },
      content: {
        value: buildTicketContent({
          title: "Payment Gateway Timeout",
          status: "Open",
          priority: "P1",
          assignee: "John Doe",
          description:
            "Payment gateway returning 504 errors during peak hours.",
          rootCause: "Database connection pool exhaustion under load.",
          resolution: "Increased pool size from 100 to 250 connections.",
        }),
        type: "text",
      },
    };

    // PUT is an upsert — creates or updates the item
    await this.graphClient
      .api(
        `/external/connections/${this.connectionId}/items/${item.properties.ticketId}`
      )
      .put(item);
  }

  /**
   * Ingest an item with HTML content (for rich documents).
   */
  async ingestHtmlItem(): Promise<void> {
    const item: ExternalItem = {
      acl: [
        {
          type: "everyone",
          value: "everyone",
          accessType: "grant",
        },
      ],
      properties: {
        title: "VPN Setup Guide",
        itemUrl: "https://wiki.contoso.com/articles/vpn-setup",
        iconUrl: "https://wiki.contoso.com/icons/wiki.png",
      },
      content: {
        value: `<html><body>
          <h1>VPN Setup Guide</h1>
          <h2>Prerequisites</h2>
          <ul>
            <li>Windows 10/11 or macOS 12+</li>
            <li>GlobalProtect client v6.1+</li>
          </ul>
          <h2>Installation Steps</h2>
          <ol>
            <li>Download GlobalProtect from the internal portal</li>
            <li>Run the installer with admin privileges</li>
            <li>Enter portal address: vpn.contoso.com</li>
          </ol>
        </body></html>`,
        type: "html",
      },
    };

    await this.graphClient
      .api(`/external/connections/${this.connectionId}/items/WIKI-042`)
      .put(item);
  }

  /**
   * Delete an item from the index.
   */
  async deleteItem(itemId: string): Promise<void> {
    await this.graphClient
      .api(`/external/connections/${this.connectionId}/items/${itemId}`)
      .delete();
  }

  /**
   * Send user activities to boost item relevance.
   * Supported types: created, modified, commented, viewed.
   * Activities older than 7 days don't surface in the M365 app.
   */
  async sendActivity(itemId: string, userEntraId: string): Promise<void> {
    await this.graphClient
      .api(
        `/external/connections/${this.connectionId}/items/${itemId}` +
          `/microsoft.graph.externalConnectors.externalItem/addActivities`
      )
      .post({
        activities: [
          {
            "@odata.type":
              "#microsoft.graph.externalConnectors.externalActivity",
            type: "viewed",
            startDateTime: new Date().toISOString(),
            performedBy: {
              "@odata.type":
                "#microsoft.graph.externalConnectors.identity",
              id: userEntraId,
              type: "user",
            },
          },
        ],
      });
  }
}

/**
 * Build rich, concatenated content from multiple source fields.
 * Lead with the most important information for Copilot summarization.
 */
function buildTicketContent(params: {
  title: string;
  status: string;
  priority: string;
  assignee: string;
  description: string;
  rootCause?: string;
  resolution?: string;
  comments?: TicketComment[];
}): string {
  const lines: string[] = [
    `Title: ${params.title}`,
    `Status: ${params.status} | Priority: ${params.priority}`,
    `Assigned to: ${params.assignee}`,
    "",
    `Description: ${params.description}`,
  ];

  if (params.rootCause) {
    lines.push("", `Root Cause: ${params.rootCause}`);
  }

  if (params.resolution) {
    lines.push("", `Resolution: ${params.resolution}`);
  }

  if (params.comments?.length) {
    lines.push("", "Comments:");
    for (const c of params.comments) {
      const date = c.date.toISOString().slice(0, 10);
      lines.push(`  [${c.author} - ${date}]: ${c.text}`);
    }
  }

  return lines.join("\n");
}

export { ItemIngestion, buildTicketContent, ExternalItem, AclEntry, TicketComment };
