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

## End-to-End Workflow (7 Steps)

| Step | What | Key API/Action |
|------|------|-----------------|
| 1. Prerequisites & Permissions | Register app in Entra ID, grant `ExternalConnection.ReadWrite.OwnedBy` + `ExternalItem.ReadWrite.OwnedBy`, get admin consent | Entra admin center |
| 2. Create Connection | Register external data source with unique ID, name, and rich description | `POST /external/connections` |
| 3. Integrate Data Enhancer | Add the Python or TypeScript data-enhancer script to the connector and use its schema suggestion as schema input | `sample_codes/data-enhancer/` |
| 4. Register Schema | Define properties, types, search attributes, and semantic labels | `POST /external/connections/{id}/schema` |
| 5. Crawl, Enhance, Ingest Items | Every full and incremental crawl must route new/changed source data through the data enhancer before Graph ingestion | Enhancer output + `PUT /external/connections/{id}/items/{itemId}` |
| 6. Configure Experiences | Enable inline results, set up search verticals, add urlToItemResolver, send user activities | M365 Admin Center + API |
| 7. Validate & Monitor | Verify items appear in search/Copilot, monitor crawl health, check quota usage | Admin Center + test queries |

> **Schema registration is asynchronous.** After POSTing a schema, poll `GET /external/connections/{id}/schema` until `status` is `completed` before ingesting items. This can take up to 10 minutes.

## Required Data Enhancer Integration

When this skill is invoked to create or scaffold a custom Copilot Connector, integrate the data enhancer by default. Do not build a connector that ingests raw crawled records or documents directly unless the user explicitly requests raw ingestion without enhancement (e.g., "skip the data enhancer", "I don't need content enhancement", or "ingest raw data directly").

Use the reusable enhancer assets in:

| Runtime | Skill asset |
|---------|-------------|
| Python | `sample_codes/data-enhancer/python/enhance_for_copilot.py` |
| TypeScript | `sample_codes/data-enhancer/typescript/src/enhance_for_copilot.ts` |

Required connector pipeline:

1. **Crawl to a staging area** - write every new or changed source record/document from full and incremental crawls to a temporary dataset folder.
2. **Run the data enhancer** - process the staged dataset with the Python or TypeScript enhancer before item ingestion.
3. **Apply/merge schema suggestion** - review `schema-suggestion.json`, merge any source-specific schema requirements, register the final schema, and poll until registration completes.
4. **Ingest enhanced items only** - read `enhanced-items.jsonl`; use each item's `properties` and `content.value` as the Graph external item payload. Apply source ACLs in the connector pipeline if the enhancer output does not include final ACLs.
5. **Fail closed on enhancer errors** - if the enhancer fails, skip Graph item upserts for that crawl and surface/log the error. Never silently fall back to raw item ingestion.
6. **Persist crawl state after successful ingestion** - update checkpoints only after enhanced items have been successfully written to Graph.

The intended flow is:

```text
Source system crawl -> staging dataset -> data enhancer -> enhanced-items.jsonl -> ACL application -> Graph externalItem upsert
```

For TypeScript connectors, either import the enhancer helpers directly or execute the built CLI from the crawl job. For Python connectors, either import `enhance_for_copilot.py` or run it as a subprocess from the crawl job. In both cases, every crawl path that can create or update external items must pass through this enhancer stage.

## Choosing the Right Tool

Answer these questions in order to find the right tool:

| Step | Question | If YES |
|------|----------|--------|
| 1 | Is there a pre-built connector for your data source? | → **Pre-built connector** (M365 Admin Center). Done. |
| 2 | Do you need live, real-time access instead of indexed content? | → **Federated Connectors** (Preview). Done. |
| 3 | Is your data source on-premises? | → **Copilot Connectors SDK + Connector Agent**. Done. |
| 4 | Are you building a Declarative Agent with the connector? | → **Microsoft 365 Agents Toolkit**. Done. |
| 5 | Do you need full crawl management (scheduling, dedup, change detection)? | → **Copilot Connectors SDK** or **Agents Toolkit**. Done. |
| 6 | None of the above? | → **Microsoft Graph REST API** for maximum flexibility. |

