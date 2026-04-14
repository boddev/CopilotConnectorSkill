---
name: copilot-connector
description: Build custom Microsoft 365 Copilot Connectors (formerly Microsoft Graph Connectors) to ingest external data into the Microsoft Graph semantic index. Use when creating, configuring, or troubleshooting custom connectors that surface external content in Microsoft 365 Copilot, Microsoft Search, and Context IQ. Covers schema design, content ingestion, ACL configuration, chunking strategies, and Copilot optimization.
---

# Microsoft 365 Copilot Connectors

Build custom connectors that bring external data into the Microsoft Graph semantic index, making it discoverable in Microsoft 365 Copilot, Microsoft Search, and Context IQ.

## How Copilot Connectors Work

```
┌──────────────┐     ┌───────────────────┐     ┌──────────────────────┐
│ Your Data    │────▶│ Copilot Connector │────▶│ Microsoft Graph      │
│ Source       │     │ (REST / SDK)      │     │ Semantic Index       │
└──────────────┘     └───────────────────┘     └──────────┬───────────┘
                                                          │
                              ┌────────────────────────────┤
                              ▼                            ▼
                     ┌─────────────────┐       ┌───────────────────┐
                     │ M365 Copilot    │       │ Microsoft Search  │
                     │ (Chat, BizChat) │       │ (SharePoint, Bing)│
                     └─────────────────┘       └───────────────────┘
```

Each connector defines a **connection** to an external data source, registers a **schema** for the data shape, and ingests **items** (with content, metadata, and ACLs) into the Microsoft Graph index. Copilot and Search then reason over this data alongside native Microsoft 365 content.

## End-to-End Workflow (6 Steps)

| Step | What | Key API/Action |
|------|------|-----------------|
| 1. Prerequisites & Permissions | Register app in Entra ID, grant `ExternalConnection.ReadWrite.OwnedBy` + `ExternalItem.ReadWrite.OwnedBy`, get admin consent | Entra admin center |
| 2. Create Connection | Register external data source with unique ID, name, and rich description | `POST /external/connections` |
| 3. Register Schema | Define properties, types, search attributes, and semantic labels | `POST /external/connections/{id}/schema` |
| 4. Ingest Items | Push external items with content, properties, and ACLs | `PUT /external/connections/{id}/items/{itemId}` |
| 5. Configure Experiences | Enable inline results, set up search verticals, add urlToItemResolver, send user activities | M365 Admin Center + API |
| 6. Validate & Monitor | Verify items appear in search/Copilot, monitor crawl health, check quota usage | Admin Center + test queries |

> **Schema registration is asynchronous.** After POSTing a schema, poll `GET /external/connections/{id}/schema` until `status` is `completed` before ingesting items. This can take up to 10 minutes.

## Choosing the Right Tool

```
Is there a pre-built connector for your data source?
├── YES → Use the pre-built connector (M365 Admin Center)
└── NO
    ├── Do you need live access or indexed content?
    │   ├── LIVE ACCESS → Federated Connectors (Preview)
    │   └── INDEXED CONTENT
    │       ├── Is your data source on-premises?
    │       │   ├── YES → Copilot Connectors SDK + Connector Agent
    │       │   └── NO
    │       │       ├── Need full crawl management? → Connectors SDK or Agents Toolkit
    │       │       └── Need maximum flexibility? → Microsoft Graph REST API directly
    │       └── Building a Declarative Agent with connector? → Agents Toolkit
```

| Tool | Language | Best For |
|------|----------|----------|
| **Microsoft 365 Agents Toolkit** | TypeScript/C# | New connectors with integrated agent development |
| **Microsoft Graph REST API** | Any (HTTP) | Maximum flexibility, polyglot teams, serverless |
| **Copilot Connectors SDK** | C# (primary) | Production-grade with full crawl management |
| **Pre-built connectors** | No code | 100+ supported data sources |
| **Federated connectors** (Preview) | Any (HTTP) | Real-time, non-indexed access to live data |

## Key Concepts

### Connection
A logical container for your external data. Each connection has a unique ID (3–128 alphanumeric chars), display name, and description. The description is critical — it tells Copilot **what kind of content** this connection has and **when to use it**.

