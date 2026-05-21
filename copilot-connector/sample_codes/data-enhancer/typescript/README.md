# TypeScript Copilot data enhancer

`src\enhance_for_copilot.ts` is the TypeScript port of the data enhancer. It now supports the same unified workflow as the Python implementation for both **tabular** and **document-like** source data.

Supported inputs:

| Type | Extensions | Output item type |
|---|---|---|
| Delimited tabular data | `csv`, `tsv` | `record`, `grouped-record`, `dataset-guide` |
| Plain text | `txt`, `text` | `document-chunk` |
| Markdown | `md`, `markdown` | `document-chunk` |
| HTML | `html`, `htm` | `document-chunk` |
| JSON documents | `json` | `document-chunk` |
| JSON Lines | `jsonl` | `document-chunk` |

## Setup

```powershell
npm install
```

## Build

```powershell
npm run build
```

## Run

After building:

```powershell
node .\dist\enhance_for_copilot.js `
  --dataset .\my-corpus `
  --extensions csv,tsv,txt,md,html,json,jsonl `
  --output .\enhanced-output
```

Document-like only:

```powershell
node .\dist\enhance_for_copilot.js `
  --dataset .\my-docs `
  --extensions md,txt,html `
  --output .\enhanced-output
```

Mixed tabular and document-like:

```powershell
node .\dist\enhance_for_copilot.js `
  --dataset .\my-corpus `
  --extensions csv,tsv,md,json `
  --output .\enhanced-output
```

During development:

```powershell
npm run dev -- `
  --dataset .\my-corpus `
  --extensions csv,tsv,txt,md,html,json,jsonl `
  --output .\enhanced-output
```

For tabular datasets with custom entity/date columns or long-format grouping, pass the same JSON config structure used by the Python port:

```powershell
node .\dist\enhance_for_copilot.js `
  --dataset .\my-dataset `
  --config .\my-enhancer-config.json `
  --output .\enhanced-output
```

## Behavior summary

### Tabular files

- Preserves the existing row-centric enhancement flow
- Supports eval matching, focused output, and grouped long-indicator records
- Generates dataset guides and Graph-safe structured schema suggestions

### Document-like files

- Extracts lightweight metadata such as title, author, and date from each format's conventions
- Cleans whitespace and removes obvious HTML boilerplate
- Splits by heading/section structure first; then by size with ~200-character overlap at natural boundaries (paragraphs, sentences)
- Chunk size target: ~2,000 characters
- Emits `document-chunk` items with `documentId`, `contentType`, `sectionPath`, `chunkIndex`, `chunkCount`, `author`, and `datePublished`

Chunking strategy by format:

- **Markdown**: splits on `#` / `##` heading boundaries; section hierarchy preserved in `sectionPath`
- **HTML**: splits on detected heading elements; script and style blocks stripped before parsing
- **Text**: splits on paragraph boundaries (double newlines), then by character limit
- **JSON / JSONL**: splits on top-level key/section boundaries; each JSONL line is a separate section

## Outputs

- `enhanced-items.jsonl`
- `enhanced-records.csv`
- `schema-suggestion.json`
- `enhancement-report.json`
- `unmatched-eval-items.json`

## Eval interaction

Eval behavior is currently **tabular-only**:

- `--include-eval-prompts`
- `--include-eval-answers`
- `--focus-on-eval`

These flags do not change non-tabular document chunk generation.

## Schema behavior

The generated schema keeps the same Microsoft Graph connector guidance as the Python implementation:

- `baseType: microsoft.graph.externalItem`
- semantic labels for `title`, `url`, and `iconUrl`
- Graph-safe property names
- `sourceFieldMappings` for tabular columns
- no searchable+refinable conflicts

When document-like files are present, the schema adds these additional properties:

| Property | Type | Refinable | Aliases |
|---|---|---|---|
| `documentId` | String | — | `document`, `sourceDocument` |
| `contentType` | String | ✓ | `format`, `fileType`, `documentFormat`, `mimeType` |
| `sectionPath` | String | — | `section`, `heading`, `headingPath` |
| `chunkIndex` | Int64 | — | `chunk` |
| `chunkCount` | Int64 | — | `totalParts`, `totalSegments` |
| `author` | String | — | `creator`, `writer` |
| `datePublished` | String | — | `publishedDate`, `documentDate`, `created` |

These properties are omitted from the schema when only tabular files are produced.

Document chunk `contentType` values use MIME-style identifiers such as `text/plain`, `text/markdown`, `text/html`, `application/json`, and `application/jsonl`.

## Content extraction

Metadata extracted per format:

- **Text**: uses the first meaningful line as title; recognises `Author:`, `Date:`, and `Source:` header lines
- **Markdown**: parses YAML frontmatter (`title`, `author`, `date`) when present; falls back to the first `# Heading`; frontmatter stripped from the body
- **HTML**: extracts `<title>`, `<meta name="author">`, `<meta name="date">`, and the first `<h1>`; removes script/style blocks before extracting visible text
- **JSON**: extracts `title`/`name`, `author`, and `date` from well-known top-level keys; renders the structure as key-value lines; only top-level fields processed
- **JSONL**: each line is a separate section; filename stem used as document title

## Limitations

- No binary document parsing (`pdf`, `docx`, etc.)
- HTML boilerplate removal is heuristic (regex-based, no DOM parser); complex templates may retain nav or footer text
- Chunking is character-based with natural-boundary hints; token counts are not used
- JSON arrays at the top level are not recursively expanded; only top-level object structure is processed
- Eval matching, `--focus-on-eval`, and `--long-indicator-mode` are limited to tabular sources
- YAML frontmatter parsing handles simple `key: value` pairs only

## Tests

```powershell
npm test -- --runInBand
```

## Validation

```powershell
npm run build
npm test -- --runInBand
```
