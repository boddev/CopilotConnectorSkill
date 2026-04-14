// Throttle-resilient ingestion with batch concurrency control
// Shows: retry with exponential backoff on 429, batch ingestion with concurrency limits, auto-chunking
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
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BiConsumer;

/**
 * Demonstrates throttle-resilient ingestion strategies for a Copilot Connector.
 * Includes exponential backoff retry, batch concurrency control via Semaphore,
 * and automatic content chunking for items exceeding the 4 MB limit.
 */
public class ThrottleResilientIngestion {

    private final GraphServiceClient graphClient;
    private final String connectionId;

    public ThrottleResilientIngestion(GraphServiceClient graphClient, String connectionId) {
        this.graphClient = graphClient;
        this.connectionId = connectionId;
    }

    /**
     * Ingest a single item with exponential backoff retry on throttling (HTTP 429).
     *
     * @param item       the external item to ingest
     * @param maxRetries maximum number of retry attempts
     */
    public void ingestWithRetry(ExternalItem item, int maxRetries) throws InterruptedException {
        for (int attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                graphClient.external().connections()
                        .byExternalConnectionId(connectionId)
                        .items()
                        .byExternalItemId(item.getId())
                        .put(item);
                return; // Success
            } catch (ApiException ex) {
                if (ex.getResponseStatusCode() == 429) {
                    if (attempt == maxRetries) {
                        throw ex;
                    }

                    // Use Retry-After header if available, otherwise exponential backoff
                    long retryAfterSeconds = parseRetryAfter(ex, attempt);

                    System.out.printf("Throttled on item %s. Retry %d/%d after %ds%n",
                            item.getId(), attempt + 1, maxRetries, retryAfterSeconds);

                    Thread.sleep(retryAfterSeconds * 1000);
                } else {
                    throw ex; // Non-throttling error — don't retry
                }
            }
        }
    }

    /** Convenience overload with default 5 retries. */
    public void ingestWithRetry(ExternalItem item) throws InterruptedException {
        ingestWithRetry(item, 5);
    }

    /**
     * Batch ingest items with controlled concurrency.
     * Uses a Semaphore to limit parallel requests (recommended: 4-8,
     * never exceeding the 25 concurrent operations per connection limit).
     *
     * @param items          items to ingest
     * @param maxConcurrency maximum parallel ingestion requests
     * @param progress       optional callback receiving (completed, total) counts
     */
    public void batchIngest(
            List<ExternalItem> items,
            int maxConcurrency,
            BiConsumer<Integer, Integer> progress) throws InterruptedException {

        var semaphore = new Semaphore(maxConcurrency);
        var completed = new AtomicInteger(0);
        int total = items.size();

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var futures = new ArrayList<Future<?>>();

            for (var item : items) {
                Future<?> future = executor.submit(() -> {
                    try {
                        semaphore.acquire();
                        try {
                            ingestWithRetry(item);
                            int count = completed.incrementAndGet();
                            if (progress != null) {
                                progress.accept(count, total);
                            }
                        } finally {
                            semaphore.release();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException("Ingestion interrupted", e);
                    }
                });
                futures.add(future);
            }

            // Wait for all tasks to complete
            for (var future : futures) {
                try {
                    future.get();
                } catch (ExecutionException e) {
                    System.err.println("Item ingestion failed: " + e.getCause().getMessage());
                }
            }
        }
    }

    /** Convenience overload with default concurrency of 4 and no progress callback. */
    public void batchIngest(List<ExternalItem> items) throws InterruptedException {
        batchIngest(items, 4, null);
    }

    /**
     * Check payload size before ingestion and auto-chunk if needed.
     * The 4 MB limit applies to the full serialized request body.
     *
     * @param item the external item to ingest (may be chunked)
     */
    public void ingestWithAutoChunk(ExternalItem item) throws InterruptedException {
        // Estimate serialized size from content + properties
        String contentValue = item.getContent() != null ? item.getContent().getValue() : "";
        int byteSize = contentValue.getBytes(StandardCharsets.UTF_8).length;

        if (byteSize > 3_800_000) { // Leave 200KB buffer below the 4 MB limit
            System.out.printf("Item %s is %.1fMB — chunking required.%n",
                    item.getId(), byteSize / 1_000_000.0);

            List<String> chunks = chunkContent(contentValue, 3_500_000);

            for (int i = 0; i < chunks.size(); i++) {
                ExternalItem chunkedItem = cloneItemWithChunk(item, chunks.get(i), i, chunks.size());
                ingestWithRetry(chunkedItem);
            }
        } else {
            ingestWithRetry(item);
        }
    }

    /**
     * Split content at paragraph boundaries, respecting byte size limits.
     */
    private static List<String> chunkContent(String content, int maxChunkBytes) {
        String[] paragraphs = content.split("\n\n");
        var chunks = new ArrayList<String>();
        var current = new StringBuilder();
        int currentSize = 0;

        for (String para : paragraphs) {
            if (para.isBlank()) continue;

            int paraSize = para.getBytes(StandardCharsets.UTF_8).length;

            if (currentSize + paraSize > maxChunkBytes && !current.isEmpty()) {
                chunks.add(current.toString());
                current.setLength(0);
                currentSize = 0;
            }

            current.append(para).append("\n\n");
            currentSize += paraSize;
        }

        if (!current.isEmpty()) {
            chunks.add(current.toString());
        }

        return chunks;
    }

    /**
     * Create a chunked version of an item with a unique ID and title context.
     */
    private static ExternalItem cloneItemWithChunk(
            ExternalItem original, String chunkContent, int chunkIndex, int totalChunks) {

        String originalTitle = "Document";
        if (original.getProperties() != null
                && original.getProperties().getAdditionalData() != null
                && original.getProperties().getAdditionalData().containsKey("title")) {
            originalTitle = original.getProperties().getAdditionalData().get("title").toString();
        }

        var props = new HashMap<String, Object>();
        if (original.getProperties() != null && original.getProperties().getAdditionalData() != null) {
            props.putAll(original.getProperties().getAdditionalData());
        }
        props.put("title", originalTitle + " (Part " + (chunkIndex + 1) + " of " + totalChunks + ")");
        props.put("parentDocumentId", original.getId() != null ? original.getId() : "");
        props.put("chunkIndex", chunkIndex);
        props.put("totalChunks", totalChunks);

        // Prepend contextual header for self-contained chunks
        String contextHeader = "Document: " + originalTitle + "\n"
                + "Part " + (chunkIndex + 1) + " of " + totalChunks + "\n\n";

        ExternalItem chunkedItem = new ExternalItem();
        chunkedItem.setId(original.getId() + "_chunk_" + chunkIndex);
        chunkedItem.setAcl(original.getAcl());

        Properties properties = new Properties();
        properties.setAdditionalData(props);
        chunkedItem.setProperties(properties);

        ExternalItemContent content = new ExternalItemContent();
        content.setValue(contextHeader + chunkContent);
        content.setType(original.getContent() != null
                ? original.getContent().getType()
                : ExternalItemContentType.Text);
        chunkedItem.setContent(content);

        return chunkedItem;
    }

    /**
     * Parse Retry-After from the exception, falling back to exponential backoff.
     */
    private static long parseRetryAfter(ApiException ex, int attempt) {
        // The Kiota ApiException may carry response headers; try to extract Retry-After.
        // Fall back to exponential backoff: 1s, 2s, 4s, 8s, 16s...
        try {
            var headers = ex.getResponseHeaders();
            if (headers != null) {
                var retryValues = headers.get("Retry-After");
                if (retryValues != null && !retryValues.isEmpty()) {
                    return Long.parseLong(retryValues.iterator().next());
                }
            }
        } catch (Exception ignored) {
            // Header parsing failed — use fallback
        }
        return (long) Math.pow(2, attempt);
    }
}
