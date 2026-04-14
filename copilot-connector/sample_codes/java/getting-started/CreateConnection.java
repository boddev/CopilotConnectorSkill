// Complete Java example: Create a Copilot Connector end-to-end
// Demonstrates: authenticate → create connection → register schema → poll status → ingest item → configure urlToItemResolver
//
// Prerequisites:
//   Maven: com.microsoft.graph:microsoft-graph:6.x, com.azure:azure-identity:1.x
//   Gradle: implementation 'com.microsoft.graph:microsoft-graph:6.+'
//           implementation 'com.azure:azure-identity:1.+'
//
// Required app permissions (Application): ExternalConnection.ReadWrite.All, ExternalItem.ReadWrite.All

import com.azure.identity.ClientSecretCredential;
import com.azure.identity.ClientSecretCredentialBuilder;
import com.microsoft.graph.GraphServiceClient;
import com.microsoft.graph.models.externalconnectors.*;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;

public class CreateConnection {

    public static void main(String[] args) throws Exception {

        // --- Step 1: Authenticate with Microsoft Graph ---
        ClientSecretCredential credential = new ClientSecretCredentialBuilder()
                .tenantId("YOUR_TENANT_ID")
                .clientId("YOUR_CLIENT_ID")
                .clientSecret("YOUR_CLIENT_SECRET")
                .build();

        GraphServiceClient graphClient = new GraphServiceClient(credential);

        // --- Step 2: Create the connection ---
        ExternalConnection connection = new ExternalConnection();
        connection.setId("contosohelpdesk");       // 3-128 alphanumeric chars, unique per tenant
        connection.setName("Contoso Helpdesk");
        connection.setDescription(
                "Internal IT helpdesk tickets from the Contoso Helpdesk system. " +
                "Contains incident reports, service requests, and change requests. " +
                "Used by IT support staff and employees to track and resolve technical issues.");

        ExternalConnection createdConnection = graphClient.external().connections()
                .post(connection);

        System.out.println("Connection created: " + createdConnection.getId());

        // --- Step 3: Register the schema ---
        Schema schema = new Schema();
        schema.setBaseType("microsoft.graph.externalItem");

        List<Property> properties = new LinkedList<>();

        Property ticketIdProp = new Property();
        ticketIdProp.setName("ticketId");
        ticketIdProp.setType(PropertyType.String);
        ticketIdProp.setIsQueryable(true);
        ticketIdProp.setIsRetrievable(true);
        ticketIdProp.setIsExactMatchRequired(true);
        ticketIdProp.setAliases(List.of("ID"));
        properties.add(ticketIdProp);

        Property titleProp = new Property();
        titleProp.setName("title");
        titleProp.setType(PropertyType.String);
        titleProp.setIsSearchable(true);
        titleProp.setIsQueryable(true);
        titleProp.setIsRetrievable(true);
        titleProp.setLabels(List.of(Label.Title));
        properties.add(titleProp);

        Property statusProp = new Property();
        statusProp.setName("status");
        statusProp.setType(PropertyType.String);
        statusProp.setIsQueryable(true);
        statusProp.setIsRetrievable(true);
        statusProp.setIsRefinable(true);
        statusProp.setAliases(List.of("state"));
        properties.add(statusProp);

        Property priorityProp = new Property();
        priorityProp.setName("priority");
        priorityProp.setType(PropertyType.Int64);
        priorityProp.setIsQueryable(true);
        priorityProp.setIsRetrievable(true);
        priorityProp.setIsRefinable(true);
        properties.add(priorityProp);

        Property assignedToProp = new Property();
        assignedToProp.setName("assignedTo");
        assignedToProp.setType(PropertyType.String);
        assignedToProp.setIsSearchable(true);
        assignedToProp.setIsQueryable(true);
        assignedToProp.setIsRetrievable(true);
        assignedToProp.setAliases(List.of("assignee", "owner"));
        properties.add(assignedToProp);

        Property createdDateProp = new Property();
        createdDateProp.setName("createdDate");
        createdDateProp.setType(PropertyType.DateTime);
        createdDateProp.setIsQueryable(true);
        createdDateProp.setIsRetrievable(true);
        createdDateProp.setIsRefinable(true);
        createdDateProp.setLabels(List.of(Label.CreatedDateTime));
        properties.add(createdDateProp);

        Property lastModifiedDateProp = new Property();
        lastModifiedDateProp.setName("lastModifiedDate");
        lastModifiedDateProp.setType(PropertyType.DateTime);
        lastModifiedDateProp.setIsQueryable(true);
        lastModifiedDateProp.setIsRetrievable(true);
        lastModifiedDateProp.setLabels(List.of(Label.LastModifiedDateTime));
        properties.add(lastModifiedDateProp);

        Property itemUrlProp = new Property();
        itemUrlProp.setName("itemUrl");
        itemUrlProp.setType(PropertyType.String);
        itemUrlProp.setIsRetrievable(true);
        itemUrlProp.setLabels(List.of(Label.Url));
        properties.add(itemUrlProp);

        Property iconUrlProp = new Property();
        iconUrlProp.setName("iconUrl");
        iconUrlProp.setType(PropertyType.String);
        iconUrlProp.setIsRetrievable(true);
        iconUrlProp.setLabels(List.of(Label.IconUrl));
        properties.add(iconUrlProp);

        schema.setProperties(properties);

        // Schema registration is async — returns 202 Accepted
        graphClient.external().connections()
                .byExternalConnectionId("contosohelpdesk")
                .schema()
                .patch(schema);

        // --- Step 3b: Poll until schema registration completes ---
        System.out.println("Schema registration started. Polling for completion...");
        while (true) {
            Schema currentSchema = graphClient.external().connections()
                    .byExternalConnectionId("contosohelpdesk")
                    .schema()
                    .get();

            ConnectionOperationStatus status = currentSchema.getStatus().getState();
            System.out.println("Schema status: " + status);

            if (status == ConnectionOperationStatus.Completed) {
                break;
            }
            if (status == ConnectionOperationStatus.Failed) {
                throw new RuntimeException("Schema registration failed");
            }

            Thread.sleep(30_000); // 30 seconds
        }

        // --- Step 4: Ingest items ---
        ExternalItem externalItem = new ExternalItem();
        externalItem.setId("TICKET-001");

        Acl acl = new Acl();
        acl.setType(AclType.Everyone);
        acl.setValue("everyone");
        acl.setAccessType(AccessType.Grant);
        externalItem.setAcl(List.of(acl));

        Properties props = new Properties();
        HashMap<String, Object> additionalData = new HashMap<>();
        additionalData.put("ticketId", "TICKET-001");
        additionalData.put("title", "VPN Connection Drops After Windows Update");
        additionalData.put("status", "Open");
        additionalData.put("priority", 2);
        additionalData.put("assignedTo", "jane.smith@contoso.com");
        additionalData.put("createdDate", OffsetDateTime.parse("2026-03-15T10:30:00Z"));
        additionalData.put("lastModifiedDate", OffsetDateTime.parse("2026-03-20T14:15:00Z"));
        additionalData.put("itemUrl", "https://helpdesk.contoso.com/tickets/TICKET-001");
        additionalData.put("iconUrl", "https://helpdesk.contoso.com/icons/ticket.png");
        props.setAdditionalData(additionalData);
        externalItem.setProperties(props);

        ExternalItemContent content = new ExternalItemContent();
        content.setValue(
                "Title: VPN Connection Drops After Windows Update\n" +
                "Status: Open | Priority: P2\n" +
                "Assigned to: Jane Smith\n\n" +
                "Description: Multiple users report VPN disconnections after installing " +
                "KB5034441 Windows update. Affects GlobalProtect VPN client v6.1.\n\n" +
                "Root Cause: Windows update modified network adapter settings, causing " +
                "MTU mismatch with VPN tunnel configuration.\n\n" +
                "Workaround: Reset network adapter MTU to 1400 via 'netsh interface ipv4 " +
                "set subinterface \"Ethernet\" mtu=1400 store=persistent'");
        content.setType(ExternalItemContentType.Text);
        externalItem.setContent(content);

        // PUT is an upsert — creates or updates the item
        graphClient.external().connections()
                .byExternalConnectionId("contosohelpdesk")
                .items()
                .byExternalItemId("TICKET-001")
                .put(externalItem);

        System.out.println("Item ingested successfully!");

        // --- Step 5: Configure urlToItemResolver ---
        ItemIdResolver resolver = new ItemIdResolver();
        UrlMatchInfo urlMatchInfo = new UrlMatchInfo();
        urlMatchInfo.setBaseUrls(List.of("https://helpdesk.contoso.com"));
        urlMatchInfo.setUrlPattern("/tickets/(?<itemId>[A-Za-z0-9-]+)");
        resolver.setUrlMatchInfo(urlMatchInfo);

        ActivitySettings activitySettings = new ActivitySettings();
        activitySettings.setUrlToItemResolvers(List.of(resolver));

        ExternalConnection updateConnection = new ExternalConnection();
        updateConnection.setActivitySettings(activitySettings);

        graphClient.external().connections()
                .byExternalConnectionId("contosohelpdesk")
                .patch(updateConnection);

        System.out.println("Connector setup complete!");
        System.out.println("Next: Enable inline results in M365 Admin Center > Search & intelligence > Verticals");
    }
}