### Schema
A flat list of properties defining your data's structure. Each property has a type, search attributes (searchable, queryable, retrievable, refinable), and optional semantic labels. **You must register the schema before ingesting items.** Schema registration is asynchronous — poll until complete.

### ExternalItem
An individual data record. Contains: `properties` (structured metadata), `content` (unstructured text/HTML for semantic indexing), and `acl` (who can access it). Each item has a unique ID and is limited to **4 MB** total payload size.

### Content Property
A built-in property (not defined in schema) that holds unstructured text for full-text search and Copilot summarization. Supports `text` or `html` types. **Markdown is NOT supported** — convert to HTML or strip to plain text.

### Semantic Labels
Tags that tell Microsoft 365 the semantic role of each property (e.g., `title`, `url`, `createdBy`). Critical for Copilot integration — **always assign at minimum: `title`, `url`, and `iconUrl`**.

### ACL (Access Control List)
Every item must have an ACL specifying who can see it. Values must be **Microsoft Entra object IDs** (GUIDs), not emails or UPNs. Security trimming happens at query time.

## Hard Invariants (Schema Rules That Cause Rework If Missed)

These are design-time constraints. Getting them wrong may require recreating your connection and reingesting all data:

1. **`searchable` and `refinable` are mutually exclusive** — A property cannot be both. Decide at design time.
2. **Cannot add `refinable` via schema update** — Must be set in the initial schema or requires a new connection.
3. **Each semantic label maps to exactly one property** — No duplicates.
4. **Properties must be `retrievable` before receiving semantic labels.**
5. **`isExactMatchRequired` can only be set on non-searchable properties.**
6. **Schema updates that change search capabilities require reingestion** of all items.
7. **`title`, `url`, and `iconUrl` semantic labels are critical** — Without them, content may not surface in Copilot results at all.
8. **Content type for compliance connections must be `text`** — HTML is not supported when `enabledContentExperience` is `compliance`.
9. **Item IDs must be URL-safe** — No `#`, `?`, `&`, `/` characters.
10. **`@odata.type` annotation is required** for collection properties in item payloads.

## Schema Design Quick Reference

### Property Types

| Type | Use For | Example |
|------|---------|---------|
| `String` | Text, identifiers | `title`, `description` |
| `Int64` | Whole numbers | `priority`, `severity` |
| `Double` | Decimals | `price`, `score` |
| `DateTime` | Timestamps | `createdDate`, `dueDate` |
| `Boolean` | Flags | `isResolved`, `isActive` |
| `StringCollection` | Multi-value text | `tags`, `categories` |

### Attribute Decision Matrix

| Want to... | Set |
|------------|-----|
| Match in user search queries | `isSearchable: true` |
| Filter with KQL | `isQueryable: true` |
| Show in search results / use in labels | `isRetrievable: true` |
| Appear as UI filter control | `isRefinable: true` |
| Match exact identifiers (GUIDs, IDs) | `isExactMatchRequired: true` |

### Critical Semantic Labels (ordered by impact on discovery)

1. `title` — Main name/heading
2. `lastModifiedDateTime` — When last edited
3. `lastModifiedBy` — Who last edited
4. `url` — Direct link to source item
5. `fileName` / `fileExtension` — File metadata
6. `iconUrl` — Visual identifier

> See [schema-design.md](references/schema-design.md) for the complete labels list, property naming rules, aliases, and full attribute configuration guide.

## Content Property Best Practices

- **Put unstructured, searchable text in `content`**. Keep structured, filterable values as separate schema properties.
- **Concatenate related fields** — Merge `description`, `rootCause`, `resolution`, and `comments` into one content value with labeled sections.
- **Lead with the most important information** — Copilot performs best when key facts are at the beginning.
- **Use `html` for rich documents** with headings, lists, and tables. Use semantic tags (`<h1>`-`<h6>`, `<p>`, `<table>`), strip navigation/scripts/styles.
- **Use `text` for short, factual records** (tickets, database rows, API responses).

> See [content-and-ingestion.md](references/content-and-ingestion.md) for chunking strategies, throttle handling, and batch ingestion patterns.

## Data Aggregation Warning

Copilot **cannot reliably aggregate across multiple items** (counts, sums, averages). It retrieves a subset of results and may produce confident-sounding but incorrect totals.

