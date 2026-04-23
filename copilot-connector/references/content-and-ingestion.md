# Content & Ingestion Reference

Detailed guidance on content formatting, chunking strategies, throttle handling, and batch ingestion patterns.

## The Content Property

The `content` property is built-in to every Copilot Connector schema. You do NOT define it in the schema — include it directly in the item payload during ingestion.

The content property is:
- **Semantically indexed** for full-text search
- Used to generate **dynamic snippets** in search results
- Available to Copilot for **summarization and semantic reasoning**

### Supported Content Types

| Type | Format | When to Use |
|------|--------|-------------|
| `text` | Plain text, no markup | Short/factual records, structured data, compliance scenarios |
| `html` | HTML markup | Rich documents, formatted content with headings/lists/tables |

> **Markdown is NOT supported.** Convert to HTML or strip to plain text before ingestion.

> For compliance connections (`enabledContentExperience: "compliance"`), you **must** use `text`.

### HTML Best Practices

- Use semantic tags: `<h1>`–`<h6>`, `<p>`, `<ul>`, `<ol>`, `<table>`, `<strong>`, `<em>`
- **Strip**: `<script>`, `<style>`, navigation, footers, ads, inline CSS, class/id/data attributes
- Use `<table>` with `<th>` and `<td>` for tabular data — Copilot reasons well over structured tables
- Avoid deeply nested HTML — flatten to reduce token overhead

### Structuring Content for Copilot

1. **Lead with the most important information** — Key facts, summaries, and conclusions first
2. **Use descriptive headings** — Help Copilot identify sections
3. **Include contextual metadata inline** — If a property is important for understanding, repeat it in content
4. **Concatenate related text fields** — Merge `summary`, `description`, `rootCause`, `resolution` into one value

### Content Concatenation Pattern (C#)

```csharp
var contentBuilder = new StringBuilder();
contentBuilder.AppendLine($"Title: {ticket.Title}");
contentBuilder.AppendLine($"Status: {ticket.Status} | Priority: {ticket.Priority}");
contentBuilder.AppendLine($"Assigned to: {ticket.AssignedTo}");
contentBuilder.AppendLine();
contentBuilder.AppendLine($"Description: {ticket.Description}");

if (!string.IsNullOrEmpty(ticket.RootCause))
    contentBuilder.AppendLine($"Root Cause: {ticket.RootCause}");

if (!string.IsNullOrEmpty(ticket.Resolution))
    contentBuilder.AppendLine($"Resolution: {ticket.Resolution}");

foreach (var comment in ticket.Comments.OrderByDescending(c => c.Date))
    contentBuilder.AppendLine($"[{comment.Author} - {comment.Date:yyyy-MM-dd}]: {comment.Text}");
```

### Content Concatenation Pattern (Python)

```python
def build_ticket_content(title, status, priority, assignee, description,
                         root_cause=None, resolution=None, comments=None):
    lines = [
        f"Title: {title}",
        f"Status: {status} | Priority: {priority}",
        f"Assigned to: {assignee}",
        "",
        f"Description: {description}",
    ]
    if root_cause:
        lines.append(f"\nRoot Cause: {root_cause}")
    if resolution:
        lines.append(f"\nResolution: {resolution}")
    if comments:
        lines.append("\nComments:")
        for author, date, text in comments:
            lines.append(f"  [{author} - {date:%Y-%m-%d}]: {text}")
    return "\n".join(lines)
```

### Content Concatenation Pattern (Java)

```java
public static String buildTicketContent(String title, String status,
        String priority, String assignee, String description,
        String rootCause, String resolution) {
    var sb = new StringBuilder();
    sb.append("Title: ").append(title).append("\n");
    sb.append("Status: ").append(status).append(" | Priority: ").append(priority).append("\n");
    sb.append("Assigned to: ").append(assignee).append("\n\n");
    sb.append("Description: ").append(description).append("\n");
    if (rootCause != null && !rootCause.isBlank())
        sb.append("\nRoot Cause: ").append(rootCause).append("\n");
    if (resolution != null && !resolution.isBlank())
        sb.append("\nResolution: ").append(resolution).append("\n");
    return sb.toString();
}
```

