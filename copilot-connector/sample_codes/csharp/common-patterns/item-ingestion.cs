// Item ingestion patterns: single items, content building, and update/delete
using System.Text;
using Microsoft.Graph;
using Microsoft.Graph.Models.ExternalConnectors;

public class ItemIngestion
{
    private readonly GraphServiceClient _graphClient;
    private readonly string _connectionId;

    public ItemIngestion(GraphServiceClient graphClient, string connectionId)
    {
        _graphClient = graphClient;
        _connectionId = connectionId;
    }

    /// <summary>
    /// Ingest a single item with text content and everyone ACL.
    /// </summary>
    public async Task IngestSimpleItemAsync()
    {
        var item = new ExternalItem
        {
            Id = "TICKET-001",  // Must be URL-safe (no #, ?, &, /)
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
                    { "title", "Payment Gateway Timeout" },
                    { "status", "Open" },
                    { "priority", 1 },
                    { "assignedTo", "john.doe@contoso.com" },
                    { "createdDate", DateTimeOffset.Parse("2026-03-15T10:30:00Z") },
                    { "lastModifiedDate", DateTimeOffset.UtcNow },
                    { "itemUrl", "https://helpdesk.contoso.com/tickets/TICKET-001" },
                    { "iconUrl", "https://helpdesk.contoso.com/icons/ticket.png" },
                    // StringCollection requires @odata.type annotation
                    { "tags@odata.type", "Collection(Edm.String)" },
                    { "tags", new List<string> { "payments", "infrastructure", "P1" } }
                }
            },
            Content = new ExternalItemContent
            {
                Value = BuildTicketContent(
                    title: "Payment Gateway Timeout",
                    status: "Open",
                    priority: "P1",
                    assignee: "John Doe",
                    description: "Payment gateway returning 504 errors during peak hours.",
                    rootCause: "Database connection pool exhaustion under load.",
                    resolution: "Increased pool size from 100 to 250 connections."
                ),
                Type = ExternalItemContentType.Text
            }
        };

        // PUT is an upsert — creates or updates the item
        await _graphClient.External.Connections[_connectionId]
            .Items["TICKET-001"]
            .PutAsync(item);
    }

    /// <summary>
    /// Build rich, concatenated content from multiple source fields.
    /// Lead with the most important information for Copilot summarization.
    /// </summary>
    public static string BuildTicketContent(
        string title, string status, string priority, string assignee,
        string description, string? rootCause = null, string? resolution = null,
        IEnumerable<(string Author, DateTime Date, string Text)>? comments = null)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"Title: {title}");
        sb.AppendLine($"Status: {status} | Priority: {priority}");
        sb.AppendLine($"Assigned to: {assignee}");
        sb.AppendLine();
        sb.AppendLine($"Description: {description}");

        if (!string.IsNullOrEmpty(rootCause))
            sb.AppendLine($"\nRoot Cause: {rootCause}");

        if (!string.IsNullOrEmpty(resolution))
            sb.AppendLine($"\nResolution: {resolution}");

        if (comments != null)
        {
            sb.AppendLine("\nComments:");
            foreach (var (author, date, text) in comments)
                sb.AppendLine($"  [{author} - {date:yyyy-MM-dd}]: {text}");
        }

        return sb.ToString();
    }

    /// <summary>
    /// Ingest an item with HTML content (for rich documents).
    /// </summary>
    public async Task IngestHtmlItemAsync()
    {
        var item = new ExternalItem
        {
            Id = "WIKI-042",
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
                    { "title", "VPN Setup Guide" },
                    { "itemUrl", "https://wiki.contoso.com/articles/vpn-setup" },
                    { "iconUrl", "https://wiki.contoso.com/icons/wiki.png" }
                }
            },
            Content = new ExternalItemContent
            {
                Value = @"<html><body>
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
                    </body></html>",
                Type = ExternalItemContentType.Html
            }
        };

        await _graphClient.External.Connections[_connectionId]
            .Items["WIKI-042"]
            .PutAsync(item);
    }

    /// <summary>
    /// Delete an item from the index.
    /// </summary>
    public async Task DeleteItemAsync(string itemId)
    {
        await _graphClient.External.Connections[_connectionId]
            .Items[itemId]
            .DeleteAsync();
    }

    /// <summary>
    /// Send user activities to boost item relevance.
    /// Supported types: created, modified, commented, viewed
    /// Activities older than 7 days don't surface in the M365 app.
    /// </summary>
    public async Task SendActivityAsync(string itemId, string userEntraId)
    {
        var activities = new List<ExternalActivity>
        {
            new ExternalActivity
            {
                OdataType = "#microsoft.graph.externalConnectors.externalActivity",
                Type = ExternalActivityType.Viewed,
                StartDateTime = DateTimeOffset.UtcNow,
                PerformedBy = new Identity
                {
                    OdataType = "#microsoft.graph.externalConnectors.identity",
                    Id = userEntraId,
                    Type = IdentityType.User
                }
            }
        };

        await _graphClient.External.Connections[_connectionId]
            .Items[itemId]
            .MicrosoftGraphExternalConnectorsAddActivities
            .PostAsync(new() { Activities = activities });
    }
}