| Tool | Language | Best For |
|------|----------|----------|
| **Microsoft 365 Agents Toolkit** | TypeScript/C# | New connectors with integrated agent development |
| **Microsoft Graph REST API** | Any (HTTP) | Maximum flexibility, polyglot teams, serverless |
| **Microsoft Graph SDK** | C# / Python / Java / TypeScript | Production-grade with type safety and IDE support |
| **Copilot Connectors SDK** | C# (primary) | Production-grade with full crawl management |
| **Pre-built connectors** | No code | 100+ supported data sources |
| **Federated connectors** (Preview) | Any (HTTP) | Real-time, non-indexed access to live data |

### SDK Quick Reference

| SDK | Package | Auth Package |
|-----|---------|--------------|
| **C# (.NET)** | `Microsoft.Graph` (NuGet) | `Azure.Identity` |
| **Python** | `msgraph-sdk` (pip) | `azure-identity` |
| **Java** | `com.microsoft.graph:microsoft-graph` (Maven) | `com.azure:azure-identity` |
| **TypeScript** | `@microsoft/microsoft-graph-client` (npm) | `@azure/identity` |

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

### Data Enhancer
The data enhancer converts raw source crawl output into Copilot-friendly external items. It supports tabular files (`csv`, `tsv`) and document-like files (`txt`, `md`, `html`, `json`, `jsonl`), emits `enhanced-items.jsonl`, produces an inspection CSV, and generates `schema-suggestion.json`. Connector implementations generated from this skill should include the enhancer as a required pre-ingestion stage for both full and incremental crawls.

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

> See [content-and-ingestion.md](references/content-and-ingestion.md) for all 5 aggregation strategies, DA instruction templates, and anti-patterns to avoid.

## Surfacing Data in Copilot

To maximize Copilot discovery and relevance:

1. **Rich connection description** — Answer: what content? Who uses it? When? Use `contentCategory` for classification.
2. **Semantic labels** — Assign at minimum: `title`, `url`, `iconUrl`. Priority order for discovery: `title` → `lastModifiedDateTime` → `lastModifiedBy` → `url`.
3. **Mark properties searchable** — The `searchable` attribute is the most critical for Copilot matching.
4. **Configure rank hints** — For searchable properties not mapped to labels, set importance in Admin Center.
5. **Add urlToItemResolver** — Enables URL detection when users share links to your external content.
6. **Send user activities** — `created`, `modified`, `commented`, `viewed` boost item relevance.
7. **Enable inline results** — In Admin Center: Search & intelligence > Verticals > All > Show results inline.
8. **Configure result types** — Optional Adaptive Card layouts for richer search result presentation.

> See [content-and-ingestion.md](references/content-and-ingestion.md) for API examples (urlToItemResolver, activities, Adaptive Cards).

## Enterprise Security & Production Readiness

Before deploying to production, address these security requirements:

- **Use application permissions** (not delegated) — connectors are daemon workloads requiring unattended execution
- **Use `.OwnedBy` scope** — restricts access to only this app's connections and items
- **Store secrets in Azure Key Vault** — use Managed Identity for zero-credential deployment
- **Harden source system access** — dedicated integration user, read-only profile, field-level security
- **Enforce unidirectional data flow** — read from source, write to Graph, never the reverse
- **Document defense-in-depth layers** — multiple independent security controls
- **Complete blast radius analysis** — assess impact of credential compromise
- **Prepare admin consent package** — permission justification, architecture diagram, API inventory

> See [enterprise-security.md](references/enterprise-security.md) for the complete enterprise security reference, blast radius templates, deployment architecture, and admin consent checklist.

## Monitoring & Troubleshooting

Monitor connector health in the M365 Admin Center under **Search & intelligence > Connectors**. Common issues include missing semantic labels, incorrect ACLs, and throttle errors.