### Content Concatenation Pattern (TypeScript)

```typescript
function buildTicketContent(
  title: string, status: string, priority: string, assignee: string,
  description: string, rootCause?: string, resolution?: string,
  comments?: Array<{ author: string; date: Date; text: string }>
): string {
  const lines = [
    `Title: ${title}`,
    `Status: ${status} | Priority: ${priority}`,
    `Assigned to: ${assignee}`,
    "",
    `Description: ${description}`,
  ];
  if (rootCause) lines.push(`\nRoot Cause: ${rootCause}`);
  if (resolution) lines.push(`\nResolution: ${resolution}`);
  if (comments?.length) {
    lines.push("\nComments:");
    for (const c of comments) {
      lines.push(`  [${c.author} - ${c.date.toISOString().slice(0, 10)}]: ${c.text}`);
    }
  }
  return lines.join("\n");
}
```

### What Goes in `content` vs Properties

| Put in `content` | Put in properties only |
|-------------------|----------------------|
| Free-text descriptions, notes, comments | Identifiers (IDs, SKUs) |
| Combined narrative from multiple fields | Status values, categories |
| Any text users would naturally search for | Dates, numbers for filtering |
| Context that helps Copilot understand | URLs, email addresses |

> **Key principle:** Unstructured searchable text → `content`. Structured filterable values → properties. Duplicate into content only what helps Copilot understand the item contextually.

## The 4 MB Item Size Limit

Each external item's request body (ACL + properties + content) is limited to **4 MB**. This is approximately:
- 600,000–700,000 words of plain text
- ~1,400 pages at 500 words per page

> The 4 MB limit refers to parsed text content, typically ~10% of original file size. A 200-page PDF may only produce 200 KB of text. **Always measure serialized payload byte size before deciding to chunk.**

### When to Chunk

| Scenario | Chunking Needed? |
|----------|------------------|
| Short records (tickets, CRM entries) | ❌ No |
| Medium articles (wiki pages, FAQs, 1–10 pages) | ❌ Usually no |
| Serialized request body exceeds ~3.5 MB | ✅ Yes |
| Entire databases/datasets | ✅ Yes — one item per row |
| Large parsed binary files | Measure first |

### Chunking Strategy 1: Logical Section Chunking (Recommended)

Split at natural document boundaries: chapters, sections, headings.

```
Original: 200-page technical manual
├── Chunk 1: "Chapter 1: Introduction" (pages 1–15)
├── Chunk 2: "Chapter 2: Installation" (pages 16–40)
├── Chunk 3: "Chapter 3: Configuration" (pages 41–80)
└── ...
```

**Advantages:** Preserves semantic coherence; each chunk is self-contained.

### Chunking Strategy 2: Fixed-Size with Overlap

Split at fixed character boundaries with overlap.

```
Chunk size: 50,000 characters
Overlap: 5,000 characters

Chunk 1: characters 0–50,000
Chunk 2: characters 45,000–95,000
Chunk 3: characters 90,000–140,000
```

### Chunking Strategy 3: Semantic Boundary

Split at paragraph or sentence boundaries, accumulating until approaching size limit.

```python
def chunk_by_paragraphs(text, max_size=3_500_000):
    paragraphs = text.split('\n\n')
    chunks, current_chunk = [], []
    current_size = 0

    for para in paragraphs:
        para_size = len(para.encode('utf-8'))
        if current_size + para_size > max_size and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk, current_size = [], 0
        current_chunk.append(para)
        current_size += para_size

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    return chunks
```

### Linking Chunks Together

When splitting a document into multiple items, maintain relationships:

```json
{
  "properties": {
    "title": "Technical Manual — Chapter 3: Configuration",
    "parentDocumentId": "DOC-12345",
    "parentDocumentTitle": "Technical Manual v4.2",
    "chunkIndex": 3,
    "totalChunks": 5,
    "sectionPath": "Chapter 3 > Configuration > Network Settings"
  }
}
```

