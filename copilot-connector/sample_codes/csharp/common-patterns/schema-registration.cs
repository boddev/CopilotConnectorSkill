// Complete C# example: Schema registration with status polling
// Shows all property types, attributes, semantic labels, and aliases

using Microsoft.Graph;
using Microsoft.Graph.Models.ExternalConnectors;

public class SchemaRegistration
{
    private readonly GraphServiceClient _graphClient;
    private readonly string _connectionId;

    public SchemaRegistration(GraphServiceClient graphClient, string connectionId)
    {
        _graphClient = graphClient;
        _connectionId = connectionId;
    }

    public async Task RegisterSchemaAsync()
    {
        var schema = new Schema
        {
            BaseType = "microsoft.graph.externalItem",
            Properties = new List<Property>
            {
                // Searchable + Queryable + Retrievable — for full-text and filtered search
                new Property
                {
                    Name = "title",
                    Type = PropertyType.String,
                    IsSearchable = true,
                    IsQueryable = true,
                    IsRetrievable = true,
                    Labels = new List<Label?> { Label.Title }
                },
                // Searchable text (but NOT refinable — they are mutually exclusive)
                new Property
                {
                    Name = "description",
                    Type = PropertyType.String,
                    IsSearchable = true,
                    IsQueryable = false,
                    IsRetrievable = false
                },
                // Refinable (but NOT searchable — mutually exclusive)
                // Must be set in initial schema — cannot add refinable via update
                new Property
                {
                    Name = "status",
                    Type = PropertyType.String,
                    IsSearchable = false,
                    IsQueryable = true,
                    IsRetrievable = true,
                    IsRefinable = true,
                    Aliases = new List<string> { "state" }
                },
                // Numeric refinable property
                new Property
                {
                    Name = "priority",
                    Type = PropertyType.Int64,
                    IsQueryable = true,
                    IsRetrievable = true,
                    IsRefinable = true
                },
                // ExactMatchRequired — only on non-searchable properties
                new Property
                {
                    Name = "ticketId",
                    Type = PropertyType.String,
                    IsSearchable = false,
                    IsQueryable = true,
                    IsRetrievable = true,
                    IsExactMatchRequired = true,
                    Aliases = new List<string> { "ID", "incidentNumber" }
                },
                // StringCollection with refinable + exact match
                new Property
                {
                    Name = "tags",
                    Type = PropertyType.StringCollection,
                    IsQueryable = true,
                    IsRetrievable = true,
                    IsRefinable = true,
                    IsExactMatchRequired = true,
                    Aliases = new List<string> { "labels", "categories" }
                },
                // DateTime properties with semantic labels
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
                // URL and icon — critical for Copilot surfacing
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
                },
                // Boolean property
                new Property
                {
                    Name = "isResolved",
                    Type = PropertyType.Boolean,
                    IsQueryable = true,
                    IsRetrievable = true
                },
                // Double property
                new Property
                {
                    Name = "estimatedHours",
                    Type = PropertyType.Double,
                    IsQueryable = true,
                    IsRetrievable = true
                }
            }
        };

        // Schema registration is async — returns 202 Accepted
        await _graphClient.External.Connections[_connectionId].Schema
            .PatchAsync(schema);

        Console.WriteLine("Schema registration started.");
    }

    /// <summary>
    /// Poll schema status until completed or failed.
    /// Schema registration can take up to 10 minutes.
    /// </summary>
    public async Task<bool> WaitForSchemaAsync(TimeSpan? timeout = null)
    {
        timeout ??= TimeSpan.FromMinutes(15);
        var deadline = DateTime.UtcNow + timeout.Value;

        while (DateTime.UtcNow < deadline)
        {
            var schema = await _graphClient.External.Connections[_connectionId].Schema
                .GetAsync();

            var status = schema?.Status?.State;
            Console.WriteLine($"  Schema status: {status}");

            if (status == ConnectionOperationStatus.Completed)
                return true;

            if (status == ConnectionOperationStatus.Failed)
            {
                Console.Error.WriteLine("Schema registration failed.");
                return false;
            }

            await Task.Delay(TimeSpan.FromSeconds(30));
        }

        throw new TimeoutException("Schema registration timed out");
    }
}
