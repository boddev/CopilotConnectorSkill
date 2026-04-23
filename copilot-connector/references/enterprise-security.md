# Enterprise Security & Production Readiness

Comprehensive security guidance for deploying Copilot Connectors to production. Address these requirements **before requesting admin consent** from your security team.

## Application vs. Delegated Permissions

Copilot Connectors operate as **daemon/service identities** running on scheduled timers (daily full crawl, incremental crawls every few hours). This requires unattended, headless execution — which fundamentally requires application-level permissions.

### Why Delegated Permissions Don't Work in Production

| Requirement | Delegated | Application |
|---|---|---|
| Unattended automation | ❌ Requires interactive sign-in | ✅ Fully supported |
| Scheduled ingestion (daily + incremental) | ❌ Tokens expire with user sessions | ✅ Persistent, renewable tokens |
| Resilience to user lifecycle changes | ❌ Fails if user leaves org or MFA blocks refresh | ✅ Independent of any user account |
| Production-grade reliability | ❌ Not recommended by Microsoft | ✅ Recommended by Microsoft |
| Background indexing and refresh | ❌ Not supported | ✅ Fully supported |

> **Microsoft's documentation states** that delegated permissions are supported for development/testing but are **not recommended for production ingestion scenarios**.

### Justifying Application Permissions to Security Teams

Document these key points in your admin consent request:

1. **Why application permissions are required** — The connector operates as a headless service; delegated tokens cannot be acquired or refreshed without user interaction
2. **Why `.OwnedBy` is sufficient** — `ExternalConnection.ReadWrite.OwnedBy` and `ExternalItem.ReadWrite.OwnedBy` restrict access to only connections and items created by this specific app registration
3. **Why `.All` is not needed** — `.All` would grant access to all tenant connections; `.OwnedBy` limits scope to this app's own connections
4. **What the permissions cannot do** — These permissions cannot access emails, files, calendars, Teams messages, OneDrive, or any other Microsoft 365 data

## Secret Management: Azure Key Vault & Managed Identity

Production connectors must **never store credentials in source code, configuration files, or environment variables**.

### Recommended Architecture

```
┌─────────────────────┐      Managed Identity      ┌──────────────────┐
│  Azure App Service  │ ──────(Entra ID token)────▶ │  Azure Key Vault │
│  (Connector Host)   │                             │                  │
│                     │ ◀────(secrets at runtime)── │  • Graph Secret  │
│  System-Assigned    │                             │  • Source Secret  │
│  Managed Identity   │                             │  • Tenant Config  │
└─────────────────────┘                             └──────────────────┘
```

### Implementation Steps

1. **Azure Key Vault** — Create a Key Vault (Standard tier) and store all sensitive secrets:
   - Microsoft Entra client secret (for Graph API authentication)
   - Source system credentials (e.g., Salesforce client ID and secret)
   - Tenant ID and other configuration secrets

2. **System-Assigned Managed Identity** — Enable on the Azure App Service (or compute host). Eliminates the need for storing any credentials in application code.

3. **Key Vault RBAC** — Assign **Key Vault Secrets User** role to the App Service's Managed Identity. Grants `GET` permission on secrets only.

4. **Runtime secret access** — The connector authenticates to Key Vault using the Managed Identity (an Entra ID–based token issued automatically by the platform) and retrieves secrets via secure HTTPS calls.

### Authentication Hierarchy (Preferred → Least Preferred)

| Method | Security | Use When |
|---|---|---|
| **Managed Identity** | ✅ Highest — no credentials to manage | App runs in Azure (App Service, Functions, VM) |
| **Certificate-based authentication** | ✅ High — no shared secret | App runs outside Azure but can store certificates securely |
| **Client secret** | ⚠️ Medium — secret must be rotated | Development/testing only; avoid in production |
| **Device code flow** | ❌ Not for production | Interactive development only |

> **Never use** client secrets, device code flow, or service principal passwords directly in your connector code for production deployments.

## Source System Security Hardening

Securing the Microsoft Graph side (ACLs, permissions) is necessary but not sufficient. Enterprise connectors must also harden access to the **source data system** (CRM, ITSM, ERP, etc.) to enforce least-privilege principles.

### Recommended Controls

