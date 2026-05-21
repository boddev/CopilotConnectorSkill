# Data Enhancer Integration for Copilot Connectors

Use these scripts when creating a custom Microsoft 365 Copilot Connector. They convert raw crawled source data into Copilot-friendly external item payloads before the connector writes items to Microsoft Graph.

## Required integration pattern

Every connector crawl that can create or update external items should use this sequence:

```text
Source system crawl -> staging dataset -> data enhancer -> enhanced-items.jsonl -> ACL application -> Graph externalItem upsert
```

The connector should never silently bypass the enhancer. If enhancement fails, fail the crawl, log/surface the error, and do not upsert raw source items.

## Included implementations

| Runtime | Files | Use when |
|---------|-------|----------|
| Python | `python\enhance_for_copilot.py`, `python\nontabular.py` | The connector or crawl worker is Python-based, or you want a no-non-stdlib CLI. |
| TypeScript | `typescript\src\enhance_for_copilot.ts`, `typescript\src\nontabular.ts` | The connector or crawl worker is Node.js/TypeScript-based. |

## Runtime contract

1. Crawl full or incremental source changes into a staging directory.
2. Run the enhancer against that staging directory.
3. Use `schema-suggestion.json` as the starting point for the connector schema.
4. Read `enhanced-items.jsonl` and map each line to a Graph `externalItem`.
5. Apply final source-system ACLs in the connector pipeline unless the enhancer output already contains authoritative ACLs.
6. Persist crawl checkpoints only after enhanced items are successfully ingested.

## Outputs

| Output | Purpose |
|--------|---------|
| `enhanced-items.jsonl` | Graph-connector-shaped items with `properties` and `content`. |
| `enhanced-records.csv` | Inspection-friendly copy of generated content and key properties. |
| `schema-suggestion.json` | Suggested Graph connector schema with safe property names, labels, aliases, and source mappings. |
| `enhancement-report.json` | Processing counts, skipped files, stats, and coverage information. |

## Python usage

```powershell
python .\python\enhance_for_copilot.py `
  --dataset .\staging-crawl `
  --extensions csv,tsv,txt,md,html,json,jsonl `
  --output .\enhanced-output
```

## TypeScript usage

```powershell
Set-Location .\typescript
npm install
npm run build
node .\dist\enhance_for_copilot.js `
  --dataset ..\staging-crawl `
  --extensions csv,tsv,txt,md,html,json,jsonl `
  --output ..\enhanced-output
```

## Connector mapping notes

- Use `content.value` as the Graph external item `content.value`.
- Do not register `content` as a schema property.
- Keep `title`, `url`, and `iconUrl` retrievable and semantically labeled.
- Merge source-specific ACLs after enhancement so security trimming matches the source system.
- For incremental crawls, stage only new/changed source items, enhance them, ingest the enhanced output, and separately delete Graph items whose source items were deleted.
