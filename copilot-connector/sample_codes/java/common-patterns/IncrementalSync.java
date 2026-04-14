// Incremental sync pattern: track changes and only re-ingest modified items
//
// Prerequisites:
//   Maven: com.microsoft.graph:microsoft-graph:6.x, com.azure:azure-identity:1.x
//   Gradle: implementation 'com.microsoft.graph:microsoft-graph:6.+'
//           implementation 'com.azure:azure-identity:1.+'

import com.microsoft.graph.GraphServiceClient;
import com.microsoft.graph.models.externalconnectors.*;
import com.microsoft.graph.models.externalconnectors.Properties;
import com.microsoft.kiota.ApiException;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Demonstrates incremental sync patterns for a Copilot Connector.
 * Covers timestamp-based sync with checkpoint tracking and hash-based
 * change detection for sources that don't provide modification dates.
 */
public class IncrementalSync {

    private final GraphServiceClient graphClient;
    private final String connectionId;

    public IncrementalSync(GraphServiceClient graphClient, String connectionId) {
        this.graphClient = graphClient;
        this.connectionId = connectionId;
    }

    /**
     * Perform incremental sync by comparing source items against a checkpoint.
     * Only ingests new/modified items and deletes removed items.
     *
     * @param currentSourceItems all items currently in the source system
     * @param lastCheckpoint     the checkpoint from the previous sync run
     */
    public void runIncrementalSync(
            List<SourceItem> currentSourceItems,
            SyncCheckpoint lastCheckpoint) {

        var sourceById = currentSourceItems.stream()
                .collect(Collectors.toMap(SourceItem::id, item -> item));
        Set<String> previousIds = lastCheckpoint.knownItemIds();

        // 1. Find new and modified items
        List<SourceItem> toUpsert = currentSourceItems.stream()
                .filter(item ->
                        !previousIds.contains(item.id()) ||                     // New item
                        item.lastModified().isAfter(lastCheckpoint.timestamp())) // Modified since last sync
                .toList();

        // 2. Find deleted items (in previous checkpoint but not in current source)
        List<String> toDelete = previousIds.stream()
                .filter(id -> !sourceById.containsKey(id))
                .toList();

        System.out.printf("Incremental sync: %d upserts, %d deletes%n",
                toUpsert.size(), toDelete.size());

        // 3. Upsert new/modified items
        for (var sourceItem : toUpsert) {
            ExternalItem externalItem = mapToExternalItem(sourceItem);
            graphClient.external().connections()
                    .byExternalConnectionId(connectionId)
                    .items()
                    .byExternalItemId(sourceItem.id())
                    .put(externalItem);
        }

        // 4. Delete removed items
        for (String itemId : toDelete) {
            try {
                graphClient.external().connections()
                        .byExternalConnectionId(connectionId)
                        .items()
                        .byExternalItemId(itemId)
                        .delete();
            } catch (ApiException ex) {
                if (ex.getResponseStatusCode() == 404) {
                    // Item already deleted — safe to ignore
                } else {
                    throw ex;
                }
            }
        }

        // 5. Update checkpoint
        Set<String> currentIds = new HashSet<>(sourceById.keySet());
        var newCheckpoint = new SyncCheckpoint(OffsetDateTime.now(), currentIds);
        saveCheckpoint(newCheckpoint);
    }

    /**
     * Hash-based change detection: only re-ingest items whose content hash changed.
     * More efficient than timestamp-based when source doesn't track modification dates.
     *
     * @param currentSourceItems all items currently in the source system
     * @param previousHashes     map of itemId → content hash from the previous sync
     */
    public void runHashBasedSync(
            List<SourceItem> currentSourceItems,
            Map<String, String> previousHashes) {

        for (var sourceItem : currentSourceItems) {
            String currentHash = computeContentHash(sourceItem);

            String previousHash = previousHashes.get(sourceItem.id());
            if (previousHash != null && previousHash.equals(currentHash)) {
                continue; // No changes — skip
            }

            ExternalItem externalItem = mapToExternalItem(sourceItem);
            graphClient.external().connections()
                    .byExternalConnectionId(connectionId)
                    .items()
                    .byExternalItemId(sourceItem.id())
                    .put(externalItem);

            previousHashes.put(sourceItem.id(), currentHash);
        }
    }

    private ExternalItem mapToExternalItem(SourceItem source) {
        ExternalItem item = new ExternalItem();
        item.setId(source.id());

        Acl acl = new Acl();
        acl.setType(AclType.Everyone);
        acl.setValue("everyone");
        acl.setAccessType(AccessType.Grant);
        item.setAcl(List.of(acl));

        Properties props = new Properties();
        HashMap<String, Object> additionalData = new HashMap<>();
        additionalData.put("title", source.title());
        additionalData.put("status", source.status());
        additionalData.put("lastModifiedDate", source.lastModified());
        additionalData.put("itemUrl", source.url());
        additionalData.put("iconUrl", source.iconUrl() != null ? source.iconUrl() : "");
        props.setAdditionalData(additionalData);
        item.setProperties(props);

        ExternalItemContent content = new ExternalItemContent();
        content.setValue(source.fullContent());
        content.setType(ExternalItemContentType.Text);
        item.setContent(content);

        return item;
    }

    private String computeContentHash(SourceItem item) {
        String combined = item.title() + "|" + item.status() + "|"
                + item.fullContent() + "|" + item.lastModified();
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(combined.getBytes(StandardCharsets.UTF_8));
            return bytesToHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException("SHA-256 not available", e);
        }
    }

    private static String bytesToHex(byte[] bytes) {
        var sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    private void saveCheckpoint(SyncCheckpoint checkpoint) {
        // Implement: save to database, blob storage, or local file
        System.out.printf("Checkpoint saved: %s, %d items%n",
                checkpoint.timestamp(), checkpoint.knownItemIds().size());
    }

    // --- Supporting types ---

    /** Represents an item from the source system. */
    public record SourceItem(
            String id,
            String title,
            String status,
            String fullContent,
            String url,
            String iconUrl,
            OffsetDateTime lastModified
    ) {}

    /** Tracks sync state between runs. */
    public record SyncCheckpoint(
            OffsetDateTime timestamp,
            Set<String> knownItemIds
    ) {}
}