| Control | Purpose | Example |
|---|---|---|
| **Dedicated Integration User** | Service account with API-only access; cannot log in via browser | Salesforce Integration license, ServiceNow integration user |
| **Read-Only Profile/Role** | Disable Create, Edit, Delete on all objects; enable Read only on required objects | Clone a "Read Only" standard profile and restrict further |
| **Field-Level Security (FLS)** | Block access to sensitive fields (passwords, login history, SSN, PII) | Set `Visible=OFF` for sensitive fields on the integration user's profile |
| **Connected App / OAuth Policies** | Restrict API access to admin-approved users only; bind to the read-only profile | Admin-approved users only, restricted to the read-only profile |
| **IP Allowlisting** | Restrict API access to known Azure outbound IP ranges | Configure on Connected App and/or integration user profile |
| **API Rate Limits** | Cap API calls on the integration user to prevent abuse | Per-user rate limits on the source system |

### Example: Salesforce Source System Hardening

```
1. Create a Custom Profile
   Setup > Users > Profiles > New
   Clone from "Read Only" standard profile
   Disable Create/Edit/Delete on ALL objects
   Enable Read only on required objects (e.g., Account, Contact, Opportunity)

2. Apply Field-Level Security
   Profile > Field-Level Security > per object
   Set Visible=OFF for: password fields, login history, delegation fields
   Keep only fields needed for connector ingestion

3. Create Integration User
   License: Salesforce Integration (API-only; no browser login)
   Profile: Your custom Read-Only profile
   Active: checked

4. Configure Connected App
   OAuth Scopes: minimum required (e.g., "api" for REST API access)
   Permitted Users: "Admin approved users are pre-authorized"
   Assign only the Read-Only Profile
   Enable Client Credentials Flow with Run As = Integration User

5. IP Allowlisting (post-deployment)
   Restrict to Azure outbound IP ranges for your App Service region
```

