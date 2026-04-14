// Schema registration with status polling
// Shows all property types, attributes, semantic labels, and aliases
//
// Prerequisites: npm install @microsoft/microsoft-graph-client @azure/identity

import { Client } from "@microsoft/microsoft-graph-client";

/** A single property in a Microsoft Graph external connector schema. */
interface SchemaProperty {
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

/** The full schema payload sent to the Graph API. */
interface SchemaDefinition {
  baseType: string;
  properties: SchemaProperty[];
}

/** Status returned when polling schema registration. */
interface SchemaStatus {
  status?: {
    state?: string;
  };
}

/**
 * Manages schema registration and status polling for an external connection.
 */
class SchemaRegistration {
  constructor(
    private readonly graphClient: Client,
    private readonly connectionId: string
  ) {}

  /**
   * Register a schema with all supported property types and attributes.
   * Schema registration is async — the API returns 202 Accepted.
   */
  async registerSchema(): Promise<void> {
    const schema: SchemaDefinition = {
      baseType: "microsoft.graph.externalItem",
      properties: [
        // Searchable + Queryable + Retrievable — for full-text and filtered search
        {
          name: "title",
          type: "String",
          isSearchable: true,
          isQueryable: true,
          isRetrievable: true,
          labels: ["title"],
        },
        // Searchable text (but NOT refinable — they are mutually exclusive)
        {
          name: "description",
          type: "String",
          isSearchable: true,
          isQueryable: false,
          isRetrievable: false,
        },
        // Refinable (but NOT searchable — mutually exclusive)
        // Must be set in initial schema — cannot add refinable via update
        {
          name: "status",
          type: "String",
          isSearchable: false,
          isQueryable: true,
          isRetrievable: true,
          isRefinable: true,
          aliases: ["state"],
        },
        // Numeric refinable property
        {
          name: "priority",
          type: "Int64",
          isQueryable: true,
          isRetrievable: true,
          isRefinable: true,
        },
        // ExactMatchRequired — only on non-searchable properties
        {
          name: "ticketId",
          type: "String",
          isSearchable: false,
          isQueryable: true,
          isRetrievable: true,
          isExactMatchRequired: true,
          aliases: ["ID", "incidentNumber"],
        },
        // StringCollection with refinable + exact match
        {
          name: "tags",
          type: "StringCollection",
          isQueryable: true,
          isRetrievable: true,
          isRefinable: true,
          isExactMatchRequired: true,
          aliases: ["labels", "categories"],
        },
        // DateTime properties with semantic labels
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
        // URL and icon — critical for Copilot surfacing
        {
          name: "itemUrl",
          type: "String",
          isRetrievable: true,
          labels: ["url"],
        },
        {
          name: "iconUrl",
          type: "String",
          isRetrievable: true,
          labels: ["iconUrl"],
        },
        // Boolean property
        {
          name: "isResolved",
          type: "Boolean",
          isQueryable: true,
          isRetrievable: true,
        },
        // Double property
        {
          name: "estimatedHours",
          type: "Double",
          isQueryable: true,
          isRetrievable: true,
        },
      ],
    };

    // Schema registration is async — returns 202 Accepted
    await this.graphClient
      .api(`/external/connections/${this.connectionId}/schema`)
      .patch(schema);

    console.log("Schema registration started.");
  }

  /**
   * Poll schema status until completed or failed.
   * Schema registration can take up to 10 minutes.
   *
   * @param timeoutMs - Maximum time to wait in milliseconds (default: 15 minutes)
   * @returns `true` if schema registration completed successfully
   */
  async waitForSchema(timeoutMs = 15 * 60 * 1000): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;

    while (Date.now() < deadline) {
      const schema: SchemaStatus = await this.graphClient
        .api(`/external/connections/${this.connectionId}/schema`)
        .get();

      const state = schema?.status?.state;
      console.log(`  Schema status: ${state}`);

      if (state === "completed") return true;

      if (state === "failed") {
        console.error("Schema registration failed.");
        return false;
      }

      await new Promise((resolve) => setTimeout(resolve, 30_000));
    }

    throw new Error("Schema registration timed out");
  }
}

export { SchemaRegistration, SchemaProperty, SchemaDefinition, SchemaStatus };
