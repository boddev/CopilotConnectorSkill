// Item ingestion patterns: single items, content building, HTML content, delete, and user activities
//
// Prerequisites:
//   Maven: com.microsoft.graph:microsoft-graph:6.x, com.azure:azure-identity:1.x
//   Gradle: implementation 'com.microsoft.graph:microsoft-graph:6.+'
//           implementation 'com.azure:azure-identity:1.+'

import com.microsoft.graph.GraphServiceClient;
import com.microsoft.graph.models.externalconnectors.*;
import com.microsoft.graph.models.externalconnectors.Properties;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;

/**
 * Demonstrates item ingestion patterns for a Copilot Connector.
 * Covers simple text items, HTML content, content building, deletion,
 * and user activity signals.
 */
public class ItemIngestion {

    private final GraphServiceClient graphClient;
    private final String connectionId;

    public ItemIngestion(GraphServiceClient graphClient, String connectionId) {
        this.graphClient = graphClient;
        this.connectionId = connectionId;
    }

    /**
     * Ingest a single item with text content and everyone ACL.
     */
    public void ingestSimpleItem() {
        ExternalItem item = new ExternalItem();
        item.setId("TICKET-001"); // Must be URL-safe (no #, ?, &, /)

        Acl acl = new Acl();
        acl.setType(AclType.Everyone);
        acl.setValue("everyone");
        acl.setAccessType(AccessType.Grant);
        item.setAcl(List.of(acl));

        Properties props = new Properties();
        HashMap<String, Object> additionalData = new HashMap<>();
        additionalData.put("ticketId", "TICKET-001");
        additionalData.put("title", "Payment Gateway Timeout");
        additionalData.put("status", "Open");
        additionalData.put("priority", 1);
        additionalData.put("assignedTo", "john.doe@contoso.com");
        additionalData.put("createdDate", OffsetDateTime.parse("2026-03-15T10:30:00Z"));
        additionalData.put("lastModifiedDate", OffsetDateTime.now());
        additionalData.put("itemUrl", "https://helpdesk.contoso.com/tickets/TICKET-001");
        additionalData.put("iconUrl", "https://helpdesk.contoso.com/icons/ticket.png");
        // StringCollection requires @odata.type annotation
        additionalData.put("tags@odata.type", "Collection(Edm.String)");
        additionalData.put("tags", List.of("payments", "infrastructure", "P1"));
        props.setAdditionalData(additionalData);
        item.setProperties(props);

        ExternalItemContent content = new ExternalItemContent();
        content.setValue(buildTicketContent(
                "Payment Gateway Timeout",
                "Open",
                "P1",
                "John Doe",
                "Payment gateway returning 504 errors during peak hours.",
                "Database connection pool exhaustion under load.",
                "Increased pool size from 100 to 250 connections.",
                null));
        content.setType(ExternalItemContentType.Text);
        item.setContent(content);

        // PUT is an upsert — creates or updates the item
        graphClient.external().connections()
                .byExternalConnectionId(connectionId)
                .items()
                .byExternalItemId("TICKET-001")
                .put(item);
    }

    /**
     * Build rich, concatenated content from multiple source fields.
     * Lead with the most important information for Copilot summarization.
     *
     * @param title       ticket title
     * @param status      current status
     * @param priority    priority level (e.g., P1, P2)
     * @param assignee    person assigned
     * @param description problem description
     * @param rootCause   root cause analysis (nullable)
     * @param resolution  resolution or workaround (nullable)
     * @param comments    list of comment records (nullable)
     * @return formatted content string
     */
    public static String buildTicketContent(
            String title, String status, String priority, String assignee,
            String description, String rootCause, String resolution,
            List<CommentRecord> comments) {

        var sb = new StringBuilder();
        sb.append("Title: ").append(title).append("\n");
        sb.append("Status: ").append(status).append(" | Priority: ").append(priority).append("\n");
        sb.append("Assigned to: ").append(assignee).append("\n");
        sb.append("\n");
        sb.append("Description: ").append(description).append("\n");

        if (rootCause != null && !rootCause.isBlank()) {
            sb.append("\nRoot Cause: ").append(rootCause).append("\n");
        }

        if (resolution != null && !resolution.isBlank()) {
            sb.append("\nResolution: ").append(resolution).append("\n");
        }

        if (comments != null) {
            sb.append("\nComments:\n");
            for (var comment : comments) {
                sb.append("  [").append(comment.author())
                  .append(" - ").append(comment.date())
                  .append("]: ").append(comment.text()).append("\n");
            }
        }

        return sb.toString();
    }

    /** A single comment on a helpdesk ticket. */
    public record CommentRecord(String author, String date, String text) {}

    /**
     * Ingest an item with HTML content (for rich documents).
     */
    public void ingestHtmlItem() {
        ExternalItem item = new ExternalItem();
        item.setId("WIKI-042");

        Acl acl = new Acl();
        acl.setType(AclType.Everyone);
        acl.setValue("everyone");
        acl.setAccessType(AccessType.Grant);
        item.setAcl(List.of(acl));

        Properties props = new Properties();
        HashMap<String, Object> additionalData = new HashMap<>();
        additionalData.put("title", "VPN Setup Guide");
        additionalData.put("itemUrl", "https://wiki.contoso.com/articles/vpn-setup");
        additionalData.put("iconUrl", "https://wiki.contoso.com/icons/wiki.png");
        props.setAdditionalData(additionalData);
        item.setProperties(props);

        ExternalItemContent content = new ExternalItemContent();
        content.setValue("""
                <html><body>
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
                </body></html>""");
        content.setType(ExternalItemContentType.Html);
        item.setContent(content);

        graphClient.external().connections()
                .byExternalConnectionId(connectionId)
                .items()
                .byExternalItemId("WIKI-042")
                .put(item);
    }

    /**
     * Delete an item from the index.
     *
     * @param itemId the external item ID to delete
     */
    public void deleteItem(String itemId) {
        graphClient.external().connections()
                .byExternalConnectionId(connectionId)
                .items()
                .byExternalItemId(itemId)
                .delete();
    }

    /**
     * Send user activities to boost item relevance.
     * Supported types: created, modified, commented, viewed.
     * Activities older than 7 days don't surface in the M365 app.
     *
     * @param itemId      the external item ID
     * @param userEntraId the Entra ID (GUID) of the user who performed the action
     */
    public void sendActivity(String itemId, String userEntraId) {
        ExternalActivity activity = new ExternalActivity();
        activity.setOdataType("#microsoft.graph.externalConnectors.externalActivity");
        activity.setType(ExternalActivityType.Viewed);
        activity.setStartDateTime(OffsetDateTime.now());

        Identity performedBy = new Identity();
        performedBy.setOdataType("#microsoft.graph.externalConnectors.identity");
        performedBy.setId(userEntraId);
        performedBy.setType(IdentityType.User);
        activity.setPerformedBy(performedBy);

        List<ExternalActivity> activities = new LinkedList<>();
        activities.add(activity);

        var requestBody = new com.microsoft.graph.external.connections.item.items.item
                .microsoftgraphexternalconnectorsaddactivities.AddActivitiesPostRequestBody();
        requestBody.setActivities(activities);

        graphClient.external().connections()
                .byExternalConnectionId(connectionId)
                .items()
                .byExternalItemId(itemId)
                .microsoftGraphExternalConnectorsAddActivities()
                .post(requestBody);
    }
}