### Making Chunks Self-Contained

Add a contextual header to every chunk so Copilot can attribute it correctly:

```
Document: Technical Manual v4.2
Section: Chapter 3 — Configuration > Network Settings
Part 3 of 5

[Actual section content begins here...]
```

### Chunk Indexing Rules

1. **Deterministic item IDs** — Derive from source key + chunk index: `DOC-12345_chunk_3`
2. **Unique titles per chunk** — Include section context in title
3. **Apply all relevant labels to every chunk** — Each chunk is an independent item
4. **Deep-link URL** — Point to the specific section when possible

## Size Limits and Throttling

| Limit | Value |
|-------|-------|
| Item request body size | **4 MB** |
| Activities per call | **20** |
| Concurrent operations per connection | **25** |
| Throttle response | **HTTP 429** with `Retry-After` header |

### Throttle-Resilient Ingestion (C#)

```csharp
public async Task IngestWithRetry(ExternalItem item, int maxRetries = 5)
{
    for (int attempt = 0; attempt <= maxRetries; attempt++)
    {
        try
        {
            await graphClient.External.Connections[connectionId]
                .Items[item.Id]
                .PutAsync(item);
            return;
        }
        catch (ServiceException ex) when (ex.ResponseStatusCode == 429)
        {
            var retryAfter = ex.ResponseHeaders?
                .RetryAfter?.Delta ?? TimeSpan.FromSeconds(Math.Pow(2, attempt));
            await Task.Delay(retryAfter);
        }
    }
    throw new Exception($"Failed to ingest item after {maxRetries} retries");
}
```

### Throttle-Resilient Ingestion (Python)

```python
async def ingest_with_retry(graph_client, connection_id, item, max_retries=5):
    for attempt in range(max_retries + 1):
        try:
            await (graph_client.external.connections
                .by_external_connection_id(connection_id)
                .items.by_external_item_id(item.id)
                .put(item))
            return
        except ODataError as e:
            if e.response_status_code == 429 and attempt < max_retries:
                wait = int(e.response_headers.get("Retry-After", 2 ** attempt))
                await asyncio.sleep(wait)
            else:
                raise
```

### Throttle-Resilient Ingestion (TypeScript)

```typescript
async function ingestWithRetry(
  graphClient: Client, connectionId: string,
  item: ExternalItemPayload, maxRetries = 5
): Promise<void> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      await graphClient.api(
        `/external/connections/${connectionId}/items/${item.id}`
      ).put(item);
      return;
    } catch (error: any) {
      if (error.statusCode === 429 && attempt < maxRetries) {
        const retryAfter = parseInt(error.headers?.["retry-after"] ?? String(2 ** attempt));
        await new Promise(r => setTimeout(r, retryAfter * 1000));
      } else { throw error; }
    }
  }
}
```

### Batch Ingestion Strategies

**1. Sequential with rate limiting** — One at a time with delay. Simplest, lowest throughput.

**2. Concurrent with semaphore (recommended)** — 4–8 simultaneous calls, never exceeding the 25 concurrent ops limit.

```csharp
var semaphore = new SemaphoreSlim(4);
var tasks = items.Select(async item =>
{
    await semaphore.WaitAsync();
    try { await IngestWithRetry(item); }
    finally { semaphore.Release(); }
});
await Task.WhenAll(tasks);
```

**3. Queue-based** — Azure Queue / Service Bus + Azure Functions. Best for large-scale, fault-tolerant ingestion.

### Crawl Strategies

| Strategy | Best For |
|----------|----------|
| **Full crawl** | Initial load, periodic reconciliation |
| **Incremental crawl** | Ongoing sync, delta changes only |
| **Event-based** | Real-time updates via webhooks |
| **Scheduled** | Infrequently updated content |

### Ingestion Gotchas

