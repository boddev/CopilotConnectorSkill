// Schema registration with status polling
// Shows all property types, attributes, semantic labels, and aliases
//
// Prerequisites:
//   Maven: com.microsoft.graph:microsoft-graph:6.x, com.azure:azure-identity:1.x
//   Gradle: implementation 'com.microsoft.graph:microsoft-graph:6.+'
//           implementation 'com.azure:azure-identity:1.+'

import com.microsoft.graph.GraphServiceClient;
import com.microsoft.graph.models.externalconnectors.*;

import java.time.Duration;
import java.time.Instant;
import java.util.LinkedList;
import java.util.List;

/**
 * Demonstrates schema registration for a Copilot Connector.
 * Covers every property type (String, Int64, DateTime, Double, Boolean, StringCollection),
 * all attribute flags, semantic labels, aliases, and async polling for completion.
 */
public class SchemaRegistration {

    private final GraphServiceClient graphClient;
    private final String connectionId;

    public SchemaRegistration(GraphServiceClient graphClient, String connectionId) {
        this.graphClient = graphClient;
        this.connectionId = connectionId;
    }

    /**
     * Register a comprehensive schema showing every property type and attribute combination.
     */
    public void registerSchema() {
        Schema schema = new Schema();
        schema.setBaseType("microsoft.graph.externalItem");

        List<Property> properties = new LinkedList<>();

        // Searchable + Queryable + Retrievable — for full-text and filtered search
        Property titleProp = new Property();
        titleProp.setName("title");
        titleProp.setType(PropertyType.String);
        titleProp.setIsSearchable(true);
        titleProp.setIsQueryable(true);
        titleProp.setIsRetrievable(true);
        titleProp.setLabels(List.of(Label.Title));
        properties.add(titleProp);

        // Searchable text (but NOT refinable — they are mutually exclusive)
        Property descriptionProp = new Property();
        descriptionProp.setName("description");
        descriptionProp.setType(PropertyType.String);
        descriptionProp.setIsSearchable(true);
        descriptionProp.setIsQueryable(false);
        descriptionProp.setIsRetrievable(false);
        properties.add(descriptionProp);

        // Refinable (but NOT searchable — mutually exclusive)
        // Must be set in initial schema — cannot add refinable via update
        Property statusProp = new Property();
        statusProp.setName("status");
        statusProp.setType(PropertyType.String);
        statusProp.setIsSearchable(false);
        statusProp.setIsQueryable(true);
        statusProp.setIsRetrievable(true);
        statusProp.setIsRefinable(true);
        statusProp.setAliases(List.of("state"));
        properties.add(statusProp);

        // Numeric refinable property
        Property priorityProp = new Property();
        priorityProp.setName("priority");
        priorityProp.setType(PropertyType.Int64);
        priorityProp.setIsQueryable(true);
        priorityProp.setIsRetrievable(true);
        priorityProp.setIsRefinable(true);
        properties.add(priorityProp);

        // ExactMatchRequired — only on non-searchable properties
        Property ticketIdProp = new Property();
        ticketIdProp.setName("ticketId");
        ticketIdProp.setType(PropertyType.String);
        ticketIdProp.setIsSearchable(false);
        ticketIdProp.setIsQueryable(true);
        ticketIdProp.setIsRetrievable(true);
        ticketIdProp.setIsExactMatchRequired(true);
        ticketIdProp.setAliases(List.of("ID", "incidentNumber"));
        properties.add(ticketIdProp);

        // StringCollection with refinable + exact match
        Property tagsProp = new Property();
        tagsProp.setName("tags");
        tagsProp.setType(PropertyType.StringCollection);
        tagsProp.setIsQueryable(true);
        tagsProp.setIsRetrievable(true);
        tagsProp.setIsRefinable(true);
        tagsProp.setIsExactMatchRequired(true);
        tagsProp.setAliases(List.of("labels", "categories"));
        properties.add(tagsProp);

        // DateTime properties with semantic labels
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

        // URL and icon — critical for Copilot surfacing
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

        // Boolean property
        Property isResolvedProp = new Property();
        isResolvedProp.setName("isResolved");
        isResolvedProp.setType(PropertyType.Boolean);
        isResolvedProp.setIsQueryable(true);
        isResolvedProp.setIsRetrievable(true);
        properties.add(isResolvedProp);

        // Double property
        Property estimatedHoursProp = new Property();
        estimatedHoursProp.setName("estimatedHours");
        estimatedHoursProp.setType(PropertyType.Double);
        estimatedHoursProp.setIsQueryable(true);
        estimatedHoursProp.setIsRetrievable(true);
        properties.add(estimatedHoursProp);

        schema.setProperties(properties);

        // Schema registration is async — returns 202 Accepted
        graphClient.external().connections()
                .byExternalConnectionId(connectionId)
                .schema()
                .patch(schema);

        System.out.println("Schema registration started.");
    }

    /**
     * Poll schema status until completed or failed.
     * Schema registration can take up to 10 minutes.
     *
     * @param timeout maximum time to wait for completion
     * @return true if schema registration completed successfully
     * @throws RuntimeException if timeout is exceeded
     */
    public boolean waitForSchema(Duration timeout) throws InterruptedException {
        if (timeout == null) {
            timeout = Duration.ofMinutes(15);
        }

        Instant deadline = Instant.now().plus(timeout);

        while (Instant.now().isBefore(deadline)) {
            Schema schema = graphClient.external().connections()
                    .byExternalConnectionId(connectionId)
                    .schema()
                    .get();

            ConnectionOperationStatus status = schema.getStatus().getState();
            System.out.println("  Schema status: " + status);

            if (status == ConnectionOperationStatus.Completed) {
                return true;
            }

            if (status == ConnectionOperationStatus.Failed) {
                System.err.println("Schema registration failed.");
                return false;
            }

            Thread.sleep(30_000); // 30 seconds
        }

        throw new RuntimeException("Schema registration timed out");
    }

    /** Convenience overload with default 15-minute timeout. */
    public boolean waitForSchema() throws InterruptedException {
        return waitForSchema(Duration.ofMinutes(15));
    }
}
