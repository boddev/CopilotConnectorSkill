// Incremental sync pattern: track changes and only re-ingest modified items
using Microsoft.Graph;
using Microsoft.Graph.Models.ExternalConnectors;

public class IncrementalSync
{
    private readonly GraphServiceClient _graphClient;
    private readonly string _connectionId;

    public IncrementalSync(GraphServiceClient graphClient, string connectionId)
    {
        _graphClient = graphClient;
        _connectionId = connectionId;
    }

    /// <summary>
    /// Perform incremental sync by comparing source items against a checkpoint.
    /// Only ingests new/modified items and deletes removed items.
    /// </summary>
    public async Task RunIncrementalSyncAsync(
        IEnumerable<SourceItem> currentSourceItems,
        SyncCheckpoint lastCheckpoint)
    {
        var sourceById = currentSourceItems.ToDictionary(s => s.Id);
        var previousIds = lastCheckpoint.KnownItemIds;

        // 1. Find new and modified items
        var toUpsert = currentSourceItems
            .Where(item =>
                !previousIds.Contains(item.Id) ||           // New item
                item.LastModified > lastCheckpoint.Timestamp) // Modified since last sync
            .ToList();

        // 2. Find deleted items (in previous checkpoint but not in current source)
        var toDelete = previousIds
            .Where(id => !sourceById.ContainsKey(id))
            .ToList();

        Console.WriteLine($"Incremental sync: {toUpsert.Count} upserts, {toDelete.Count} deletes");

        // 3. Upsert new/modified items
        foreach (var sourceItem in toUpsert)
        {
            var externalItem = MapToExternalItem(sourceItem);
            await _graphClient.External.Connections[_connectionId]
                .Items[sourceItem.Id]
                .PutAsync(externalItem);
        }

        // 4. Delete removed items
        foreach (var itemId in toDelete)
        {
            try
            {
                await _graphClient.External.Connections[_connectionId]
                    .Items[itemId]
                    .DeleteAsync();
            }
            catch (ServiceException ex) when (ex.ResponseStatusCode == 404)
            {
                // Item already deleted — safe to ignore
            }
        }

        // 5. Update checkpoint
        var newCheckpoint = new SyncCheckpoint
        {
            Timestamp = DateTimeOffset.UtcNow,
            KnownItemIds = sourceById.Keys.ToHashSet()
        };
        await SaveCheckpointAsync(newCheckpoint);
    }

    /// <summary>
    /// Hash-based change detection: only re-ingest items whose content hash changed.
    /// More efficient than timestamp-based when source doesn't track modification dates.
    /// </summary>
    public async Task RunHashBasedSyncAsync(
        IEnumerable<SourceItem> currentSourceItems,
        Dictionary<string, string> previousHashes)
    {
        foreach (var sourceItem in currentSourceItems)
        {
            var currentHash = ComputeContentHash(sourceItem);

            if (previousHashes.TryGetValue(sourceItem.Id, out var prevHash) &&
                prevHash == currentHash)
            {
                continue; // No changes — skip
            }

            var externalItem = MapToExternalItem(sourceItem);
            await _graphClient.External.Connections[_connectionId]
                .Items[sourceItem.Id]
                .PutAsync(externalItem);

            previousHashes[sourceItem.Id] = currentHash;
        }
    }

    private ExternalItem MapToExternalItem(SourceItem source)
    {
        return new ExternalItem
        {
            Id = source.Id,
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
                    { "title", source.Title },
                    { "status", source.Status },
                    { "lastModifiedDate", source.LastModified },
                    { "itemUrl", source.Url },
                    { "iconUrl", source.IconUrl ?? "" }
                }
            },
            Content = new ExternalItemContent
            {
                Value = source.FullContent,
                Type = ExternalItemContentType.Text
            }
        };
    }

    private string ComputeContentHash(SourceItem item)
    {
        var combined = $"{item.Title}|{item.Status}|{item.FullContent}|{item.LastModified}";
        var bytes = System.Security.Cryptography.SHA256.HashData(
            System.Text.Encoding.UTF8.GetBytes(combined));
        return Convert.ToHexString(bytes);
    }

    private Task SaveCheckpointAsync(SyncCheckpoint checkpoint)
    {
        // Implement: save to database, blob storage, or local file
        Console.WriteLine($"Checkpoint saved: {checkpoint.Timestamp}, {checkpoint.KnownItemIds.Count} items");
        return Task.CompletedTask;
    }
}

// Supporting types
public class SourceItem
{
    public string Id { get; set; } = "";
    public string Title { get; set; } = "";
    public string Status { get; set; } = "";
    public string FullContent { get; set; } = "";
    public string Url { get; set; } = "";
    public string? IconUrl { get; set; }
    public DateTimeOffset LastModified { get; set; }
}

public class SyncCheckpoint
{
    public DateTimeOffset Timestamp { get; set; }
    public HashSet<string> KnownItemIds { get; set; } = new();
}