- **`@odata.type` required** for collection properties in payloads (e.g., `"tags@odata.type": "Collection(Edm.String)"`)
- **Non-ASCII characters** — Ensure UTF-8 encoding; some languages inflate byte size significantly
- **Item ID restrictions** — Must be URL-safe; no `#`, `?`, `&`, `/`
- **Excessively large property values** impact performance even within 4 MB limit

### Payload Size Check (C#)

```csharp
var json = JsonSerializer.Serialize(externalItem);
var byteSize = Encoding.UTF8.GetByteCount(json);

if (byteSize > 3_800_000) // Leave 200KB buffer
{
    var chunks = ChunkContent(externalItem.Content.Value, maxChunkSize: 3_500_000);
    for (int i = 0; i < chunks.Count; i++)
    {
        var chunkedItem = CloneItemWithChunk(externalItem, chunks[i], i, chunks.Count);
        await IngestWithRetry(chunkedItem);
    }
}
else
{
    await IngestWithRetry(externalItem);
}
```

### Payload Size Check (Python)

```python
import json

payload = json.dumps(item_dict)
byte_size = len(payload.encode("utf-8"))

if byte_size > 3_800_000:  # Leave 200KB buffer
    chunks = chunk_content(item_dict["content"]["value"], max_chunk_bytes=3_500_000)
    for i, chunk in enumerate(chunks):
        chunked = clone_item_with_chunk(item_dict, chunk, i, len(chunks))
        await ingest_with_retry(graph_client, connection_id, chunked)
else:
    await ingest_with_retry(graph_client, connection_id, item)
```

### Payload Size Check (TypeScript)

```typescript
const payload = JSON.stringify(item);
const byteSize = Buffer.byteLength(payload, "utf-8");

if (byteSize > 3_800_000) { // Leave 200KB buffer
  const chunks = chunkContent(item.content.value, 3_500_000);
  for (let i = 0; i < chunks.length; i++) {
    const chunked = cloneItemWithChunk(item, chunks[i], i, chunks.length);
    await ingestWithRetry(graphClient, connectionId, chunked);
  }
} else {
  await ingestWithRetry(graphClient, connectionId, item);
}
```

## Data Aggregation Strategies

Copilot **cannot reliably aggregate** across multiple items (counts, sums, averages). It retrieves a subset and may produce incorrect totals.

### Strategy 1: Pre-Computed Summary Items (Recommended)

Ingest dedicated summary items with pre-calculated aggregations at regular intervals, per logical grouping.

### Strategy 2: Roll-Up Properties

Add pre-computed aggregate values as properties on parent items (e.g., `totalTasks`, `completionPercentage`).

### Strategy 3: Declarative Agent Instructions

Include explicit instructions in your Declarative Agent to handle aggregation correctly:

```
## Data Interpretation Instructions

This connector contains individual support tickets and pre-computed summary items.

When users ask aggregate questions (counts, totals, averages, trends):
1. Look for summary items first (property: reportType = "monthly-summary" or "weekly-summary")
2. Reference the pre-computed values in summary items rather than counting individual tickets
3. If no summary item exists for the requested aggregation, clearly state that the data shown represents a sample and may not be comprehensive
4. Never present a count derived from search results as an exact total

Available summary item types:
- Monthly team summaries (reportType: "monthly-summary")
- Weekly status reports (reportType: "weekly-summary")
- Quarterly trend analyses (reportType: "quarterly-trend")
```

### Strategy 4: Connector Actions + Power Automate

Define connector actions that call back to source APIs for real-time aggregation.

### Strategy 5: Federated Connectors (Preview)

For data too sensitive or dynamic to index — live queries executed against the source.

### Aggregation Anti-Patterns

| ❌ Don't | Why |
|----------|-----|
| Rely on Copilot to count items | Search returns a limited subset |
| Ask Copilot to sum values across results | Incomplete data → wrong totals |
| Expect Copilot to rank all items | Copilot sees a window, not full dataset |
| Ingest raw data without summaries | Aggregate questions will be unreliable |
| Use Copilot as a database query engine | Copilot is semantic reasoning, not SQL |

## Surfacing Data in Copilot — Enablement Steps

### 1. Connection Description

