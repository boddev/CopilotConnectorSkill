# Schema Design Reference

Complete reference for designing Copilot Connector schemas.

## Property Naming Rules

- Use **clear, descriptive names** that convey semantic meaning
- Avoid abbreviations, acronyms, or cryptic identifiers
- Add **property descriptions** to help Copilot interpret properties

| ✅ Do | ❌ Don't |
|-------|---------|
| `parentOrganizationName` | `orgName` |
| `incidentRootCause` | `dataBlob` |
| `qualifiedSalesLead` | `ftxInvIsLead` |
| `departmentName` | `brOrgName` |

## All Property Types

| Type | Use For | Example Properties |
|------|---------|-------------------|
| `String` | Free-text values, identifiers, names | `title`, `description`, `assignee` |
| `Int64` | Whole numbers, counts, priorities | `priority`, `itemCount`, `severity` |
| `Double` | Decimal numbers, scores, percentages | `score`, `price`, `completionRate` |
| `DateTime` | Timestamps | `createdDate`, `lastModified`, `dueDate` |
| `Boolean` | True/false flags | `isResolved`, `isActive`, `isPublic` |
| `StringCollection` | Multi-value text (tags, categories) | `tags`, `categories`, `skills` |
| `Int64Collection` | Multi-value integers | `relatedItemIds`, `scores` |
| `DoubleCollection` | Multi-value decimals | `measurements`, `ratings` |
| `DateTimeCollection` | Multi-value timestamps | `milestones`, `reviewDates` |

> The Graph API also supports `principal` and `principalCollection` types for representing Microsoft Entra ID users and groups directly.

## Schema Limits

| Limit | Value |
|-------|-------|
| Maximum properties per schema | **128** |
| Maximum external groups per tenant | 100,000 |
| Maximum external groups per user (for search) | 10,000 |

## Attribute Configuration Guide

### Searchable

The property value is added to the full-text index. Copilot matches user queries against searchable properties.

- ✅ Mark: `title`, `description`, `tags`, `createdBy`, `assignedTo`
- ❌ Don't mark: Large binary fields, refinable fields (mutually exclusive)
- Only mark properties essential for search relevance

### Queryable

Enables KQL (Keyword Query Language) filtering. Supports prefix matching with wildcard `*` (suffix matching not supported).

- ✅ Mark: `status`, `priority`, `assignedTo`, `category`, `ticketId`
- ❌ Don't mark: Large text fields like `description`
- Combine with `retrievable: true` so filtered properties appear in results

### Retrievable

The property value is returned in search results and available for display templates.

- ✅ Mark: `title`, `summary`, `status`, `assignedTo`, `createdDateTime`
- ❌ Don't over-mark: Too many or large retrievable properties increase search latency
- **Required** for properties mapped to semantic labels

### Refinable

Appears as a filter control (dropdown, checkbox) in Microsoft Search UI.

- ✅ Mark: `tags`, `status`, `priority`, `category`, `type`
- ⚠️ **Mutually exclusive with searchable**
- ⚠️ Only `String`, numeric, and `DateTime` types can be refinable
- ⚠️ **Cannot be added via schema update** — must be in initial schema
- ⚠️ Too many refinable properties impact performance

### ExactMatchRequired

The full string value is indexed without tokenization.

- ✅ Use for: GUIDs, ticket IDs, SKUs, part numbers
- ⚠️ Can only be applied to properties that are **not searchable**

## Attribute Compatibility Matrix

| Combination | Allowed? |
|-------------|----------|
| Searchable + Queryable | ✅ Yes |
| Searchable + Retrievable | ✅ Yes |
| Searchable + Refinable | ❌ No — mutually exclusive |
| Searchable + ExactMatch | ❌ No — ExactMatch requires non-searchable |
| Queryable + Refinable | ✅ Yes |
| Queryable + Retrievable | ✅ Yes (recommended combination) |
| Refinable + Retrievable | ✅ Yes |

## Complete Semantic Labels Reference

### Core Labels

| Label | Description | Maps To Properties Like |
|-------|-------------|------------------------|
| `title` | Main name/heading of the item | `documentTitle`, `ticketSubject`, `reportName` |
| `url` | Direct link to open the item in source | `documentLink`, `ticketUrl`, `recordUrl` |
| `iconUrl` | URL of an icon/thumbnail | `thumbnailUrl`, `logo`, `previewImage` |
| `createdBy` | User who created the item | `authorEmail`, `submittedBy`, `createdByUser` |
| `lastModifiedBy` | User who last edited | `editorEmail`, `updatedBy`, `lastChangedBy` |
| `authors` | All collaborators | `authorName`, `writer`, `contributors` |
| `createdDateTime` | When the item was created | `createdOn`, `submissionDate`, `entryDate` |
| `lastModifiedDateTime` | When last modified | `lastUpdated`, `modifiedOn`, `changeDate` |
| `fileName` | Name of the file | `documentName`, `attachmentName` |
| `fileExtension` | File extension | `documentType`, `format` |
| `containerName` | Parent container name | `projectName`, `folderName`, `groupName` |
| `containerUrl` | URL of the parent container | `projectUrl`, `folderLink`, `groupPage` |

### Extended Labels

Additional labels beyond the core set (check current docs for availability):

`assignedTo`, `dueDate`, `closedDate`, `closedBy`, `reportedBy`, `sprintName`, `severity`, `state`, `priority`, `secondaryId`, `itemParentId`, `parentUrl`, `tags`, `itemType`, `itemPath`, `numReactions`

> Always verify current label availability: `microsoft_docs_fetch(url="https://learn.microsoft.com/graph/connecting-external-content-manage-schema#semantic-labels")`

### Label Impact on Discovery (Priority Order)

1. `title` — **Most important.** Required for result cluster experience.
2. `lastModifiedDateTime`
3. `lastModifiedBy`
4. `url`
5. `fileName`
6. `fileExtension`

### Label Rules

- Properties assigned to labels **must be retrievable**
- Each label maps to **exactly one property**
- Property **data type must match** the label's expected type
- Assigning a label to a property with large content **increases search latency**

## Aliases

Friendly names for properties used in search queries and refinable filters.

| Property | Suggested Aliases |
|----------|-------------------|
| `createdBy` | `author`, `owner`, `submittedBy` |
| `title` | `subject`, `heading` |
| `tags` | `labels`, `categories` |
| `fileName` | `documentName`, `file` |
| `summary` | `description`, `abstract` |

**Best practices:**
- Use aliases for common synonyms and domain-specific terms
- Keep aliases short and intuitive
- System-autocreated aliases for refinable properties cannot be removed

## Rank Hints

For searchable properties **not** mapped to semantic labels, configure rank hints in the M365 Admin Center:

1. Go to **Search & intelligence** > **Customization** > **Relevance tuning**
2. Set importance from `default` to `veryHigh`

Rank hints prioritize certain properties in search results alongside other item attributes.

## Schema Update Rules

| Operation | Supported? | Reingestion? |
|-----------|-----------|--------------|
| Add a new property | ✅ Yes | Recommended |
| Add/remove search capability | ✅ Yes | **Required** |
| Add refinable attribute | ❌ Not via update | Requires new connection |
| Add/remove alias | ✅ Yes | Not needed |
| Add/remove semantic label | ✅ Yes | Not needed |

> After any schema update, reindex items to ensure consistent behavior.
