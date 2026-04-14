// Complete C# example: Create a Copilot Connector end-to-end
// Prerequisites: Microsoft.Graph NuGet package, Azure.Identity NuGet package

using Azure.Identity;
using Microsoft.Graph;
using Microsoft.Graph.Models.ExternalConnectors;

// --- Step 1: Authenticate with Microsoft Graph ---
var credential = new ClientSecretCredential(
    tenantId: "YOUR_TENANT_ID",
    clientId: "YOUR_CLIENT_ID",
    clientSecret: "YOUR_CLIENT_SECRET"
);
var graphClient = new GraphServiceClient(credential);

// --- Step 2: Create the connection ---
var connection = new ExternalConnection
{
    Id = "contosohelpdesk",      // 3-128 alphanumeric chars, unique per tenant
    Name = "Contoso Helpdesk",
    Description = "Internal IT helpdesk tickets from the Contoso Helpdesk system. " +
                  "Contains incident reports, service requests, and change requests. " +
                  "Used by IT support staff and employees to track and resolve technical issues."
};

var createdConnection = await graphClient.External.Connections
    .PostAsync(connection);

Console.WriteLine($"Connection created: {createdConnection?.Id}");

// --- Step 3: Register the schema ---
var schema = new Schema
{
    BaseType = "microsoft.graph.externalItem",
    Properties = new List<Property>
    {
        new Property
        {
            Name = "ticketId",
            Type = PropertyType.String,
            IsQueryable = true,
            IsRetrievable = true,
            IsExactMatchRequired = true,
            Aliases = new List<string> { "ID" }
        },
        new Property
        {
            Name = "title",
            Type = PropertyType.String,
            IsSearchable = true,
            IsQueryable = true,
            IsRetrievable = true,
            Labels = new List<Label?> { Label.Title }
        },
        new Property
        {
            Name = "status",
            Type = PropertyType.String,
            IsQueryable = true,
            IsRetrievable = true,
            IsRefinable = true,
            Aliases = new List<string> { "state" }
        },
        new Property
        {
            Name = "priority",
            Type = PropertyType.Int64,
            IsQueryable = true,
            IsRetrievable = true,
            IsRefinable = true
        },
        new Property
        {
            Name = "assignedTo",
            Type = PropertyType.String,
            IsSearchable = true,
            IsQueryable = true,
            IsRetrievable = true,
            Aliases = new List<string> { "assignee", "owner" }
        },
        new Property
        {
            Name = "createdDate",
            Type = PropertyType.DateTime,
            IsQueryable = true,
            IsRetrievable = true,
            IsRefinable = true,
            Labels = new List<Label?> { Label.CreatedDateTime }
        },
        new Property
        {
            Name = "lastModifiedDate",
            Type = PropertyType.DateTime,
            IsQueryable = true,
            IsRetrievable = true,
            Labels = new List<Label?> { Label.LastModifiedDateTime }
        },
        new Property
        {
            Name = "itemUrl",
            Type = PropertyType.String,
            IsRetrievable = true,
            Labels = new List<Label?> { Label.Url }
        },
        new Property
        {
            Name = "iconUrl",
            Type = PropertyType.String,
            IsRetrievable = true,
            Labels = new List<Label?> { Label.IconUrl }
        }
    }
};

await graphClient.External.Connections["contosohelpdesk"].Schema
    .PatchAsync(schema);

// --- Step 3b: Poll until schema registration completes ---
Console.WriteLine("Schema registration started. Polling for completion...");
while (true)
{
    var currentSchema = await graphClient.External.Connections["contosohelpdesk"].Schema
        .GetAsync();

    var status = currentSchema?.Status?.State;
    Console.WriteLine($"Schema status: {status}");

    if (status == ConnectionOperationStatus.Completed)
        break;

    if (status == ConnectionOperationStatus.Failed)
        throw new Exception("Schema registration failed");

    await Task.Delay(TimeSpan.FromSeconds(30));
}

// --- Step 4: Ingest items ---
var externalItem = new ExternalItem
{
    Id = "TICKET-001",
    Acl = new List<AclEntry>
    {
        new AclEntry
        {
            Type = AclType.Everyone,
            Value = "everyone",
            AccessType = AccessType.Grant
        }
    },
    Properties = new Properties
    {
        AdditionalData = new Dictionary<string, object>
        {
            { "ticketId", "TICKET-001" },
            { "title", "VPN Connection Drops After Windows Update" },
            { "status", "Open" },
            { "priority", 2 },
            { "assignedTo", "jane.smith@contoso.com" },
            { "createdDate", DateTimeOffset.Parse("2026-03-15T10:30:00Z") },
            { "lastModifiedDate", DateTimeOffset.Parse("2026-03-20T14:15:00Z") },
            { "itemUrl", "https://helpdesk.contoso.com/tickets/TICKET-001" },
            { "iconUrl", "https://helpdesk.contoso.com/icons/ticket.png" }
        }
    },
    Content = new ExternalItemContent
    {
        Value = "Title: VPN Connection Drops After Windows Update\n" +
                "Status: Open | Priority: P2\n" +
                "Assigned to: Jane Smith\n\n" +
                "Description: Multiple users report VPN disconnections after installing " +
                "KB5034441 Windows update. Affects GlobalProtect VPN client v6.1.\n\n" +
                "Root Cause: Windows update modified network adapter settings, causing " +
                "MTU mismatch with VPN tunnel configuration.\n\n" +
                "Workaround: Reset network adapter MTU to 1400 via 'netsh interface ipv4 " +
                "set subinterface \"Ethernet\" mtu=1400 store=persistent'",
        Type = ExternalItemContentType.Text
    }
};

await graphClient.External.Connections["contosohelpdesk"]
    .Items["TICKET-001"]
    .PutAsync(externalItem);

Console.WriteLine("Item ingested successfully!");

// --- Step 5: Configure urlToItemResolver ---
var activitySettings = new ActivitySettings
{
    UrlToItemResolvers = new List<UrlToItemResolverBase>
    {
        new ItemIdResolver
        {
            UrlMatchInfo = new UrlMatchInfo
            {
                BaseUrls = new List<string> { "https://helpdesk.contoso.com" },
                UrlPattern = "/tickets/(?<itemId>[A-Za-z0-9-]+)"
            }
        }
    }
};

await graphClient.External.Connections["contosohelpdesk"]
    .PatchAsync(new ExternalConnection { ActivitySettings = activitySettings });

Console.WriteLine("Connector setup complete!");
Console.WriteLine("Next: Enable inline results in M365 Admin Center > Search & intelligence > Verticals");