Provide a rich description answering: What content? Who uses it? When in their workflow? What are notable characteristics?

Consider setting `contentCategory` (e.g., `"howTo"`, `"reference"`).

### 2. Apply Semantic Labels

Minimum: `title`, `url`, `iconUrl`

### 3. Mark Properties Searchable

The `searchable` attribute determines which properties Copilot matches against.

### 4. Configure Rank Hints

For searchable properties not mapped to labels, set importance in Admin Center.

### 5. Add urlToItemResolver

```http
PATCH /external/connections/{connectionId}
{
  "activitySettings": {
    "urlToItemResolvers": [{
      "@odata.type": "#microsoft.graph.externalConnectors.itemIdResolver",
      "urlMatchInfo": {
        "baseUrls": ["https://yourapp.contoso.com"],
        "urlPattern": "/items/(?<itemId>[a-zA-Z0-9]+)"
      }
    }]
  }
}
```

### 6. Send User Activities

Supported types: `created`, `modified`, `commented`, `viewed`. Activities older than **7 days** don't surface in the Microsoft 365 app.

```http
POST /external/connections/{connectionId}/items/{itemId}/addActivities
{
  "activities": [
    {
      "@odata.type": "#microsoft.graph.externalConnectors.externalActivity",
      "type": "commented",
      "startDateTime": "2026-03-23T10:00:00Z",
      "performedBy": {
        "@odata.type": "#microsoft.graph.externalConnectors.identity",
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "type": "user"
      }
    }
  ]
}
```

### 7. Enable Inline Results

In M365 Admin Center: **Search & intelligence** > **Customizations** > **Verticals** > **All** > **Manage connector result** > Enable **Show results inline**.

### 8. Configure Result Types (Optional)

Create custom result layouts using Adaptive Cards for richer search result presentation:

```json
{
  "type": "AdaptiveCard",
  "body": [
    {
      "type": "TextBlock",
      "text": "${title}",
      "weight": "Bolder",
      "size": "Medium"
    },
    {
      "type": "TextBlock",
      "text": "Status: ${status} | Priority: ${priority}",
      "spacing": "Small"
    },
    {
      "type": "TextBlock",
      "text": "${description}",
      "wrap": true,
      "maxLines": 3
    }
  ],
  "actions": [
    {
      "type": "Action.OpenUrl",
      "title": "Open Item",
      "url": "${url}"
    }
  ]
}
```

For the **All vertical**, inline results render with default or custom result types. For **custom verticals**, a result type/layout is generally required for proper rendering.

### Declarative Agents with Connectors

When building a Declarative Agent that uses your connector as a knowledge source:

1. **Include property descriptions** in the agent's instruction set
2. **Specify available query patterns** — tell the agent which properties support filtering
3. **Document aggregation boundaries** — explain what summary data is available
4. **Provide example queries** — include sample natural-language questions and expected data sources

## Delimited Data (CSV/TSV)

### Pre-Built CSV Connector

Available in M365 Admin Center for CSV files in SharePoint or Azure Data Lake Storage. Supports column-to-property mapping, multi-item delimiters, and ACL configuration.

### Custom Connector: Row-Per-Item Mapping

Each CSV row becomes one `externalItem`. Map columns to schema properties and build content by concatenating descriptive columns with labels.

### Multi-Value Delimiters

```csharp
private List<string> ParseMultiValue(string value, string delimiter = ";")
{
    if (string.IsNullOrWhiteSpace(value)) return new List<string>();
    return value.Split(delimiter)
                .Select(v => v.Trim())
                .Where(v => !string.IsNullOrEmpty(v))
                .ToList();
}
```

Map to `StringCollection` properties with `isRefinable: true` and `isExactMatchRequired: true`.

### Large CSV Files

1. **Stream** — Don't load entire file into memory
2. **Batch** in groups of 100–500 items with concurrent ingestion
3. **Checkpoint** — Track last successfully ingested row
4. **Deterministic IDs** — Derive from unique columns
5. **Partition** — Split very large CSVs by date, category, or region
