// Throttle-resilient ingestion with batch concurrency control
using System.Text;
using System.Text.Json;
using Microsoft.Graph;
using Microsoft.Graph.Models.ExternalConnectors;

public class ResilientIngestion
{
    private readonly GraphServiceClient _graphClient;
    private readonly string _connectionId;

    public ResilientIngestion(GraphServiceClient graphClient, string connectionId)
    {
        _graphClient = graphClient;
        _connectionId = connectionId;
    }

    /// <summary>
    /// Ingest a single item with exponential backoff retry on throttling.
    /// </summary>
    public async Task IngestWithRetryAsync(ExternalItem item, int maxRetries = 5)
    {
        for (int attempt = 0; attempt <= maxRetries; attempt++)
        {
            try
            {
                await _graphClient.External.Connections[_connectionId]
                    .Items[item.Id]
                    .PutAsync(item);
                return; // Success
            }
            catch (ServiceException ex) when (ex.ResponseStatusCode == 429)
            {
                if (attempt == maxRetries)
                    throw;

                var retryAfter = ex.ResponseHeaders?
                    .RetryAfter?.Delta ?? TimeSpan.FromSeconds(Math.Pow(2, attempt));

                Console.WriteLine(
                    $"Throttled on item {item.Id}. Retry {attempt + 1}/{maxRetries} " +
                    $"after {retryAfter.TotalSeconds}s");

                await Task.Delay(retryAfter);
            }
        }
    }

    /// <summary>
    /// Batch ingest items with controlled concurrency.
    /// Uses a semaphore to limit parallel requests (recommended: 4-8,
    /// never exceeding the 25 concurrent operations per connection limit).
    /// </summary>
    public async Task BatchIngestAsync(
        IEnumerable<ExternalItem> items,
        int maxConcurrency = 4,
        IProgress<(int completed, int total)>? progress = null)
    {
        var itemList = items.ToList();
        var semaphore = new SemaphoreSlim(maxConcurrency);
        int completed = 0;

        var tasks = itemList.Select(async item =>
        {
            await semaphore.WaitAsync();
            try
            {
                await IngestWithRetryAsync(item);
                var count = Interlocked.Increment(ref completed);
                progress?.Report((count, itemList.Count));
            }
            finally
            {
                semaphore.Release();
            }
        });

        await Task.WhenAll(tasks);
    }

    /// <summary>
    /// Check payload size before ingestion and auto-chunk if needed.
    /// The 4 MB limit applies to the full serialized request body.
    /// </summary>
    public async Task IngestWithAutoChunkAsync(ExternalItem item)
    {
        var json = JsonSerializer.Serialize(item);
        var byteSize = Encoding.UTF8.GetByteCount(json);

        if (byteSize > 3_800_000) // Leave 200KB buffer
        {
            Console.WriteLine(
                $"Item {item.Id} is {byteSize / 1_000_000.0:F1}MB — chunking required.");

            var chunks = ChunkContent(item.Content?.Value ?? "", maxChunkBytes: 3_500_000);

            for (int i = 0; i < chunks.Count; i++)
            {
                var chunkedItem = CloneItemWithChunk(item, chunks[i], i, chunks.Count);
                await IngestWithRetryAsync(chunkedItem);
            }
        }
        else
        {
            await IngestWithRetryAsync(item);
        }
    }

    /// <summary>
    /// Split content at paragraph boundaries, respecting byte size limits.
    /// </summary>
    private static List<string> ChunkContent(string content, int maxChunkBytes)
    {
        var paragraphs = content.Split("\n\n", StringSplitOptions.RemoveEmptyEntries);
        var chunks = new List<string>();
        var current = new StringBuilder();
        int currentSize = 0;

        foreach (var para in paragraphs)
        {
            var paraSize = Encoding.UTF8.GetByteCount(para);

            if (currentSize + paraSize > maxChunkBytes && current.Length > 0)
            {
                chunks.Add(current.ToString());
                current.Clear();
                currentSize = 0;
            }

            current.AppendLine(para);
            current.AppendLine();
            currentSize += paraSize;
        }

        if (current.Length > 0)
            chunks.Add(current.ToString());

        return chunks;
    }

    /// <summary>
    /// Create a chunked version of an item with a unique ID and title context.
    /// </summary>
    private static ExternalItem CloneItemWithChunk(
        ExternalItem original, string chunkContent, int chunkIndex, int totalChunks)
    {
        var originalTitle = original.Properties?.AdditionalData?
            .GetValueOrDefault("title")?.ToString() ?? "Document";

        var props = new Dictionary<string, object>(
            original.Properties?.AdditionalData ?? new Dictionary<string, object>());

        props["title"] = $"{originalTitle} (Part {chunkIndex + 1} of {totalChunks})";
        props["parentDocumentId"] = original.Id ?? "";
        props["chunkIndex"] = chunkIndex;
        props["totalChunks"] = totalChunks;

        // Prepend contextual header for self-contained chunks
        var contextHeader =
            $"Document: {originalTitle}\n" +
            $"Part {chunkIndex + 1} of {totalChunks}\n\n";

        return new ExternalItem
        {
            Id = $"{original.Id}_chunk_{chunkIndex}",
            Acl = original.Acl,
            Properties = new Properties { AdditionalData = props },
            Content = new ExternalItemContent
            {
                Value = contextHeader + chunkContent,
                Type = original.Content?.Type ?? ExternalItemContentType.Text
            }
        };
    }
}