**Solution: Pre-computed summary items.** Ingest dedicated summary items alongside detail records:

```json
{
  "id": "summary-engineering-2026-03",
  "properties": {
    "title": "Engineering Ticket Summary — March 2026",
    "reportType": "monthly-summary",
    "openTickets": 47,
    "closedTickets": 123
  },
  "content": {
    "value": "Engineering Team Summary for March 2026. Open tickets: 47. Closed: 123. Avg resolution: 18.5 hours.",
    "type": "text"
  }
}
```

When using Declarative Agents, instruct the agent to look for summary items first and never present search-result counts as exact totals.

## ACL Decision Tree

```
What identity system does your source use?
├── Microsoft Entra ID users/groups only
│   └── Use direct Entra object IDs in ACL (type: "user" or "group")
├── Non-Entra groups (Salesforce roles, ServiceNow groups, custom RBAC)
│   └── Create external groups via group sync API, then reference in ACL
├── Mixed identity sources
│   └── Map non-Entra identities to Entra object IDs during ingestion
│       + Use external groups for complex role structures
└── Public content (visible to all tenant users)
    └── Use type: "everyone" or "everyoneExceptGuests"
```

**Key rules:**
- `deny` always overrides `grant`
- Use group-based ACLs over per-user ACLs for maintainability
- Never expand group membership into individual item ACLs — use external groups instead
- Always use Entra object IDs, not emails or UPNs

## Pre-Launch Checklist

- [ ] App registered in Entra ID with required permissions + admin consent
- [ ] Schema registered with all properties and correct attributes
- [ ] Semantic labels assigned: `title`, `url`, `iconUrl` (minimum)
- [ ] Text properties marked as `searchable`
- [ ] Content property populated with rich, descriptive text
- [ ] ACLs configured and tested with multiple user roles
- [ ] Connection description is detailed and descriptive
- [ ] `urlToItemResolver` configured for URL-based item resolution
- [ ] User activities being sent (`created`, `modified`, `commented`, `viewed`)
- [ ] Inline results enabled in the "All" vertical (Admin Center)
- [ ] Throttle handling with exponential backoff implemented
- [ ] Items within 4 MB limit (chunked if necessary)
- [ ] Summary items ingested for commonly-asked aggregate questions

## Quick Start

See [getting-started/create-connection.cs](sample_codes/getting-started/create-connection.cs) for a complete C# example.
See [getting-started/create-connection-rest.http](sample_codes/getting-started/create-connection-rest.http) for raw REST API calls.

## Learn More

| Topic | How to Find |
|-------|-------------|
| Connectors overview | `microsoft_docs_fetch(url="https://learn.microsoft.com/microsoft-365/copilot/connectors/overview")` |
| Connectors API reference | `microsoft_docs_fetch(url="https://learn.microsoft.com/graph/connecting-external-content-connectors-api-overview")` |
| Schema registration guide | `microsoft_docs_fetch(url="https://learn.microsoft.com/graph/connecting-external-content-manage-schema")` |
| Managing items | `microsoft_docs_search(query="Microsoft Graph external items create update delete")` |
| API limits and throttling | `microsoft_docs_search(query="Microsoft Graph connectors API limits throttling")` |
| Build with Agents Toolkit | `microsoft_docs_fetch(url="https://learn.microsoft.com/microsoft-365/copilot/extensibility/build-your-first-connector")` |
| Connectors SDK | `microsoft_docs_search(query="Copilot connectors SDK custom connector sample")` |
| Result layout (Adaptive Cards) | `microsoft_docs_search(query="Microsoft Search customize results layout adaptive cards")` |
| Declarative Agents + connectors | `microsoft_docs_search(query="declarative agent copilot connector knowledge source")` |
| External groups (ACL) | `microsoft_docs_search(query="Microsoft Graph external groups permissions connectors")` |
| Troubleshooting | `microsoft_docs_search(query="Copilot connector troubleshoot items not appearing")` |
| Best practices reference | Fetch from `https://github.com/boddev/CustomCopilotConnectorBestPractices` |
| Schema archetypes | See [schema-archetypes.md](references/schema-archetypes.md) for pre-built templates |
