# Copilot data enhancer

`enhance_for_copilot.py` converts source datasets into richer Microsoft Graph connector items that are easier for Microsoft 365 Copilot to retrieve.

The enhancer now supports a **single workflow for both tabular and document-like content**:

- **Tabular files** (`.csv`, `.tsv`) keep the existing row-centric flow, dataset guides, eval matching, and grouped long-indicator behavior.
- **Document-like files** (`.txt`, `.md`, `.html`, `.json`, `.jsonl`) are extracted, cleaned, chunked by structure first, then emitted as `document-chunk` items with section and chunk metadata.

The tool stays data-generic by default:

- It auto-detects common CSV/TSV delimiters for tabular files.
- It uses generic key-field heuristics when no config is supplied.
- It supports optional JSON config for **tabular** field aliases, priority fields, key-field candidates, and long-format grouping columns.
- It keeps Graph-safe schema property names, `baseType: microsoft.graph.externalItem`, semantic labels for `title` / `url` / `iconUrl`, `sourceFieldMappings`, and no searchable+refinable conflicts.

## Setup

Requires Python 3.10+.

```powershell
pip install -e ".[dev]"
```

Or run the script directly (no non-stdlib dependencies):

```powershell
python .\enhance_for_copilot.py --help
```

## Supported input types

| Type | Extensions | Output item type |
|---|---|---|
| Delimited tabular data | `csv`, `tsv` | `record`, `grouped-record`, `dataset-guide` |
| Plain text | `txt`, `text` | `document-chunk` |
| Markdown | `md`, `markdown` | `document-chunk` |
| HTML | `html`, `htm` | `document-chunk` |
| JSON documents | `json` | `document-chunk` |
| JSON Lines | `jsonl` | `document-chunk` |

## Run on any dataset

### Tabular only

```powershell
python .\enhance_for_copilot.py `
  --dataset .\my-dataset `
  --extensions csv,tsv `
  --output .\enhanced-output
```

### Document-like only

```powershell
python .\enhance_for_copilot.py `
  --dataset .\my-docs `
  --extensions txt,md,html,json,jsonl `
  --output .\enhanced-output
```

### Mixed corpus

```powershell
python .\enhance_for_copilot.py `
  --dataset .\my-corpus `
  --extensions csv,tsv,txt,md,html,json,jsonl `
  --output .\enhanced-output
```

If your **tabular** dataset uses custom entity/date column names or a long-format layout that should be grouped, pass a config file:

```json
{
  "priorityFields": ["product", "quarter", "metric_name", "value"],
  "keyFieldCandidates": {
    "entity": ["product"],
    "year": ["quarter"],
    "iso": []
  },
  "longIndicatorColumns": {
    "idColumn": "metric_code",
    "nameColumn": "metric_name",
    "entityColumn": "product",
    "yearColumn": "quarter",
    "valueColumn": "value",
    "isoColumn": "",
    "groupLabel": "grouped metrics"
  }
}
```

```powershell
python .\enhance_for_copilot.py `
  --dataset .\my-dataset `
  --config .\my-enhancer-config.json `
  --output .\enhanced-output
```

## Run on the sample tabular dataset

```powershell
python .\enhance_for_copilot.py `
  --dataset .\environment-datasets `
  --eval .\eval-output\environment-datasets-eval.evalgen.json `
  --config .\examples\environment-config.json `
  --output .\enhanced-output
```

## Outputs

- `enhanced-items.jsonl` — Graph-connector-shaped items with `properties` and `content`
- `enhanced-records.csv` — inspection-friendly copy of generated content and key properties
- `schema-suggestion.json` — suggested connector schema with Graph-safe properties, labels, source mappings, and production notes
- `enhancement-report.json` — counts, skipped files, tabular file stats, non-tabular file stats, eval coverage, and assertion gaps
- `unmatched-eval-items.json` — eval prompts that did not match generated tabular records

When non-tabular files are processed, `schema-suggestion.json` includes these additional properties:

| Property | Type | Searchable | Refinable | Aliases |
|---|---|---|---|---|
| `documentId` | String | — | — | `document`, `sourceDocument` |
| `contentType` | String | — | ✓ | `format`, `fileType`, `documentFormat`, `mimeType` |
| `sectionPath` | String | — | — | `section`, `heading`, `headingPath` |
| `chunkIndex` | Int64 | — | — | `chunk` |
| `chunkCount` | Int64 | — | — | `totalParts`, `totalSegments` |
| `author` | String | — | — | `creator`, `writer` |
| `datePublished` | String | — | — | `publishedDate`, `documentDate`, `created` |

These properties are omitted from the schema when only tabular files are produced.

Document chunk `contentType` values use MIME-style identifiers such as `text/plain`, `text/markdown`, `text/html`, `application/json`, and `application/jsonl`.

## Document extraction and chunking behavior

Document-like files follow a conservative generic flow:

1. **Extract** content and lightweight metadata from the source file
2. **Clean** whitespace and strip obvious HTML boilerplate such as navigation/footer/script content
3. **Preserve structure** by splitting on headings/sections first when available
4. **Chunk by size** only when a section still exceeds ~2,000 characters, with ~200-character overlap at natural text boundaries (paragraphs, sentences)
5. **Emit context** in both properties and `content.value` so each chunk remains understandable in isolation

Chunking strategy by format:

- **Markdown**: splits on `#` / `##` heading boundaries first; section hierarchy is preserved in `sectionPath`
- **HTML**: splits on detected heading elements (`h1`–`h6`); script and style blocks are stripped before parsing
- **Text**: splits on paragraph boundaries (double newlines), then by character limit
- **JSON / JSONL**: splits on top-level key/section boundaries; each JSONL line is treated as a separate section