> See [troubleshooting.md](references/troubleshooting.md) for the debugging workflow, common issues table, and testing checklist.

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
- [ ] Filter properties marked as `queryable` and/or `refinable`
- [ ] Display properties marked as `retrievable`
- [ ] Content property populated with rich, descriptive text
- [ ] Data enhancer integrated into every full and incremental crawl path before Graph item upsert
- [ ] `schema-suggestion.json` reviewed and merged into the connector schema before registration
- [ ] Crawl job fails closed if the data enhancer fails; raw ingestion cannot bypass the enhancer
- [ ] ACLs configured and tested with multiple user roles
- [ ] Connection description is detailed and descriptive
- [ ] `urlToItemResolver` configured for URL-based item resolution
- [ ] User activities being sent (`created`, `modified`, `commented`, `viewed`)
- [ ] Inline results enabled in the "All" vertical (Admin Center)
- [ ] Throttle handling with exponential backoff implemented
- [ ] Items within 4 MB limit (chunked if necessary)
- [ ] Incremental crawl strategy defined for ongoing sync
- [ ] Summary items ingested for commonly-asked aggregate questions

## Copilot Optimization Checklist

- [ ] Content is information-dense and well-structured
- [ ] All new/changed crawl data is transformed by the data enhancer before indexing
- [ ] Content leads with the most important information
- [ ] Multiple text fields concatenated into content with labels
- [ ] Summary items ingested for aggregate data queries
- [ ] Declarative Agent instructions include property descriptions
- [ ] Declarative Agent instructions address aggregation limitations
- [ ] Properties have clear, descriptive names (not abbreviations)
- [ ] Aliases defined for common synonyms
- [ ] Connection description answers: what, who, when, characteristics

## Security Checklist

- [ ] ACLs mirror source system permissions
- [ ] External groups used for non-Entra ID permissions
- [ ] Group memberships not expanded into individual ACLs
- [ ] `deny` entries used sparingly and intentionally
- [ ] Compliance content type set to `text` (if applicable)
- [ ] Sensitive data excluded or properly access-controlled
- [ ] All Entra object IDs validated (not emails or UPNs)

> See [enterprise-security.md](references/enterprise-security.md) for the full enterprise security & production readiness checklist.

## Quick Start

Pick the language that matches your project:

| Language | Getting Started | Common Patterns |
|----------|----------------|-----------------|
| **C# (.NET)** | [create-connection.cs](sample_codes/csharp/getting-started/create-connection.cs) | [csharp/common-patterns/](sample_codes/csharp/common-patterns/) |
| **Python** | [create-connection.py](sample_codes/python/getting-started/create-connection.py) | [python/common-patterns/](sample_codes/python/common-patterns/) |
| **Java** | [CreateConnection.java](sample_codes/java/getting-started/CreateConnection.java) | [java/common-patterns/](sample_codes/java/common-patterns/) |
| **TypeScript** | [create-connection.ts](sample_codes/typescript/getting-started/create-connection.ts) | [typescript/common-patterns/](sample_codes/typescript/common-patterns/) |
| **REST API** | [create-connection-rest.http](sample_codes/rest/create-connection-rest.http) | — |
| **Agents Toolkit** | [agents-toolkit/README.md](sample_codes/agents-toolkit/README.md) | [agents-toolkit/](sample_codes/agents-toolkit/) |
| **Data Enhancer** | [data-enhancer/README.md](sample_codes/data-enhancer/README.md) | [Python](sample_codes/data-enhancer/python/) / [TypeScript](sample_codes/data-enhancer/typescript/) |

Each language folder includes the same 6 samples: end-to-end connection setup, schema registration, item ingestion, throttle-resilient batch ingestion, ACL configuration, and incremental sync.

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
| Troubleshooting | See [troubleshooting.md](references/troubleshooting.md) for common issues, then `microsoft_docs_search(query="Copilot connector troubleshoot items not appearing")` |
| Enterprise security | See [enterprise-security.md](references/enterprise-security.md) for production readiness |
| Best practices reference | See `https://github.com/boddev/CustomCopilotConnectorBestPractices` for the comprehensive guide |
| Schema archetypes | See [schema-archetypes.md](references/schema-archetypes.md) for pre-built templates |
