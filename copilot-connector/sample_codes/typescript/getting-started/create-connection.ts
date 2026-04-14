// Complete TypeScript example: Create a Copilot Connector end-to-end
// Demonstrates: authenticate → create connection → register schema →
//   poll schema status → ingest item → configure urlToItemResolver
//
// Prerequisites: npm install @microsoft/microsoft-graph-client @azure/identity

import { Client } from "@microsoft/microsoft-graph-client";
import { ClientSecretCredential } from "@azure/identity";
import { TokenCredentialAuthenticationProvider } from
  "@microsoft/microsoft-graph-client/authProviders/azureTokenCredentials";

// --- Step 1: Authenticate with Microsoft Graph ---

const credential = new ClientSecretCredential(
  "YOUR_TENANT_ID",
  "YOUR_CLIENT_ID",
  "YOUR_CLIENT_SECRET"
);

const authProvider = new TokenCredentialAuthenticationProvider(credential, {
  scopes: ["https://graph.microsoft.com/.default"],
});

const graphClient = Client.initWithMiddleware({ authProvider });

// --- Step 2: Create the connection ---

const connection = await graphClient.api("/external/connections").post({
  id: "contosohelpdesk",       // 3-128 alphanumeric chars, unique per tenant
  name: "Contoso Helpdesk",
  description:
    "Internal IT helpdesk tickets from the Contoso Helpdesk system. " +
    "Contains incident reports, service requests, and change requests. " +
    "Used by IT support staff and employees to track and resolve technical issues.",
});

console.log(`Connection created: ${connection.id}`);

// --- Step 3: Register the schema ---

await graphClient
  .api("/external/connections/contosohelpdesk/schema")
  .patch({
    baseType: "microsoft.graph.externalItem",
    properties: [
      {
        name: "ticketId",
        type: "String",
        isQueryable: true,
        isRetrievable: true,
        isExactMatchRequired: true,
        aliases: ["ID"],
      },
      {
        name: "title",
        type: "String",
        isSearchable: true,
        isQueryable: true,
        isRetrievable: true,
        labels: ["title"],
      },
      {
        name: "status",
        type: "String",
        isQueryable: true,
        isRetrievable: true,
        isRefinable: true,
        aliases: ["state"],
      },
      {
        name: "priority",
        type: "Int64",
        isQueryable: true,
        isRetrievable: true,
        isRefinable: true,
      },
      {
        name: "assignedTo",
        type: "String",
        isSearchable: true,
        isQueryable: true,
        isRetrievable: true,
        aliases: ["assignee", "owner"],
      },
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
    ],
  });

// --- Step 3b: Poll until schema registration completes ---

console.log("Schema registration started. Polling for completion...");

while (true) {
  const schema = await graphClient
    .api("/external/connections/contosohelpdesk/schema")
    .get();

  const state: string | undefined = schema?.status?.state;
  console.log(`Schema status: ${state}`);

  if (state === "completed") break;

  if (state === "failed") {
    throw new Error("Schema registration failed");
  }

  await new Promise((resolve) => setTimeout(resolve, 30_000));
}

// --- Step 4: Ingest items ---

await graphClient
  .api("/external/connections/contosohelpdesk/items/TICKET-001")
  .put({
    acl: [
      {
        type: "everyone",
        value: "everyone",
        accessType: "grant",
      },
    ],
    properties: {
      ticketId: "TICKET-001",
      title: "VPN Connection Drops After Windows Update",
      status: "Open",
      priority: 2,
      assignedTo: "jane.smith@contoso.com",
      createdDate: "2026-03-15T10:30:00Z",
      lastModifiedDate: "2026-03-20T14:15:00Z",
      itemUrl: "https://helpdesk.contoso.com/tickets/TICKET-001",
      iconUrl: "https://helpdesk.contoso.com/icons/ticket.png",
    },
    content: {
      value:
        "Title: VPN Connection Drops After Windows Update\n" +
        "Status: Open | Priority: P2\n" +
        "Assigned to: Jane Smith\n\n" +
        "Description: Multiple users report VPN disconnections after installing " +
        "KB5034441 Windows update. Affects GlobalProtect VPN client v6.1.\n\n" +
        "Root Cause: Windows update modified network adapter settings, causing " +
        "MTU mismatch with VPN tunnel configuration.\n\n" +
        'Workaround: Reset network adapter MTU to 1400 via \'netsh interface ipv4 ' +
        'set subinterface "Ethernet" mtu=1400 store=persistent\'',
      type: "text",
    },
  });

console.log("Item ingested successfully!");

// --- Step 5: Configure urlToItemResolver ---

await graphClient.api("/external/connections/contosohelpdesk").patch({
  activitySettings: {
    urlToItemResolvers: [
      {
        "@odata.type": "#microsoft.graph.externalConnectors.itemIdResolver",
        urlMatchInfo: {
          baseUrls: ["https://helpdesk.contoso.com"],
          urlPattern: "/tickets/(?<itemId>[A-Za-z0-9-]+)",
        },
      },
    ],
  },
});

console.log("Connector setup complete!");
console.log(
  "Next: Enable inline results in M365 Admin Center > " +
    "Search & intelligence > Verticals"
);