Notes by format:

- **Text**: uses the first meaningful line as a title when possible; recognises `Author:`, `Date:`, and `Source:` header lines
- **Markdown**: parses YAML frontmatter (`title`, `author`, `date`) when present; falls back to the first `# Heading`; frontmatter is stripped from the body
- **HTML**: extracts `<title>`, `<meta name="author">`, `<meta name="date">`, and the first `<h1>`; removes `<script>`, `<style>`, and common boilerplate containers before extracting visible text
- **JSON**: extracts `title`/`name`, `author`, and `date` from well-known top-level keys; renders the remaining structure as readable key-value lines; only top-level fields are processed
- **JSONL**: treats each line as a separate section; uses the filename stem as the document title

## Eval prompt usage

By default, eval sets help match and focus **tabular** records, but the enhancer does **not** inject prompt or expected-answer text into content.

For experiments where you intentionally want prompt examples in indexed tabular content:

```powershell
python .\enhance_for_copilot.py `
  --dataset .\environment-datasets `
  --eval .\eval-output\environment-datasets-eval.evalgen.json `
  --output .\enhanced-output-with-prompts `
  --include-eval-prompts
```

Important:

- Eval matching is currently **tabular-only**
- Non-tabular files do **not** participate in eval matching or prompt injection
- `--focus-on-eval` only filters tabular output
- Only use `--include-eval-answers` for controlled diagnostics, not holdout evaluation or production content

## Important options

| Option | Purpose |
|---|---|
| `--config path\to\config.json` | Supplies dataset-specific field labels, key-field candidates, priority fields, and long-format grouping columns for **tabular** workflows. |
| `--extensions csv,tsv,txt,md,html,json,jsonl` | Selects which file types to process. |
| `--encoding latin-1` | Input encoding for source files and CSV eval files. Default: auto-detect (UTF-8 BOM, then Windows-1252). |
| `--url-prefix https://example.com/data` | HTTPS base URL for generated item URLs. Without this, URLs use `file:///` paths. Grouped-record URLs are generated as `{prefix}/_grouped/{entity}/{year}`. |
| `--long-indicator-mode grouped` | Default. Pivots long-format tabular rows into one grouped record per entity/time key. Requires explicit `longIndicatorColumns`. |
| `--long-indicator-mode row` | Keeps one item per source tabular row. |
| `--long-indicator-mode both` | Emits both grouped and source-row items. |
| `--focus-on-eval` | Emits only eval-matched **tabular** records plus dataset guides. Non-tabular files are unaffected by eval matching. |
| `--max-records-per-file N` | Smoke-test limit on source rows or generated document chunks per file. |
| `--acl-mode everyone` | Adds placeholder ACLs. Default is `none` so your connector pipeline can apply source permissions. |

## Connector ingestion notes

Use `content.value` as the external item `content` property; do **not** register `content` as a schema property.

The generated schema keeps the existing Graph/Copilot connector best practices:

- `baseType: microsoft.graph.externalItem`
- semantic labels for `title`, `url`, and `iconUrl`
- Graph-safe property names
- `sourceFieldMappings` for tabular source fields
- no property is both searchable and refinable
- refinable properties intentionally limited to a small stable set

Production guidance:

- Populate `url` and `iconUrl` with valid absolute URLs before ingestion
- Keep ACL assignment in the connector pipeline unless the dataset is intentionally tenant-wide
- Register the schema asynchronously and poll until registration completes
- Keep exact source values as properties when verbatim answers matter
- Precompute separate summary items for aggregate questions instead of relying on Copilot to sum across many records at query time

## Limitations

- No binary document parsing (`.pdf`, `.docx`, etc.) is included
- HTML boilerplate removal is heuristic (stdlib `html.parser`, no DOM tree); complex templates may retain nav or footer text
- Chunking is character-based with natural-boundary hints; token counts are not used (no tokenizer dependency)
- JSON arrays at the top level are not recursively expanded; only top-level object structure is processed
- Tabular config (field aliases, key-field candidates, long-indicator columns) does not affect document extraction
- Eval matching, `--focus-on-eval`, and `--long-indicator-mode` are limited to tabular sources
- YAML frontmatter parsing handles simple `key: value` pairs only; nested YAML structures are not supported

## Running tests

```powershell
python -m pytest tests/ -v
```

## Config file reference (tabular workflows)

The optional `--config` JSON file adapts the **tabular** flow to arbitrary schemas without modifying the script.

| Key | Type | Purpose |
|---|---|---|
| `description` | string | Human-readable description of the config (ignored by the tool). |
| `fieldAliases` | object | Maps column names to human-readable labels used in generated content. |
| `priorityFields` | array of strings | Column names that appear first in generated records regardless of eval coverage. |
| `keyFieldCandidates` | object | Maps logical keys (`entity`, `year`, `iso`) to arrays of candidate column names. **Replaces** the default list for that key. |
| `longIndicatorColumns` | object | Describes the columns that identify a long-format indicator file. Required: `idColumn`, `nameColumn`, `entityColumn`, `yearColumn`, `valueColumn`. Optional: `isoColumn`, `groupLabel`. |

### keyFieldCandidates merge semantics

When you set `keyFieldCandidates.entity = ["station"]`, the tool uses only `["station"]` for entity detection — it does **not** append to the built-in defaults. To keep a default and add more candidates, copy the relevant defaults into your array.

### Eval set formats

JSON eval sets (`--eval path.json`) support supporting facts, assertions, categories, and difficulty. CSV eval sets support `prompt`, `expected_answer`, and `source_location` only.
