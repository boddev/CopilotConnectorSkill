# Copilot Connector Skill

An AI agent skill that transforms GitHub Copilot CLI and Claude Code into specialized assistants for building **Microsoft 365 Copilot Connectors** (formerly Microsoft Graph Connectors).

When activated, this skill gives your AI agent deep knowledge of the Microsoft Graph connectors API, schema design best practices, content ingestion patterns, ACL configuration, enterprise security, and production readiness — so it can guide you through every step of creating a custom connector that surfaces external data in Microsoft 365 Copilot and Microsoft Search.

All connectors built with this skill follow the [**Copilot Connector Best Practices**](https://github.com/boddev/CustomCopilotConnectorBestPractices) — a comprehensive guide covering schema design, content optimization, security hardening, and production deployment.

## What Are Copilot Connectors?

Copilot Connectors bring external data into the Microsoft Graph semantic index. Once indexed, that data becomes discoverable across Microsoft 365 — users can ask Copilot natural-language questions and get answers grounded in your external systems (helpdesks, wikis, CRMs, databases, etc.).

## What This Skill Does

| Capability | How It Helps |
|---|---|
| **End-to-end workflow guidance** | Walks through the full 7-step process: prerequisites → connection → data enhancement → schema → enhanced ingestion → experiences → validation |
| **Schema design** | Knows all property types, attributes, semantic labels, and the hard rules that cause rework if missed |
| **7 schema archetypes** | Pre-built schema templates for knowledge bases, tickets, CRM, HR, financial, product catalogs, and file repositories |
| **Multi-language code generation** | Provides C#, Python, Java, TypeScript SDK patterns, and REST API examples for every operation |
| **Agents Toolkit integration** | Guides building connectors using the M365 Agents Toolkit with TypeScript + Azure Functions |
| **Content formatting** | Guides text vs HTML decisions, content concatenation, and Copilot summarization optimization |
| **Chunking strategies** | Handles the 4 MB payload limit with logical, fixed-size, and semantic boundary chunking |
| **ACL configuration** | Covers user, group, everyone, external groups, and deny patterns |
| **Copilot optimization** | urlToItemResolver, user activities, Adaptive Card result types, rank hints, Declarative Agent guidance |
| **Aggregation awareness** | Warns that Copilot can't aggregate across items and suggests pre-computed summary patterns, DA instructions, and anti-patterns |
| **Delimited data handling** | CSV/TSV parsing, row-per-item mapping, multi-value delimiters, large file strategies |
| **Data enhancer integration** | Includes Python and TypeScript scripts that transform every full and incremental crawl into Copilot-friendly enhanced items before Graph ingestion |
| **Enterprise security** | App vs delegated permissions, Key Vault + Managed Identity, source system hardening, blast radius analysis |
| **Production readiness** | Deployment architecture, crawl scheduling, audit logging, admin consent package preparation |
| **Troubleshooting** | Common issues table, debugging workflow, SDK test utility, Admin Center monitoring |
| **Throttle resilience** | Provides retry logic, batch concurrency, and incremental sync patterns |
| **Dynamic lookups** | Includes Microsoft Learn MCP queries for deeper topics not stored locally |

## Project Structure

```
copilot-connector/
├── SKILL.md                                    # Core skill knowledge and instructions
├── references/
│   ├── schema-design.md                        # Property types, attributes, semantic labels, aliases
│   ├── content-and-ingestion.md                # Content formatting, chunking, throttling, batch patterns
│   ├── schema-archetypes.md                    # 7 pre-built schema templates for common scenarios
│   ├── enterprise-security.md                  # Production readiness, Key Vault, blast radius, admin consent
│   └── troubleshooting.md                      # Common issues, debugging workflow, testing checklist
└── sample_codes/
    ├── csharp/
    │   ├── getting-started/
    │   │   └── create-connection.cs            # End-to-end C# example
    │   └── common-patterns/
    │       ├── schema-registration.cs          # Schema registration with status polling
    │       ├── item-ingestion.cs               # Item creation, content building, upsert/delete
    │       ├── throttle-resilient-ingestion.cs # Retry logic + batch concurrency control
    │       ├── acl-configuration.cs            # All ACL patterns + external group management
    │       └── incremental-sync.cs             # Change detection + delta sync
    ├── python/
    │   ├── getting-started/
    │   │   └── create-connection.py            # End-to-end Python example
    │   └── common-patterns/
    │       ├── schema-registration.py          # Schema registration with async polling
    │       ├── item-ingestion.py               # Item creation, content building, upsert/delete
    │       ├── throttle-resilient-ingestion.py # Retry + asyncio.Semaphore concurrency
    │       ├── acl-configuration.py            # All ACL patterns + external group management
    │       └── incremental-sync.py             # Change detection + delta sync
    ├── java/
    │   ├── getting-started/
    │   │   └── CreateConnection.java           # End-to-end Java example
    │   └── common-patterns/
    │       ├── SchemaRegistration.java          # Schema registration with status polling
    │       ├── ItemIngestion.java               # Item creation, content building, upsert/delete
    │       ├── ThrottleResilientIngestion.java  # Retry + ExecutorService concurrency
    │       ├── AclConfiguration.java            # All ACL patterns + external group management
    │       └── IncrementalSync.java             # Change detection + delta sync
    ├── typescript/
    │   ├── getting-started/
    │   │   └── create-connection.ts            # End-to-end TypeScript example
    │   └── common-patterns/
    │       ├── schema-registration.ts          # Schema registration with polling
    │       ├── item-ingestion.ts               # Item creation, content building, upsert/delete
    │       ├── throttle-resilient-ingestion.ts # Retry + semaphore concurrency
    │       ├── acl-configuration.ts            # All ACL patterns + external group management
    │       └── incremental-sync.ts             # Change detection + delta sync
    ├── data-enhancer/
    │   ├── README.md                           # Required crawl → enhancer → Graph ingestion contract
    │   ├── python/
    │   │   ├── enhance_for_copilot.py          # Python enhancer for tabular and document-like crawls
    │   │   ├── nontabular.py                   # Compatibility exports for non-tabular helpers
    │   │   ├── pyproject.toml
    │   │   └── README.md
    │   └── typescript/
    │       ├── src/
    │       │   ├── enhance_for_copilot.ts      # TypeScript enhancer for tabular and document-like crawls
    │       │   └── nontabular.ts               # Compatibility exports for non-tabular helpers
    │       ├── package.json
    │       ├── package-lock.json
    │       ├── tsconfig.json
    │       └── README.md
    ├── rest/
    │   └── create-connection-rest.http         # Raw REST API calls
    └── agents-toolkit/
        ├── README.md                           # Agents Toolkit setup and walkthrough guide
        ├── connector-config.ts                 # Connection + schema configuration
        ├── data-source.ts                      # Data source integration patterns
        └── declarative-agent-connector.tsp     # TypeSpec Declarative Agent example
```

## Installation

### GitHub Copilot CLI

Copy or clone the `copilot-connector/` folder into your Copilot CLI skills directory:

```bash
# Clone the repo
git clone https://github.com/boddev/CopilotConnectorSkill.git

# Copy the skill into your project's skills directory
cp -r CopilotConnectorSkill/copilot-connector /path/to/your/project/.github/skills/

# Or into your personal skills directory
cp -r CopilotConnectorSkill/copilot-connector ~/.copilot/skills/
```

### Claude Code

Add the skill to your Claude Code configuration:

```bash
# Clone the repo
git clone https://github.com/boddev/CopilotConnectorSkill.git

# Copy to your project's skill directory
cp -r CopilotConnectorSkill/copilot-connector /path/to/your/project/.claude/skills/
```

### Manual Installation

You can also reference the skill directly from any location by pointing your agent configuration to the `copilot-connector/` folder. The only required file is `SKILL.md` — the references and sample codes are loaded on demand.

## Usage Examples

### Example 1: Create a Helpdesk Ticket Connector

**You say:**
> "I need to build a Copilot Connector that indexes helpdesk tickets from our ServiceNow instance. Each ticket has an ID, title, description, status, priority, assignee, and creation date."

**The agent will:**
1. Reference the **Tickets/Work Items archetype** from `schema-archetypes.md`
2. Generate a schema with the correct property types, attributes, and semantic labels
3. Produce C#, Python, Java, or TypeScript code for creating the connection and registering the schema
4. Build a content concatenation pattern that merges description + resolution + comments
5. Set up ACLs based on your permission model
6. Remind you to enable inline results in the M365 Admin Center

**Sample output (schema snippet):**
```json
{
  "baseType": "microsoft.graph.externalItem",
  "properties": [
    {
      "name": "ticketId",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isExactMatchRequired": true
    },
    {
      "name": "title",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["title"]
    },
    {
      "name": "status",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true
    }
  ]
}
```

### Example 2: Ingest a Knowledge Base with Large Articles

**You say:**
> "I have a Confluence wiki with 5,000 articles. Some articles are very long — over 100 pages. How should I ingest this into a Copilot Connector?"

**The agent will:**
1. Recommend the **Knowledge Base archetype** schema with `html` content type
2. Explain the 4 MB item size limit and when chunking is actually needed
3. Suggest **logical section chunking** (split at headings) as the primary strategy
4. Show how to make chunks self-contained with contextual headers
5. Generate throttle-resilient batch ingestion code with a semaphore for concurrency
6. Advise stripping navigation chrome, scripts, and styles from the HTML
7. Recommend an incremental sync strategy for ongoing updates

### Example 3: Handle Complex Permissions

**You say:**
> "Our data source uses custom role-based access. Users belong to Salesforce permission sets that don't map directly to Entra ID groups. How do I set up ACLs?"

**The agent will:**
1. Walk through the **ACL decision tree** and identify the external groups pattern
2. Show how to create external groups via the Graph API
3. Generate code to map Salesforce permission sets to external groups
4. Add Entra ID users to the external groups
5. Reference those groups in item ACLs
6. Warn against expanding group membership into individual item ACLs

### Example 4: Build a Connector with the Agents Toolkit

**You say:**
> "I want to build a Copilot Connector using the Agents Toolkit in VS Code. My data is in a custom REST API."

**The agent will:**
1. Walk through the **Agents Toolkit** setup (VS Code extension, prerequisites)
2. Guide you through creating a new Copilot Connector project
3. Show how to customize `src/custom/` for your REST API data source
4. Help design the schema in `src/references/`
5. Explain the F5 local development experience
6. Guide deployment to Azure Functions
7. Optionally, show how to create a Declarative Agent that uses the connector as a knowledge source

## Prerequisites for Building Connectors

This skill helps you *build* connectors. To actually run them, you'll need:

- **Microsoft 365 tenant** with appropriate licenses
- **App registration** in Microsoft Entra ID with permissions:
  - `ExternalConnection.ReadWrite.OwnedBy`
  - `ExternalItem.ReadWrite.OwnedBy`
- **Admin consent** for the application
- **Microsoft 365 Copilot license** (to test Copilot integration)

## Best Practices

This skill integrates all best practices from the **[Copilot Connector Best Practices & Development Guide](https://github.com/boddev/CustomCopilotConnectorBestPractices)**. Every connector built with this skill follows these practices, covering:

- **Schema design** — Property naming, types, attributes, semantic labels, aliases, and the hard invariants that cause rework if missed
- **Content optimization** — Structuring content for Copilot summarization, HTML best practices, content concatenation patterns
- **Data handling** — Chunking strategies, delimited data (CSV/TSV), large payload management
- **Aggregation** — Pre-computed summaries, Declarative Agent instructions, anti-patterns
- **Copilot integration** — urlToItemResolver, user activities, Adaptive Cards, rank hints
- **Access control** — ACL patterns, external groups, deny rules
- **Enterprise security** — Key Vault + Managed Identity, source system hardening, defense-in-depth, blast radius analysis
- **Production readiness** — Deployment architecture, crawl scheduling, admin consent package, secret rotation
- **Troubleshooting** — Common issues, debugging workflow, Admin Center monitoring

### Updating Best Practices

To pull the latest version of the best practices guide into a local copy for offline reference:

```bash
# From the skill directory
curl -sL https://raw.githubusercontent.com/boddev/CustomCopilotConnectorBestPractices/main/ReadMe.md \
  -o references/best-practices-guide.md
```

This is optional — the skill already embeds all best practices in its reference files. Use this if you want the original comprehensive guide available locally.

## Key Resources

| Resource | Link |
|---|---|
| Copilot Connectors Overview | https://learn.microsoft.com/microsoft-365/copilot/connectors/overview |
| Connectors API Reference | https://learn.microsoft.com/graph/connecting-external-content-connectors-api-overview |
| Schema Best Practices | https://learn.microsoft.com/graph/connecting-external-content-manage-schema |
| Build with Agents Toolkit | https://learn.microsoft.com/microsoft-365/copilot/extensibility/build-your-first-connector |
| Best Practices Guide | https://github.com/boddev/CustomCopilotConnectorBestPractices |

## Contributing

Contributions are welcome! If you have improvements to the schema archetypes, additional code samples, or corrections to the best practices, please open a pull request.

## License

This project is licensed under the [MIT License](LICENSE).