> **Key insight**: Even when an OAuth scope is broad (e.g., Salesforce's `api` scope grants full REST API access), the **actual data access is controlled by the Integration User's Profile and Field-Level Security**, not by the OAuth scope alone.

## Unidirectional Data Flow / Read-Only Pipeline

Enterprise connectors should be designed as **one-directional, read-only pipelines**. Data flows from the source system into Microsoft Graph — never the reverse.

```
┌──────────────┐     READ ONLY      ┌───────────────────┐     WRITE       ┌──────────────────┐
│ Source System │ ──────────────────▶│ Copilot Connector │ ──────────────▶│ Microsoft Graph  │
│ (Salesforce,  │   GET requests     │ (Python, C#, etc.)│   PUT/POST      │ Semantic Index   │
│  ServiceNow)  │   only             │                   │   items + ACLs  │                  │
└──────────────┘                    └───────────────────┘                 └──────────────────┘
       ▲                                                                          │
       │                        NO DATA FLOWS BACK                                │
       └──────────────────────── ✕ ───────────────────────────────────────────────┘
```

### API Operations Inventory

Document every HTTP method, endpoint, and purpose for your security review:

**Source System Operations (Example: Salesforce)**

| HTTP Method | Endpoint | Purpose | Writes Data? |
|---|---|---|---|
| `POST` | `/services/oauth2/token` | OAuth authentication | No (auth only) |
| `GET` | `/services/data/{ver}/sobjects/{type}/describe/` | Discover available fields | No |
| `GET` | `/services/data/{ver}/query?q=SELECT...` | Fetch records via SOQL | No |
| `GET` | `/services/data/{ver}/query/{locator}` | Paginate through results | No |

**Microsoft Graph Operations**

| HTTP Method | Endpoint | Purpose | Frequency |
|---|---|---|---|
| `POST` | `/external/connections` | Create external connection | Once (first deploy) |
| `GET` | `/external/connections/{id}` | Check connection readiness | Every crawl |
| `POST` | `/external/connections/{id}/schema` | Deploy search schema | Once (first deploy) |
| `PUT` | `/external/connections/{id}/items/{itemId}` | Ingest record with ACLs | Per record, per crawl |
| `DELETE` | `/external/connections/{id}/items/{itemId}` | Remove deleted records | Per deleted record |
| `GET` | `/users/{id}?$select=id` | Map source user to Entra ID GUID | Per unique user, cached |

> **Zero POST/PUT/PATCH/DELETE operations to source data objects.** This distinction is critical for security reviewers.

## Defense in Depth — Layered Security Model

Implement **multiple independent security layers** so that no single control failure results in a breach.

### Source System Layers

| Layer | Control | Effect |
|---|---|---|
| 1 | **OAuth Scope** | Grants API access to the source system |
| 2 | **Dedicated Integration User** | Limits identity to API-only access |
| 3 | **Read-Only Profile / Role** | Create/Edit/Delete disabled on all objects |
| 4 | **Field-Level Security** | Blocks access to sensitive fields |
| 5 | **Connected App / OAuth Policy** | Admin-approved users only; bound to read-only profile |
| 6 | **IP Allowlist + Rate Limits** | Restricts API calls to Azure outbound IPs; caps volume |

### Microsoft Graph Permission Layers

| Layer | Control | Effect |
|---|---|---|
| 1 | **`.OwnedBy` permission scope** | App can only access its own connections and items |
| 2 | **Azure Key Vault + Managed Identity** | No credentials in code; secrets accessible only to authorized compute identity |
| 3 | **Key Vault RBAC** | Only App Service Managed Identity has `Key Vault Secrets User` role |
| 4 | **M365 Search ACL Trimming** | Ingested items include per-user ACLs; M365 Search enforces at query time |

## Blast Radius Analysis

Document the impact of credential compromise for each system.

### Microsoft Entra App Credential Compromise

| Scenario | Risk Level | Impact | Mitigation |
|---|---|---|---|
| Attacker creates rogue connections | LOW | Visible in Admin Center; require schema + items | Monitor via M365 Admin Center |
| Attacker injects fake search results | MEDIUM | Could insert items; ACLs still enforced at query time | Admin Center shows all items; Key Vault secret rotation |
| Attacker deletes the connection | MEDIUM | Indexed items lost; recoverable by re-running full crawl | Auto-recovery on next scheduled trigger |
| Attacker reads indexed items | LOW | Contains only data already in source system | Data already accessible to authorized source users |
| Attacker accesses emails, files, calendars | **NOT POSSIBLE** | `.OwnedBy` scope prevents access to any M365 data | Built-in Graph API scope boundary |
| Attacker accesses other apps' connections | **NOT POSSIBLE** | `.OwnedBy` limits to this app's own connections | Built-in Graph API scope boundary |

### Source System Credential Compromise

| Scenario | Risk Level | Impact | Mitigation |
|---|---|---|---|
| Attacker reads data | HIGH (without profile restriction) | All objects the Integration User can see | Read-Only Profile + FLS |
| Attacker writes or modifies data | **NOT POSSIBLE** (with Read-Only Profile) | Writes fail if Profile lacks Create/Edit | Read-Only Profile enforced at platform level |
| Attacker deletes records | **NOT POSSIBLE** (with Read-Only Profile) | Profile must explicitly grant Delete | Read-Only Profile enforced at platform level |
| Attacker exfiltrates data at scale | MEDIUM | Bulk queries possible within Profile scope | IP Allowlisting + Rate Limits + Audit Logging |
| Attacker accesses other tenants/orgs | **NOT POSSIBLE** | Credentials are org-specific | Platform-level boundary |

> **Adapt this template** to your specific source system. The goal is to demonstrate that `.OwnedBy` scope + source system hardening limits the blast radius.

## Deployment Architecture

### Recommended: Azure App Service (Daemon Workload)

```
┌──────────────────────────────────────────────────────────────┐
│                    Azure App Service                          │
│                                                              │
│  ┌─────────────────────┐    ┌────────────────────────┐       │
│  │  Connector Process  │    │  Scheduled Triggers    │       │
│  │  (Python / C# / JS) │    │                        │       │
│  │                     │    │  • Full crawl: daily    │       │
│  │  System-Assigned    │    │  • Incremental: 12h    │       │
│  │  Managed Identity   │    │  • On-demand: manual   │       │
│  └─────────┬───────────┘    └────────────────────────┘       │
│            │                                                  │
│            │  Managed Identity (Entra ID token)               │
│            ▼                                                  │
│  ┌─────────────────────┐                                     │
│  │  Azure Key Vault    │                                     │
│  │  (Secrets)          │                                     │
│  └─────────────────────┘                                     │
└──────────────────────────────────────────────────────────────┘
```

### Hosting Options

| Host | Best For | Key Consideration |
|---|---|---|
| **Azure App Service** | Always-on daemon workloads | System-Assigned Managed Identity |
| **Azure Functions (Timer Trigger)** | Lightweight, event-driven connectors | Consumption plan may have cold-start latency |
| **Azure Container Apps** | Complex connectors with specific runtime deps | Managed Identity supported; more operational overhead |
| **On-Premises Server + Connector Agent** | Data sources behind corporate firewalls | Requires the Microsoft Graph Connector Agent; use SDK |
| **Azure VM** | Full control over runtime | Higher maintenance burden; use Managed Identity |

### Crawl Scheduling

| Crawl Type | Purpose | Recommended Frequency |
|---|---|---|
| **Full crawl** | Initial load + periodic reconciliation | Daily or weekly |
| **Incremental crawl** | Detect additions, updates, deletions | Every 4–12 hours |
| **On-demand crawl** | After bulk source changes or schema updates | As needed |

> **Connection auto-recovery**: Design your connector so that if the external connection is deleted, the next scheduled crawl automatically recreates the connection, reregisters the schema, and performs a full re-ingestion.

## Audit Logging & IP Allowlisting

### Source System Audit Logging

Enable comprehensive audit logging to track all API calls by the connector's integration user:

- **Salesforce**: Enable Setup Audit Trail and Event Monitoring
- **ServiceNow**: Enable System Audit with table-level auditing
- **Custom APIs**: Implement request logging with correlation IDs matching crawl sessions

### Microsoft Graph Audit Logging

Monitor in M365 Admin Center under **Search & intelligence > Connectors**:
- Connection status changes (active, paused, failed)
- Item count and quota usage over time
- Crawl history, errors, and throughput metrics

### IP Allowlisting

1. **Identify outbound IPs** — In Azure App Service: **Properties** > **Outbound IP Addresses**
2. **Configure source system** — Add IPs to Connected App or firewall rules
3. **Re-validate after changes** — Outbound IPs may change if you move App Service Plan or region

> IP allowlisting is a defense-in-depth measure, not a primary authentication mechanism.

## Secret Rotation

Define and document a secret rotation schedule:

| Secret | Rotation Frequency | Procedure |
|---|---|---|
| Microsoft Entra client secret | Every 6–12 months | Generate new secret in Entra ID → update Key Vault → verify connector still authenticates → delete old secret |
| Source system API credentials | Per source system policy | Update in source system → update Key Vault → verify |
| Key Vault access policies | Review quarterly | Audit RBAC assignments; remove stale identities |

## Admin Consent Package Checklist

Prepare this documentation for your security team:

| Document | Purpose | Key Contents |
|---|---|---|
| **Permission Justification** | Explain each requested permission | Permission name, type (Application), scope (`.OwnedBy`), what it CAN and CANNOT do |
| **Architecture Diagram** | Show end-to-end data flow | Source system → Connector → Microsoft Graph → M365 Search/Copilot |
| **API Operations Inventory** | Enumerate every API call | HTTP method, endpoint, purpose, frequency, writes data? |
| **Blast Radius Analysis** | Assess credential compromise impact | Risk level, impact, mitigations per scenario |
| **Security Controls Summary** | Document defense-in-depth layers | Each layer, what it restricts, implementation status |
| **Source System Hardening** | Detail source-side security posture | Integration user, read-only profile, FLS, connected app policies |
| **Secret Management Plan** | Explain credential storage and rotation | Key Vault, Managed Identity, RBAC, rotation schedule |
| **Deployment Architecture** | Describe hosting and scheduling | Compute host, crawl schedule, auto-recovery strategy |

### Key Messages for Security Reviewers

1. **Minimal permissions** — `.OwnedBy` is the least-privileged variant; cannot access any other M365 data
2. **Read-only source access** — Zero write operations to the source system (when properly hardened)
3. **Zero credentials in code** — All secrets in Azure Key Vault, accessed via Managed Identity
4. **ACL enforcement** — Ingested items inherit source permissions; M365 Search enforces at query time
5. **Limited blast radius** — Credential compromise cannot access emails, files, calendars, Teams, or OneDrive

## Enterprise Security Checklist

- [ ] Application permissions used (not delegated) for production ingestion
- [ ] `.OwnedBy` permission variants used instead of `.All`
- [ ] All secrets stored in Azure Key Vault (not in code, config, or env vars)
- [ ] System-Assigned Managed Identity enabled on compute host
- [ ] Key Vault RBAC: only App Service Managed Identity has `Key Vault Secrets User` role
- [ ] Dedicated integration user created on source system (API-only, no browser login)
- [ ] Read-only profile/role applied to integration user (Create/Edit/Delete disabled)
- [ ] Field-Level Security configured to block sensitive fields
- [ ] Connected App / OAuth policies restricted to admin-approved users only
- [ ] IP allowlisting configured on source system (Azure outbound IPs only)
- [ ] API rate limits and audit logging enabled on source system
- [ ] Data flow is unidirectional — zero write operations to source system
- [ ] API operations inventory documented
- [ ] Blast radius analysis completed for both Graph and source system credentials
- [ ] Defense-in-depth layers documented with implementation status
- [ ] Permission justification package prepared for security team review
- [ ] Connection auto-recovery logic implemented
- [ ] Secret rotation schedule defined and documented
