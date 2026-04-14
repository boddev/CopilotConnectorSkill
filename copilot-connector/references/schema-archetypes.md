# Schema Archetypes

Pre-built schema templates for common enterprise data scenarios. Use these as starting points and customize to fit your data.

## Archetype 1: Knowledge Base / Wiki Articles

**Sources:** Confluence, SharePoint wikis, internal documentation, FAQs

```json
{
  "baseType": "microsoft.graph.externalItem",
  "properties": [
    {
      "name": "title",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["title"]
    },
    {
      "name": "articleUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["url"]
    },
    {
      "name": "author",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["createdBy"]
    },
    {
      "name": "lastEditor",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["lastModifiedBy"]
    },
    {
      "name": "lastModified",
      "type": "DateTime",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true,
      "labels": ["lastModifiedDateTime"]
    },
    {
      "name": "space",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true,
      "labels": ["containerName"]
    },
    {
      "name": "tags",
      "type": "StringCollection",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true,
      "isExactMatchRequired": true,
      "aliases": ["labels", "categories"]
    },
    {
      "name": "iconUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["iconUrl"]
    }
  ]
}
```

**Content strategy:** Use `html` type. Preserve headings, lists, and tables. Strip navigation chrome, sidebars, and boilerplate.

---

## Archetype 2: Tickets / Work Items

**Sources:** ServiceNow incidents, Jira issues, Azure DevOps work items, Zendesk tickets

```json
{
  "baseType": "microsoft.graph.externalItem",
  "properties": [
    {
      "name": "ticketId",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isExactMatchRequired": true,
      "aliases": ["ID"]
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
      "isRefinable": true,
      "aliases": ["state"]
    },
    {
      "name": "priority",
      "type": "Int64",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true
    },
    {
      "name": "assignedTo",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "aliases": ["assignee", "owner"]
    },
    {
      "name": "createdBy",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["createdBy"]
    },
    {
      "name": "createdDate",
      "type": "DateTime",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true,
      "labels": ["createdDateTime"]
    },
    {
      "name": "lastModifiedDate",
      "type": "DateTime",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true,
      "labels": ["lastModifiedDateTime"]
    },
    {
      "name": "tags",
      "type": "StringCollection",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true,
      "isExactMatchRequired": true,
      "aliases": ["labels", "categories"]
    },
    {
      "name": "itemUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["url"]
    },
    {
      "name": "iconUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["iconUrl"]
    }
  ]
}
```

**Content strategy:** Use `text` type. Concatenate description + root cause + resolution + recent comments. Prefix each section with a label.

---

## Archetype 3: CRM Records

**Sources:** Salesforce opportunities, Dynamics 365 leads, HubSpot contacts

```json
{
  "baseType": "microsoft.graph.externalItem",
  "properties": [
    {
      "name": "accountName",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["title"]
    },
    {
      "name": "contactEmail",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isExactMatchRequired": true
    },
    {
      "name": "dealStage",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true
    },
    {
      "name": "dealValue",
      "type": "Double",
      "isQueryable": true,
      "isRetrievable": true
    },
    {
      "name": "industry",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true
    },
    {
      "name": "lastActivity",
      "type": "DateTime",
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["lastModifiedDateTime"]
    },
    {
      "name": "recordUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["url"]
    },
    {
      "name": "iconUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["iconUrl"]
    }
  ]
}
```

**Content strategy:** Use `text`. Include recent activity notes, deal history, and key contact information in content.

---

## Archetype 4: HR / People Data

**Sources:** Employee profiles, skills directories, org chart data

> **Note:** If indexing employee profile data for people cards, use the [People connectors pattern](https://learn.microsoft.com/graph/connecting-external-content-experiences) instead. The schema below is for general HR data indexed as standard external items.

```json
{
  "baseType": "microsoft.graph.externalItem",
  "properties": [
    {
      "name": "employeeName",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["title"]
    },
    {
      "name": "department",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true,
      "labels": ["containerName"]
    },
    {
      "name": "jobTitle",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true
    },
    {
      "name": "skills",
      "type": "StringCollection",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true
    },
    {
      "name": "location",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true
    },
    {
      "name": "profileUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["url"]
    },
    {
      "name": "iconUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["iconUrl"]
    }
  ]
}
```

**Content strategy:** Use `text`. Include bio, skills summary, project history, and certifications.

---

## Archetype 5: Financial / Compliance Records

**Sources:** Audit reports, regulatory filings, policy documents, SOX controls

```json
{
  "baseType": "microsoft.graph.externalItem",
  "properties": [
    {
      "name": "documentTitle",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["title"]
    },
    {
      "name": "regulatoryBody",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true
    },
    {
      "name": "complianceStatus",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true
    },
    {
      "name": "effectiveDate",
      "type": "DateTime",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true,
      "labels": ["createdDateTime"]
    },
    {
      "name": "documentUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["url"]
    },
    {
      "name": "iconUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["iconUrl"]
    }
  ]
}
```

**Content strategy:** Use `text` (required for compliance). Include full document text. Chunk long regulatory documents.

> **Compliance note:** If `enabledContentExperience` is set to `compliance`, you must use `text` content type.

---

## Archetype 6: Product Catalogs

**Sources:** SKUs, product specifications, pricing sheets

```json
{
  "baseType": "microsoft.graph.externalItem",
  "properties": [
    {
      "name": "productName",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["title"]
    },
    {
      "name": "sku",
      "type": "String",
      "isQueryable": true,
      "isExactMatchRequired": true
    },
    {
      "name": "category",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true
    },
    {
      "name": "price",
      "type": "Double",
      "isQueryable": true,
      "isRetrievable": true
    },
    {
      "name": "availability",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true
    },
    {
      "name": "productUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["url"]
    },
    {
      "name": "iconUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["iconUrl"]
    }
  ]
}
```

**Content strategy:** Use `text` or `html`. Include full product description, specifications table, and compatibility notes.

---

## Archetype 7: File Repository (Parsed Content)

**Sources:** Network file shares, S3 buckets, document management systems

```json
{
  "baseType": "microsoft.graph.externalItem",
  "properties": [
    {
      "name": "title",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["title"]
    },
    {
      "name": "fileName",
      "type": "String",
      "isSearchable": true,
      "isRetrievable": true,
      "labels": ["fileName"]
    },
    {
      "name": "fileExtension",
      "type": "String",
      "isRetrievable": true,
      "isRefinable": true,
      "labels": ["fileExtension"]
    },
    {
      "name": "author",
      "type": "String",
      "isSearchable": true,
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["authors"]
    },
    {
      "name": "lastModified",
      "type": "DateTime",
      "isQueryable": true,
      "isRetrievable": true,
      "isRefinable": true,
      "labels": ["lastModifiedDateTime"]
    },
    {
      "name": "folderPath",
      "type": "String",
      "isQueryable": true,
      "isRetrievable": true,
      "labels": ["containerName"]
    },
    {
      "name": "fileUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["url"]
    },
    {
      "name": "iconUrl",
      "type": "String",
      "isRetrievable": true,
      "labels": ["iconUrl"]
    }
  ]
}
```

**Content strategy:** Parse binary files (PDF, DOCX, PPTX) to text before ingestion. Use libraries like Apache Tika, iTextSharp, or Azure AI Document Intelligence. Apply OCR for scanned documents. Use `html` if parsed output preserves structure.
