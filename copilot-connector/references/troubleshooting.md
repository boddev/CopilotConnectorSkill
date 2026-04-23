# Monitoring, Testing & Troubleshooting

Guidance for validating, monitoring, and diagnosing issues with Copilot Connectors.

## SDK Test Utility

The Copilot Connectors SDK includes a **test utility** with pre-built validation scenarios:

- Connection creation/validation
- Schema registration verification
- Item ingestion with various content types
- ACL validation
- Crawl simulation

Use the test utility to validate your connector code **before deploying to production**. It catches common issues like malformed payloads, invalid ACLs, and schema conflicts early in development.

## Admin Center Monitoring

Monitor connector health in the **M365 Admin Center** under **Search & intelligence > Connectors**:

| Metric | Where to Find | What to Look For |
|--------|--------------|------------------|
| **Connection status** | Connectors dashboard | Active, paused, or failed states |
| **Item count** | Connection details | Matches expected count from source system |
| **Quota usage** | Connectors overview | Percentage of tenant item quota consumed |
| **Crawl history** | Connection details > Activity | Successful crawls, errors, items processed |
| **Throughput** | Connection details > Activity | Items ingested per hour/day |
| **Error details** | Connection details > Errors | Specific failure reasons per item |

### Health Check Cadence

| Check | Frequency | Action on Failure |
|-------|-----------|-------------------|
| Connection status | Daily | Investigate if paused/failed; check credentials |
| Item count drift | Weekly | Compare with source system; run full crawl if mismatched |
| Quota usage | Monthly | Plan for capacity if approaching limit |
| Crawl errors | After each crawl | Fix and re-ingest failed items |

## Common Issues and Resolutions

| Issue | Likely Cause | Resolution |
|---|---|---|
| Items not appearing in search | Schema not registered or items not indexed | Verify schema status is `completed`; check item count in Admin Center |
| HTTP 429 errors during ingestion | Throttle limits exceeded | Implement exponential backoff with `Retry-After` header; reduce concurrency |
| Content not surfacing in Copilot | Missing semantic labels or `searchable` attribute | Add `title`, `url`, `iconUrl` labels; mark text properties as searchable |
| ACL errors on item ingestion | Invalid user/group IDs | Verify Entra ID resolution; ensure GUIDs not emails/UPNs |
| Schema update fails | Attempting incompatible changes | Some changes (e.g., adding `refinable`) require creating a new connection |
| Items showing to wrong users | Incorrect ACL configuration | Audit ACLs; test with users of different permission levels |
| Schema registration stuck | Long-running async operation | Poll `GET /external/connections/{id}/schema` — can take up to 10 minutes |
| `@odata.type` errors | Missing type annotation on collections | Add `"tags@odata.type": "Collection(Edm.String)"` to item payload |
| Item ID rejected | Non-URL-safe characters | Remove `#`, `?`, `&`, `/` from item IDs |
| Content truncated in search | Excessively large retrievable properties | Reduce number/size of retrievable properties; put large text in `content` |
| Incremental crawl missing updates | Change detection not tracking all modifications | Verify delta token or timestamp-based tracking covers all relevant fields |
| Connection auto-deleted | Admin action or security event | Implement auto-recovery: next crawl recreates connection + schema + full re-ingestion |

## Debugging Workflow

```
Item not appearing in Copilot/Search?
├── Is the connection active?
│   ├── NO → Check credentials, permissions, admin consent
│   └── YES
│       ├── Is the schema registered (status: completed)?
│       │   ├── NO → Wait or re-register schema
│       │   └── YES
│       │       ├── Is the item ingested (check Admin Center)?
│       │       │   ├── NO → Check ingestion logs for errors
│       │       │   └── YES
│       │       │       ├── Does the user have ACL access?
│       │       │       │   ├── NO → Fix ACL; verify Entra ID resolution
│       │       │       │   └── YES
│       │       │       │       ├── Are semantic labels assigned (title, url, iconUrl)?
│       │       │       │       │   ├── NO → Add labels; may need reingestion
│       │       │       │       │   └── YES
│       │       │       │       │       ├── Are text properties marked searchable?
│       │       │       │       │       │   ├── NO → Update schema; reingest
│       │       │       │       │       │   └── YES
│       │       │       │       │       │       └── Are inline results enabled?
│       │       │       │       │       │           ├── NO → Enable in Admin Center
│       │       │       │       │       │           └── YES → Allow indexing time (up to 24h)
```

## Schema Update Rules

| Operation | Supported? | Reingestion? |
|-----------|-----------|--------------|
| Add a new property | ✅ Yes | Recommended |
| Add/remove search capability | ✅ Yes | **Required** |
| Add refinable attribute | ❌ Not via update | Requires new connection |
| Add/remove alias | ✅ Yes | Not needed |
| Add/remove semantic label | ✅ Yes | Not needed |

> **After any schema update, reindex items** to ensure consistent behavior across all items.

## Testing Checklist

- [ ] Connection creates successfully
- [ ] Schema registers and reaches `completed` status
- [ ] Items ingest without errors
- [ ] Items appear in Microsoft Search with correct display
- [ ] Semantic labels display correctly (title, URL clickable, icon visible)
- [ ] ACLs work — authorized users see items, unauthorized users don't
- [ ] KQL filters work on queryable properties
- [ ] Refinable properties appear as filter controls in search
- [ ] Content appears in Copilot responses (with Copilot license)
- [ ] Throttle handling works under load (429 retries succeed)
- [ ] Incremental sync detects additions, updates, and deletions
- [ ] Full crawl completes within acceptable time window
- [ ] Connection auto-recovery works after manual deletion
