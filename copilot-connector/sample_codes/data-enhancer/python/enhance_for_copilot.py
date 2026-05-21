#!/usr/bin/env python3
"""Generate Microsoft 365 Copilot-friendly records from tabular datasets.

The tool converts sparse tabular rows into self-contained semantic records for
Microsoft Graph connector ingestion. Evaluation sets can be used to validate
coverage and, optionally, to add prompt examples to matching records.

The enhancer is **data-generic**: it works with delimited tabular datasets.
Domain-specific field labels, priority fields, and long-indicator column
mappings can be supplied via a JSON config file (--config). Without a config,
the tool applies generic heuristics to detect entity/time columns and
auto-generates human-readable labels from column names.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import html.parser
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote as urlquote


EMPTY_VALUES = {"", "null", "none", "nan", "n/a", "na"}
DELIMITER_CANDIDATES = ",\t;|"
TABULAR_EXTENSIONS: frozenset[str] = frozenset({"csv", "tsv"})
NON_TABULAR_EXTENSIONS: frozenset[str] = frozenset({"txt", "md", "markdown", "html", "htm", "json", "jsonl"})
NONTABULAR_EXTENSIONS: frozenset[str] = NON_TABULAR_EXTENSIONS
CONTENT_TYPE_MAP: dict[str, str] = {
    "txt": "text",
    "md": "markdown",
    "markdown": "markdown",
    "html": "html",
    "htm": "html",
    "json": "json",
    "jsonl": "jsonl",
}
CONTENT_TYPE_ALIASES: dict[str, str] = {
    "text/plain": "text",
    "text/markdown": "markdown",
    "text/html": "html",
    "application/json": "json",
    "application/jsonl": "jsonl",
}
CONTENT_TYPE_MIME_MAP: dict[str, str] = {
    "text": "text/plain",
    "markdown": "text/markdown",
    "html": "text/html",
    "json": "application/json",
    "jsonl": "application/jsonl",
}
_METADATA_KEY_RE = re.compile(r"[^a-z0-9]+")
_TEXT_METADATA_RE = re.compile(r"^(author|byline|date|published|source|url)\s*:\s*(.+)$", re.IGNORECASE)
_MARKDOWN_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n(?:---|\.\.\.)\s*\n", re.DOTALL)
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_DATE_FIELD_NAMES = ("date", "created_at", "createdAt", "publishDate", "published_at", "publishedAt", "timestamp")
_AUTHOR_FIELD_NAMES = ("author", "authors", "creator", "createdBy", "created_by", "byline")
_TITLE_FIELD_NAMES = ("title", "name")
_URL_FIELD_NAMES = ("url", "sourceUrl", "source_url", "link", "canonicalUrl", "canonical_url")


def document_content_type_value(content_type: str) -> str:
    normalized_type = CONTENT_TYPE_ALIASES.get(content_type, content_type)
    return CONTENT_TYPE_MIME_MAP.get(normalized_type, normalized_type)

# Field names whose integer values should NOT receive thousands-separator decoration.
# These represent time periods (year, quarter, etc.) or identifier/code columns.
_PRESERVE_NUMERIC_FIELD_NAMES: frozenset[str] = frozenset({
    "year", "date", "month", "quarter", "period",
    "timestamp", "time", "fiscal_year", "week",
})
# Field-name suffixes that indicate identifier/code columns.
_PRESERVE_NUMERIC_SUFFIXES: tuple[str, ...] = ("id", "code", "key", "no", "num", "iso")

# Generic key-field candidates used when no config is supplied.
DEFAULT_KEY_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "entity": ("country", "countryName", "country_name", "name", "entity", "region",
               "company", "organization", "station", "city", "state", "location"),
    "year": ("year", "date", "time_period", "period", "quarter", "month"),
    "iso": ("iso_code", "countryiso3code", "countryIso3Code", "country_id", "countryId", "id", "code"),
}

# Default long-indicator column mapping (World Bank style). Overridden by config.
DEFAULT_LONG_INDICATOR_COLUMNS: dict[str, str] = {
    "idColumn": "indicatorId",
    "nameColumn": "indicatorName",
    "entityColumn": "countryName",
    "yearColumn": "date",
    "valueColumn": "value",
    "isoColumn": "countryiso3code",
    "groupLabel": "long-format indicators",
}

VALID_CONFIG_KEYS = {
    "description", "fieldAliases", "priorityFields",
    "keyFieldCandidates", "longIndicatorColumns",
}
VALID_LONG_INDICATOR_KEYS = {
    "idColumn", "nameColumn", "entityColumn", "yearColumn",
    "valueColumn", "isoColumn", "groupLabel",
}


@dataclass(frozen=True)
class EnhancerConfig:
    """Immutable resolved configuration for the enhancer."""
    field_aliases: dict[str, str]
    priority_fields: list[str]
    key_field_candidates: dict[str, tuple[str, ...]]
    long_indicator_columns: dict[str, str]
    # True only when the user explicitly supplied longIndicatorColumns in a config
    # file. Long-format grouping is disabled by default so the tool behaves
    # generically on arbitrary datasets.
    has_explicit_long_config: bool = False

    @staticmethod
    def load(config_path: Path | None) -> "EnhancerConfig":
        base_aliases: dict[str, str] = {}
        base_priority: list[str] = []
        base_keys = {k: v for k, v in DEFAULT_KEY_FIELD_CANDIDATES.items()}
        base_long = dict(DEFAULT_LONG_INDICATOR_COLUMNS)

        if config_path is None:
            return EnhancerConfig(
                field_aliases=base_aliases,
                priority_fields=base_priority,
                key_field_candidates={k: tuple(v) for k, v in base_keys.items()},
                long_indicator_columns=base_long,
            )

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in config file {config_path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError(f"Config file must be a JSON object, got {type(raw).__name__}")

        unknown_keys = set(raw.keys()) - VALID_CONFIG_KEYS
        if unknown_keys:
            raise ValueError(f"Unknown config keys: {sorted(unknown_keys)}")

        if "fieldAliases" in raw:
            if not isinstance(raw["fieldAliases"], dict):
                raise ValueError("fieldAliases must be a JSON object mapping field names to labels")
            for alias_key, alias_val in raw["fieldAliases"].items():
                if not isinstance(alias_val, str):
                    raise ValueError(
                        f"fieldAliases.{alias_key} must be a string label, got {type(alias_val).__name__}"
                    )
            base_aliases.update(raw["fieldAliases"])

        if "priorityFields" in raw:
            if not isinstance(raw["priorityFields"], list):
                raise ValueError("priorityFields must be a JSON array of field names")
            for i, item in enumerate(raw["priorityFields"]):
                if not isinstance(item, str):
                    raise ValueError(
                        f"priorityFields[{i}] must be a string field name, got {type(item).__name__}"
                    )
            base_priority = raw["priorityFields"]

        if "keyFieldCandidates" in raw:
            if not isinstance(raw["keyFieldCandidates"], dict):
                raise ValueError("keyFieldCandidates must be a JSON object")
            for key, candidates in raw["keyFieldCandidates"].items():
                if not isinstance(candidates, list):
                    raise ValueError(f"keyFieldCandidates.{key} must be an array")
                for i, candidate in enumerate(candidates):
                    if not isinstance(candidate, str):
                        raise ValueError(
                            f"keyFieldCandidates.{key}[{i}] must be a string, got {type(candidate).__name__}"
                        )
                base_keys[key] = candidates

        if "longIndicatorColumns" in raw:
            if not isinstance(raw["longIndicatorColumns"], dict):
                raise ValueError("longIndicatorColumns must be a JSON object")
            unknown_li = set(raw["longIndicatorColumns"].keys()) - VALID_LONG_INDICATOR_KEYS
            if unknown_li:
                raise ValueError(f"Unknown longIndicatorColumns keys: {sorted(unknown_li)}")
            for li_key, li_val in raw["longIndicatorColumns"].items():
                if not isinstance(li_val, str):
                    raise ValueError(
                        f"longIndicatorColumns.{li_key} must be a string, got {type(li_val).__name__}"
                    )
            base_long.update(raw["longIndicatorColumns"])
            required_li = {"idColumn", "nameColumn", "entityColumn", "yearColumn", "valueColumn"}
            for req_key in required_li:
                if not base_long.get(req_key):
                    raise ValueError(
                        f"longIndicatorColumns.{req_key} must be a non-empty string after merging defaults"
                    )
            has_explicit_long_config = True
        else:
            has_explicit_long_config = False

        return EnhancerConfig(
            field_aliases=base_aliases,
            priority_fields=base_priority,
            key_field_candidates={k: tuple(v) for k, v in base_keys.items()},
            long_indicator_columns=base_long,
            has_explicit_long_config=has_explicit_long_config,
        )


@dataclass
class EvalItem:
    id: str
    prompt: str
    expected_answer: str = ""
    supporting_facts: dict[str, str] = field(default_factory=dict)
    assertions: list[str] = field(default_factory=list)
    category: str = ""
    difficulty: str = ""
    referenced_rows: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class FileStats:
    relative_path: str
    header: list[str]
    row_count: int = 0
    non_empty_counts: Counter[str] = field(default_factory=Counter)
    entity_examples: Counter[str] = field(default_factory=Counter)
    year_values: set[str] = field(default_factory=set)
    skipped_reason: str | None = None


@dataclass
class EvalCoverage:
    matched_items: set[str] = field(default_factory=set)
    matched_records: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    assertions_found: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


@dataclass
class DocumentInfo:
    title: str
    author: str
    date: str
    content_type: str
    source_path: str
    relative_path: str
    body: str
    url: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class DocumentChunk:
    section_path: str
    heading: str
    chunk_index: int
    chunk_count: int
    text: str
    item_id: str


class _HTMLDocumentParser(html.parser.HTMLParser):
    _BLOCK_TAGS = frozenset(
        {
            "article",
            "aside",
            "blockquote",
            "br",
            "div",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "main",
            "p",
            "pre",
            "section",
            "tr",
            "ul",
            "ol",
        }
    )
    _SKIP_TAGS = frozenset({"footer", "form", "nav", "noscript", "script", "style", "svg", "template"})

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._current_heading_level = 0
        self._current_heading_parts: list[str] = []
        self.title = ""
        self.first_h1 = ""
        self.author = ""
        self.date = ""
        self.url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attrs_map = {name.lower(): (value or "") for name, value in attrs}
        if tag_lower in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag_lower == "title":
            self._in_title = True
            return
        if tag_lower == "meta":
            key = _normalize_metadata_key(attrs_map.get("name") or attrs_map.get("property", ""))
            value = attrs_map.get("content", "").strip()
            if value:
                if key in {"author", "articleauthor"} and not self.author:
                    self.author = value
                elif key in {"date", "articlepublishedtime", "publishedtime"} and not self.date:
                    self.date = value
                elif key in {"ogurl", "canonicalurl"} and not self.url:
                    self.url = value
            return
        if tag_lower == "link":
            rel_values = {part.strip().lower() for part in attrs_map.get("rel", "").split()}
            href = attrs_map.get("href", "").strip()
            if "canonical" in rel_values and href and not self.url:
                self.url = href
            return
        if tag_lower == "time":
            datetime_value = attrs_map.get("datetime", "").strip()
            if datetime_value and not self.date:
                self.date = datetime_value
        if tag_lower == "li":
            self._parts.append("\n- ")
        elif tag_lower in self._BLOCK_TAGS:
            self._parts.append("\n")
        heading_match = re.fullmatch(r"h([1-6])", tag_lower)
        if heading_match:
            self._current_heading_level = int(heading_match.group(1))
            self._current_heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag_lower == "title":
            self._in_title = False
            self.title = clean_content("".join(self._title_parts))
            return
        if re.fullmatch(r"h[1-6]", tag_lower) and self._current_heading_level:
            heading_text = clean_content("".join(self._current_heading_parts))
            if heading_text:
                if self._current_heading_level == 1 and not self.first_h1:
                    self.first_h1 = heading_text
                self._parts.append(f"\n{'#' * self._current_heading_level} {heading_text}\n")
            self._current_heading_level = 0
            self._current_heading_parts = []
            return
        if tag_lower in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._current_heading_level:
            self._current_heading_parts.append(data)
            return
        self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&#{name};"))

    @property
    def text(self) -> str:
        return "".join(self._parts)


def _normalize_metadata_key(value: str) -> str:
    return _METADATA_KEY_RE.sub("", value.casefold())


def _normalize_relative_path(relative_path: str) -> str:
    return relative_path.replace("/", "\\")


def _read_text_file(path: Path, encoding: str | None = None) -> str:
    if encoding is not None:
        return path.read_text(encoding=encoding)
    for candidate in ("utf-8-sig", "cp1252"):
        try:
            return path.read_text(encoding=candidate)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _normalize_whitespace_char(char: str) -> str:
    if char in "\r\n":
        return "\n"
    if char == "\t":
        return " "
    if unicodedata.category(char) == "Zs" or char in {"\u200b", "\ufeff"}:
        return " "
    return char


def clean_content(text: str) -> str:
    normalized_chars = "".join(_normalize_whitespace_char(char) for char in text)
    normalized_text = normalized_chars.replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines = [re.sub(r" +", " ", line).strip() for line in normalized_text.split("\n")]
    joined = "\n".join(cleaned_lines)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def _document_url(relative_path: str, url_prefix: str, override_url: str = "") -> str:
    if override_url:
        return override_url
    if url_prefix:
        prefix = url_prefix.rstrip("/")
        path = relative_path.replace("\\", "/").lstrip("/")
        return f"{prefix}/{path}"
    return f"file:///{relative_path.replace(chr(92), '/')}"


def _document_title_from_first_line(text: str, fallback: str) -> str:
    for line in text.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate if len(candidate) <= 120 else fallback
    return fallback


def _document_metadata_from_prefixed_lines(text: str) -> tuple[str, str, str]:
    author = ""
    date = ""
    source_url = ""
    for line in text.splitlines()[:12]:
        match = _TEXT_METADATA_RE.match(line.strip())
        if not match:
            continue
        key = _normalize_metadata_key(match.group(1))
        value = match.group(2).strip()
        if key in {"author", "byline"} and not author:
            author = value
        elif key in {"date", "published"} and not date:
            date = value
        elif key in {"source", "url"} and not source_url:
            source_url = value
    return author, date, source_url


def _markdown_frontmatter_values(text: str) -> tuple[dict[str, str], str]:
    match = _MARKDOWN_FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        values[_normalize_metadata_key(key)] = raw_value.strip().strip("\"'")
    return values, text[match.end() :]


def _humanize_json_key(key: str) -> str:
    readable = re.sub(r"[_\-]+", " ", key).strip()
    readable = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", readable)
    if not readable:
        return "value"
    return readable[0].upper() + readable[1:]


def _json_scalar_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _json_object_lines(value: Any, prefix: str = "") -> list[str]:
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            label = _humanize_json_key(str(key))
            key_path = f"{prefix}{label}" if not prefix else f"{prefix} > {label}"
            if isinstance(item, dict):
                lines.append(f"{key_path}:")
                nested = _json_object_lines(item, key_path)
                lines.extend(f"  {line}" if line else "" for line in nested)
            elif isinstance(item, list):
                if item and all(not isinstance(entry, (dict, list)) for entry in item):
                    lines.append(f"{key_path}: {', '.join(_json_scalar_text(entry) for entry in item)}")
                else:
                    lines.append(f"{key_path}:")
                    for index, entry in enumerate(item, start=1):
                        nested = _json_object_lines(entry, f"{key_path} > Item {index}")
                        if nested:
                            lines.extend(f"  {line}" if line else "" for line in nested)
            else:
                lines.append(f"{key_path}: {_json_scalar_text(item)}")
    elif isinstance(value, list):
        for index, item in enumerate(value, start=1):
            nested = _json_object_lines(item, f"{prefix}Item {index}")
            if nested:
                lines.extend(nested)
    else:
        lines.append(f"{prefix or 'Value'}: {_json_scalar_text(value)}")
    return lines


def _json_object_metadata(payload: dict[str, Any]) -> tuple[str, str, str, str, dict[str, str]]:
    title = ""
    author = ""
    date = ""
    source_url = ""
    metadata: dict[str, str] = {}
    for key, value in payload.items():
        normalized_key = _normalize_metadata_key(str(key))
        text_value = ""
        if isinstance(value, str):
            text_value = value.strip()
        elif isinstance(value, list) and value and all(not isinstance(item, (dict, list)) for item in value):
            text_value = ", ".join(_json_scalar_text(item) for item in value)
        if normalized_key in {_normalize_metadata_key(name) for name in _TITLE_FIELD_NAMES} and text_value and not title:
            title = text_value
        elif normalized_key in {_normalize_metadata_key(name) for name in _AUTHOR_FIELD_NAMES} and text_value and not author:
            author = text_value
        elif normalized_key in {_normalize_metadata_key(name) for name in _DATE_FIELD_NAMES} and text_value and not date:
            date = text_value
        elif normalized_key in {_normalize_metadata_key(name) for name in _URL_FIELD_NAMES} and text_value and not source_url:
            source_url = text_value
        elif text_value:
            metadata[str(key)] = text_value
    return title, author, date, source_url, metadata


def _section_entries_from_headings(text: str) -> list[tuple[str, str, str]]:
    sections: list[tuple[str, str, str]] = []
    heading_stack: list[str] = []
    current_lines: list[str] = []
    current_path = ""
    current_heading = ""
    for raw_line in text.splitlines():
        match = _MARKDOWN_HEADING_RE.match(raw_line)
        if match:
            body = clean_content("\n".join(current_lines))
            if body:
                sections.append((current_path, current_heading, body))
            level = len(match.group(1))
            heading = clean_content(match.group(2))
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(heading)
            current_path = " > ".join(heading_stack)
            current_heading = heading
            current_lines = []
            continue
        current_lines.append(raw_line)
    body = clean_content("\n".join(current_lines))
    if body:
        sections.append((current_path, current_heading, body))
    return sections or [("", "", clean_content(text))]


def _paragraphs_for_document(doc: DocumentInfo) -> list[tuple[str, str, str]]:
    if doc.content_type in {"markdown", "html"}:
        return _section_entries_from_headings(doc.body)
    if doc.content_type == "jsonl":
        serialized = doc.metadata.get("_jsonl_entries", "")
        if serialized:
            entries = json.loads(serialized)
            return [
                (
                    str(entry.get("section_path", "")),
                    str(entry.get("heading", "")),
                    clean_content(str(entry.get("text", ""))),
                )
                for entry in entries
                if clean_content(str(entry.get("text", "")))
            ]
    return [("", "", clean_content(doc.body))]


def _split_text_with_overlap(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    cleaned = clean_content(text)
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]
    chunks: list[str] = []
    position = 0
    while position < len(cleaned):
        end = min(len(cleaned), position + max_chars)
        if end < len(cleaned):
            split_at = cleaned.rfind("\n\n", position + 50, end)
            if split_at == -1:
                split_at = cleaned.rfind("\n", position + 50, end)
            if split_at == -1:
                split_at = cleaned.rfind(" ", position + 50, end)
            if split_at == -1 or split_at <= position:
                split_at = end
            else:
                split_at += 2 if cleaned[split_at : split_at + 2] == "\n\n" else 1
            end = split_at
        chunk = cleaned[position:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        position = max(end - overlap_chars, position + 1)
    if len(chunks) > 1 and len(chunks[-1]) < 50:
        unique_tail = chunks[-1]
        overlap_prefix = chunks[-2][-overlap_chars:] if overlap_chars and len(chunks[-2]) > overlap_chars else ""
        if overlap_prefix and unique_tail.startswith(overlap_prefix):
            unique_tail = unique_tail[len(overlap_prefix) :].lstrip()
        merged = clean_content(f"{chunks[-2]}\n\n{unique_tail}")
        if len(merged) <= max_chars:
            chunks[-2] = merged
            chunks.pop()
    return chunks


def extract_text_document(
    path: Path,
    relative_path: str,
    url_prefix: str,
    *,
    encoding: str | None = None,
) -> DocumentInfo:
    raw_text = _read_text_file(path, encoding=encoding)
    author, date, source_url = _document_metadata_from_prefixed_lines(raw_text)
    body = clean_content(raw_text)
    title = _document_title_from_first_line(raw_text, path.stem)
    return DocumentInfo(
        title=title,
        author=author,
        date=date,
        content_type="text",
        source_path=str(path.resolve()),
        relative_path=_normalize_relative_path(relative_path),
        body=body,
        url=_document_url(relative_path, url_prefix, source_url),
        metadata={},
    )


def extract_markdown_document(
    path: Path,
    relative_path: str,
    url_prefix: str,
    *,
    encoding: str | None = None,
) -> DocumentInfo:
    raw_text = _read_text_file(path, encoding=encoding)
    frontmatter, body_text = _markdown_frontmatter_values(raw_text)
    body = clean_content(body_text)
    heading_title = ""
    for line in body.splitlines():
        match = _MARKDOWN_HEADING_RE.match(line)
        if match:
            heading_title = clean_content(match.group(2))
            break
    title = frontmatter.get("title") or heading_title or path.stem
    return DocumentInfo(
        title=title,
        author=frontmatter.get("author", ""),
        date=frontmatter.get("date", ""),
        content_type="markdown",
        source_path=str(path.resolve()),
        relative_path=_normalize_relative_path(relative_path),
        body=body,
        url=_document_url(relative_path, url_prefix, frontmatter.get("url", "")),
        metadata={key: value for key, value in frontmatter.items() if key not in {"title", "author", "date", "url"}},
    )


def extract_html_document(
    path: Path,
    relative_path: str,
    url_prefix: str,
    *,
    encoding: str | None = None,
) -> DocumentInfo:
    parser = _HTMLDocumentParser()
    parser.feed(_read_text_file(path, encoding=encoding))
    parser.close()
    title = parser.title or parser.first_h1 or path.stem
    return DocumentInfo(
        title=title,
        author=parser.author,
        date=parser.date,
        content_type="html",
        source_path=str(path.resolve()),
        relative_path=_normalize_relative_path(relative_path),
        body=clean_content(parser.text),
        url=_document_url(relative_path, url_prefix, parser.url),
        metadata={},
    )


def extract_json_document(
    path: Path,
    relative_path: str,
    url_prefix: str,
    *,
    encoding: str | None = None,
) -> DocumentInfo:
    raw_text = _read_text_file(path, encoding=encoding)
    payload = json.loads(raw_text)
    title = path.stem
    author = ""
    date = ""
    source_url = ""
    metadata: dict[str, str] = {}
    if isinstance(payload, dict):
        title, author, date, source_url, metadata = _json_object_metadata(payload)
        title = title or path.stem
        body = clean_content("\n".join(_json_object_lines(payload)))
    else:
        body = clean_content("\n".join(_json_object_lines(payload)))
    return DocumentInfo(
        title=title or path.stem,
        author=author,
        date=date,
        content_type="json",
        source_path=str(path.resolve()),
        relative_path=_normalize_relative_path(relative_path),
        body=body,
        url=_document_url(relative_path, url_prefix, source_url),
        metadata=metadata,
    )


def extract_jsonl_document(
    path: Path,
    relative_path: str,
    url_prefix: str,
    *,
    encoding: str | None = None,
) -> DocumentInfo:
    raw_text = _read_text_file(path, encoding=encoding)
    entry_payloads: list[dict[str, str]] = []
    rendered_entries: list[str] = []
    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        heading = ""
        if isinstance(payload, dict):
            heading, _, _, _, _ = _json_object_metadata(payload)
        heading = heading or f"Line {line_number}"
        entry_text = clean_content("\n".join(_json_object_lines(payload)))
        if entry_text:
            entry_payloads.append({"section_path": "", "heading": heading, "text": entry_text})
            rendered_entries.append(entry_text)
    return DocumentInfo(
        title=path.stem,
        author="",
        date="",
        content_type="jsonl",
        source_path=str(path.resolve()),
        relative_path=_normalize_relative_path(relative_path),
        body=clean_content("\n\n".join(rendered_entries)),
        url=_document_url(relative_path, url_prefix),
        metadata={"_jsonl_entries": json.dumps(entry_payloads, ensure_ascii=False)},
    )


def chunk_document(doc: DocumentInfo, max_chars: int = 2000, overlap_chars: int = 200) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for section_path, heading, body in _paragraphs_for_document(doc):
        for text in _split_text_with_overlap(body, max_chars=max_chars, overlap_chars=overlap_chars):
            chunks.append(
                DocumentChunk(
                    section_path=section_path,
                    heading=heading,
                    chunk_index=0,
                    chunk_count=0,
                    text=text,
                    item_id="",
                )
            )
    if not chunks:
        return []
    document_id = stable_id("docsrc", doc.relative_path, "0", doc.title)
    chunk_count = len(chunks)
    for index, chunk in enumerate(chunks):
        chunk.chunk_index = index
        chunk.chunk_count = chunk_count
        chunk.item_id = stable_id("doc", doc.relative_path, document_id, str(index), chunk.section_path)
    return chunks


def build_document_chunk_content(doc: DocumentInfo, chunk: DocumentChunk) -> str:
    title = f"{doc.title} — {chunk.heading}" if chunk.heading else f"{doc.title} [{chunk.chunk_index + 1}/{chunk.chunk_count}]"
    lines = [
        f"Title: {title}",
        f"Source file: {doc.relative_path}",
        f"Content type: {document_content_type_value(doc.content_type)}",
        f"Chunk: {chunk.chunk_index + 1} of {chunk.chunk_count}",
    ]
    if chunk.section_path:
        lines.append(f"Section path: {chunk.section_path}")
    if doc.author:
        lines.append(f"Author: {doc.author}")
    if doc.date:
        lines.append(f"Date published: {doc.date}")
    if doc.url:
        lines.append(f"Source URL: {doc.url}")
    lines.extend(["", "Content body:", chunk.text])
    return "\n".join(lines)


def build_document_item(chunk: DocumentChunk, doc: DocumentInfo, acl_mode: str) -> dict[str, Any]:
    title = f"{doc.title} — {chunk.heading}" if chunk.heading else f"{doc.title} [{chunk.chunk_index + 1}/{chunk.chunk_count}]"
    properties: dict[str, Any] = {
        "url": f"{doc.url}#chunk={chunk.chunk_index}",
        "iconUrl": "",
        "sourceFile": doc.relative_path,
        "documentId": stable_id("docsrc", doc.relative_path, "0", doc.title),
        "contentType": document_content_type_value(doc.content_type),
        "sectionPath": chunk.section_path,
        "chunkIndex": chunk.chunk_index,
        "chunkCount": chunk.chunk_count,
    }
    if doc.author:
        properties["author"] = doc.author
    if doc.date:
        properties["datePublished"] = doc.date
    item = graph_like_item(
        item_id=chunk.item_id,
        title=title,
        item_type="document-chunk",
        content=build_document_chunk_content(doc, chunk),
        properties=properties,
        acl_mode=acl_mode,
    )
    item["properties"]["iconUrl"] = ""
    return item


def _extract_document(
    path: Path,
    relative_path: str,
    url_prefix: str,
    *,
    encoding: str | None = None,
) -> DocumentInfo:
    extension = path.suffix.lower().lstrip(".")
    content_type = CONTENT_TYPE_MAP.get(extension)
    if content_type == "markdown":
        return extract_markdown_document(path, relative_path, url_prefix, encoding=encoding)
    if content_type == "html":
        return extract_html_document(path, relative_path, url_prefix, encoding=encoding)
    if content_type == "json":
        return extract_json_document(path, relative_path, url_prefix, encoding=encoding)
    if content_type == "jsonl":
        return extract_jsonl_document(path, relative_path, url_prefix, encoding=encoding)
    return extract_text_document(path, relative_path, url_prefix, encoding=encoding)


def process_nontabular_file(
    file_path: Path,
    relative_path: str,
    content_type: str,
    *,
    encoding: str | None = None,
    max_chunk_chars: int = 2000,
    chunk_overlap: int = 200,
    url_prefix: str = "",
) -> tuple[DocumentInfo, list[DocumentChunk]]:
    normalized_content_type = CONTENT_TYPE_ALIASES.get(content_type, content_type)
    extension = file_path.suffix.lower().lstrip(".")
    expected_content_type = CONTENT_TYPE_MAP.get(extension, normalized_content_type)
    if normalized_content_type and expected_content_type != normalized_content_type:
        expected_content_type = normalized_content_type
    doc = _extract_document(file_path, relative_path, url_prefix, encoding=encoding)
    if expected_content_type and doc.content_type != expected_content_type:
        doc.content_type = expected_content_type
    return doc, chunk_document(doc, max_chars=max_chunk_chars, overlap_chars=chunk_overlap)


def is_empty(value: Any) -> bool:
    return value is None or str(value).strip().lower() in EMPTY_VALUES


def normalized(value: Any) -> str:
    return str(value or "").strip().casefold()


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\u001f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def find_first(row: dict[str, str], candidates: Iterable[str]) -> str:
    lowered = {k.casefold(): k for k in row}
    for candidate in candidates:
        actual = lowered.get(candidate.casefold())
        if actual and not is_empty(row.get(actual)):
            return row[actual].strip()
    return ""


def humanize_field(name: str, config: EnhancerConfig) -> str:
    if name in config.field_aliases:
        return config.field_aliases[name]
    readable = re.sub(r"[_\-]+", " ", name).strip()
    readable = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", readable)
    return readable or name


def _preserves_numeric_literal(field_name: str, config: EnhancerConfig | None = None) -> bool:
    """Return True when *field_name* names a time-period or identifier column.

    Such columns store codes or periods, not quantities, so their integer
    values should not receive thousands-separator decoration.
    Checks (in order): config key_field_candidates, common name set, common
    name suffixes.
    """
    field_lower = field_name.lower()
    if config is not None:
        for candidates in config.key_field_candidates.values():
            if field_lower in {c.casefold() for c in candidates}:
                return True
    return field_lower in _PRESERVE_NUMERIC_FIELD_NAMES or any(
        field_lower.endswith(suf) for suf in _PRESERVE_NUMERIC_SUFFIXES
    )


def display_value(value: str, field_name: str = "", *, config: EnhancerConfig | None = None) -> str:
    raw = str(value).strip()
    if not raw:
        return raw
    if _preserves_numeric_literal(field_name, config):
        return raw
    if re.fullmatch(r"-?\d+", raw):
        try:
            grouped = f"{int(raw):,}"
        except ValueError:
            return raw
        if grouped != raw and abs(int(raw)) >= 1000:
            return f"{raw} (also {grouped})"
    return raw


def fact_line(field_name: str, value: str, config: EnhancerConfig) -> str:
    label = humanize_field(field_name, config)
    if label == field_name:
        return f"- {field_name}: {display_value(value, field_name, config=config)}"
    return f"- {field_name} ({label}): {display_value(value, field_name, config=config)}"


def split_supporting_fact(fact: str) -> tuple[str, str] | None:
    if "=" not in fact:
        return None
    key, value = fact.split("=", 1)
    key = key.strip()
    value = value.strip()
    return (key, value) if key else None


def parse_referenced_rows(values: Iterable[str]) -> list[tuple[str, int]]:
    refs: list[tuple[str, int]] = []
    for value in values:
        for match in re.finditer(r"(?P<file>[A-Za-z0-9][A-Za-z0-9._\-/]*\.[A-Za-z0-9]+):row\s+(?P<row>\d+)", value):
            refs.append((match.group("file").casefold(), int(match.group("row"))))
    return refs


def sniff_delimiter(sample: str, path: Path) -> str:
    if sample:
        try:
            return csv.Sniffer().sniff(sample, delimiters=DELIMITER_CANDIDATES).delimiter
        except csv.Error:
            pass
    return "\t" if path.suffix.lower() == ".tsv" else ","


def open_tabular_reader(path: Path, encoding: str | None = None) -> tuple[Any, csv.DictReader]:
    """Open a tabular file and return a (handle, reader) pair.

    When *encoding* is given it is used directly.  When *encoding* is ``None``
    the function tries UTF-8-SIG then CP-1252 (common Excel export), falling
    back to UTF-8 with replacement characters so reading never hard-fails.
    """
    if encoding is not None:
        handle = path.open(newline="", encoding=encoding)
        sample = handle.read(16384)
        handle.seek(0)
        return handle, csv.DictReader(handle, delimiter=sniff_delimiter(sample, path))

    for enc in ("utf-8-sig", "cp1252"):
        try:
            handle = path.open(newline="", encoding=enc)
            sample = handle.read(16384)
            handle.seek(0)
            return handle, csv.DictReader(handle, delimiter=sniff_delimiter(sample, path))
        except UnicodeDecodeError:
            handle.close()
    handle = path.open(newline="", encoding="utf-8", errors="replace")
    sample = handle.read(16384)
    handle.seek(0)
    return handle, csv.DictReader(handle, delimiter=sniff_delimiter(sample, path))


def load_eval_items(eval_path: Path | None, encoding: str | None = None) -> list[EvalItem]:
    if not eval_path:
        return []
    if not eval_path.exists():
        raise FileNotFoundError(f"Evaluation set not found: {eval_path}")

    if eval_path.suffix.lower() == ".json":
        # JSON files are always decoded as UTF-8 regardless of the --encoding flag.
        payload = json.loads(eval_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            raw_items = payload
        else:
            raw_items = payload.get("items", [])
        items: list[EvalItem] = []
        for index, item in enumerate(raw_items):
            supporting: dict[str, str] = {}
            for fact in item.get("supporting_facts", []) or []:
                parsed = split_supporting_fact(str(fact))
                if parsed:
                    supporting[parsed[0]] = parsed[1]
            assertions = [
                str(assertion.get("value"))
                for assertion in item.get("assertions", []) or []
                if assertion.get("type") == "must_contain" and assertion.get("value") is not None
            ]
            items.append(
                EvalItem(
                    id=str(item.get("id") or f"eval-{index + 1}"),
                    prompt=str(item.get("prompt") or ""),
                    expected_answer=str(item.get("expected_answer") or ""),
                    supporting_facts=supporting,
                    assertions=assertions,
                    category=str(item.get("category") or ""),
                    difficulty=str(item.get("difficulty") or ""),
                    referenced_rows=parse_referenced_rows(
                        list(item.get("referenced_rows", []) or [])
                        + [str(item.get("source_location") or "")]
                    ),
                )
            )
        return items

    with eval_path.open(newline="", encoding=encoding or "utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [
            EvalItem(
                id=stable_id("eval", row.get("prompt", ""), str(index)),
                prompt=row.get("prompt", ""),
                expected_answer=row.get("expected_answer", ""),
                referenced_rows=parse_referenced_rows([row.get("source_location", "")]),
            )
            for index, row in enumerate(reader, start=1)
        ]


def eval_indexes(
    eval_items: list[EvalItem],
    config: EnhancerConfig,
) -> tuple[dict[tuple[str, int], list[EvalItem]], dict[tuple[str, str], list[EvalItem]]]:
    by_ref: dict[tuple[str, int], list[EvalItem]] = defaultdict(list)
    by_entity_year: dict[tuple[str, str], list[EvalItem]] = defaultdict(list)

    entity_candidates = config.key_field_candidates.get("entity", ())
    year_candidates = config.key_field_candidates.get("year", ())

    for item in eval_items:
        for filename, row_number in item.referenced_rows:
            by_ref[(filename, row_number)].append(item)

        entity = find_first(item.supporting_facts, entity_candidates)
        year = find_first(item.supporting_facts, year_candidates)
        if entity and year:
            by_entity_year[(normalized(entity), normalized(year))].append(item)

    return by_ref, by_entity_year


def row_value_for_fact(row: dict[str, str], fact_key: str, config: EnhancerConfig) -> str:
    """Return the row value that corresponds to a supporting-fact key from an eval item.

    Lookup precedence:
    1. Exact case-insensitive match on a row column name.
    2. Logical category match: fact_key is itself a key in key_field_candidates
       (e.g. ``"entity"`` or ``"year"``), so use that group's candidate list.
    3. Candidate reverse-lookup: fact_key matches a candidate in some group,
       so use ``find_first`` with that group's candidates (handles aliases like
       ``"country"`` → entity column named ``"countryName"``).
    """
    # 1. Exact case-insensitive row-key match.
    lowered_row = {k.casefold(): k for k in row}
    exact_key = lowered_row.get(fact_key.casefold())
    if exact_key and not is_empty(row.get(exact_key, "")):
        return row[exact_key].strip()

    # 2. Logical category name match (entity / year / iso) — case-insensitive.
    role_map = {k.casefold(): v for k, v in config.key_field_candidates.items()}
    role_candidates = role_map.get(fact_key.casefold())
    if role_candidates is not None:
        return find_first(row, role_candidates)

    # 3. Candidate reverse-lookup: find which group owns this candidate name.
    fact_cf = fact_key.casefold()
    for candidates in config.key_field_candidates.values():
        if fact_cf in {c.casefold() for c in candidates}:
            return find_first(row, candidates)

    return ""


def compatible_eval_matches(
    row: dict[str, str],
    basename: str,
    row_number: int,
    entity: str,
    year: str,
    by_ref: dict[tuple[str, int], list[EvalItem]],
    by_entity_year: dict[tuple[str, str], list[EvalItem]],
    config: EnhancerConfig,
) -> list[EvalItem]:
    matches: dict[str, EvalItem] = {}

    for item in by_ref.get((basename.casefold(), row_number), []):
        matches[item.id] = item

    for item in by_entity_year.get((normalized(entity), normalized(year)), []):
        present_facts = {
            key: expected
            for key, expected in item.supporting_facts.items()
            if not is_empty(expected) and not is_empty(row_value_for_fact(row, key, config))
        }
        if present_facts and all(
            normalized(row_value_for_fact(row, key, config)) == normalized(expected)
            for key, expected in present_facts.items()
        ):
            matches[item.id] = item

    return list(matches.values())


def is_long_indicator_csv(header: list[str], config: EnhancerConfig) -> bool:
    """Return True only when the config explicitly names long-indicator columns and all are present.

    Without an explicit ``longIndicatorColumns`` section in the config the function always
    returns False, ensuring that files with column names that happen to match the built-in
    defaults are not silently treated as long-format.
    """
    if not config.has_explicit_long_config:
        return False
    li = config.long_indicator_columns
    required = {li["idColumn"], li["nameColumn"], li["entityColumn"], li["yearColumn"], li["valueColumn"]}
    return required.issubset(set(header))


def natural_key(row: dict[str, str], relative_path: str, row_number: int, long_indicator: bool, config: EnhancerConfig) -> str:
    """Return a stable string key for deduplication and ID generation.

    Uses ``\\u001f`` (ASCII Unit Separator) as the field delimiter so that
    entity names or year values containing ``|`` cannot produce collisions.
    """
    entity = find_first(row, config.key_field_candidates.get("entity", ()))
    year = find_first(row, config.key_field_candidates.get("year", ()))
    iso = find_first(row, config.key_field_candidates.get("iso", ()))
    li = config.long_indicator_columns
    sep = "\u001f"
    if long_indicator and row.get(li["idColumn"]) and entity and year:
        return sep.join([relative_path, row.get(li["idColumn"], ""), iso, entity, year])
    return sep.join([relative_path, iso, entity, year, "row", str(row_number)])


def ordered_fields(header: list[str], eval_field_counts: Counter[str], config: EnhancerConfig) -> list[str]:
    priority_fields = config.priority_fields

    def score(field_name: str) -> tuple[int, int, str]:
        if field_name in priority_fields:
            return (0, priority_fields.index(field_name), field_name)
        if eval_field_counts[field_name]:
            return (1, -eval_field_counts[field_name], field_name)
        return (2, header.index(field_name), field_name)

    return sorted(header, key=score)


def build_record_content(
    *,
    title: str,
    relative_path: str,
    row_number: int | None,
    row: dict[str, str],
    header: list[str],
    eval_matches: list[EvalItem],
    eval_field_counts: Counter[str],
    include_eval_prompts: bool,
    include_eval_answers: bool,
    row_purpose: str,
    config: EnhancerConfig,
) -> str:
    entity = find_first(row, config.key_field_candidates.get("entity", ()))
    year = find_first(row, config.key_field_candidates.get("year", ()))
    non_empty_fields = [field_name for field_name in ordered_fields(header, eval_field_counts, config) if not is_empty(row.get(field_name))]
    priority_fields = config.priority_fields
    key_empty_fields = [
        field_name
        for field_name in priority_fields
        if field_name in header and is_empty(row.get(field_name))
    ]
    key_empty_fields.extend(
        field_name
        for field_name in ordered_fields(header, eval_field_counts, config)
        if field_name in eval_field_counts and is_empty(row.get(field_name))
    )
    key_empty_fields = list(dict.fromkeys(key_empty_fields))[:25]

    lines = [
        f"Title: {title}",
        f"Source file: {relative_path}",
    ]
    if row_number is not None:
        lines.append(f"Source data row: {row_number} (1-based, excluding the header row)")
    if entity:
        lines.append(f"Entity: {entity}")
    if year:
        lines.append(f"Year or date: {year}")
    lines.extend(
        [
            f"Record purpose: {row_purpose}",
            "",
            "Key facts:",
        ]
    )

    key_fields = [field_name for field_name in priority_fields if field_name in row and not is_empty(row.get(field_name))]
    key_fields += [
        field_name
        for field_name in non_empty_fields
        if field_name not in key_fields and eval_field_counts[field_name]
    ][:12]
    for field_name in key_fields[:28]:
        lines.append(fact_line(field_name, row[field_name], config))

    remaining = [field_name for field_name in non_empty_fields if field_name not in key_fields]
    if remaining:
        lines.extend(["", "All populated fields:"])
        for field_name in remaining:
            lines.append(fact_line(field_name, row[field_name], config))

    if key_empty_fields:
        lines.extend(["", "Important fields with no value in this row:"])
        lines.append("- " + ", ".join(key_empty_fields))

    if eval_matches:
        fields = sorted(
            {
                field
                for item in eval_matches
                for field in item.supporting_facts
                if not is_empty(row_value_for_fact(row, field, config))
            }
        )
        if fields:
            lines.extend(["", "Evaluation-derived retrieval focus fields:"])
            lines.append("- " + ", ".join(f"{field} ({humanize_field(field, config)})" for field in fields))

    if include_eval_prompts and eval_matches:
        lines.extend(["", "Example questions this record can answer:"])
        for item in eval_matches[:8]:
            if item.prompt:
                lines.append(f"- {item.prompt}")
            if include_eval_answers and item.expected_answer:
                lines.append(f"  Expected answer: {item.expected_answer}")

    return "\n".join(lines)


def graph_like_item(
    *,
    item_id: str,
    title: str,
    item_type: str,
    content: str,
    properties: dict[str, Any],
    acl_mode: str,
) -> dict[str, Any]:
    props = {
        "title": title,
        "itemType": item_type,
        **{key: value for key, value in properties.items() if value not in (None, "")},
    }
    item = {
        "id": item_id,
        "properties": props,
        "content": {"type": "text", "value": content},
    }
    if acl_mode != "none":
        item["acl"] = [{"type": acl_mode, "value": acl_mode, "accessType": "grant"}]
    return item


def write_item(jsonl_handle: Any, csv_writer: csv.DictWriter, item: dict[str, Any]) -> None:
    jsonl_handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    csv_writer.writerow(
        {
            "id": item["id"],
            "itemType": item["properties"].get("itemType", ""),
            "title": item["properties"].get("title", ""),
            "sourceFile": item["properties"].get("sourceFile", ""),
            "sourceRow": item["properties"].get("sourceRow", ""),
            "entityName": item["properties"].get("entityName", ""),
            "year": item["properties"].get("year", ""),
            "documentId": item["properties"].get("documentId", ""),
            "contentType": item["properties"].get("contentType", ""),
            "sectionPath": item["properties"].get("sectionPath", ""),
            "chunkIndex": item["properties"].get("chunkIndex", ""),
            "chunkCount": item["properties"].get("chunkCount", ""),
            "author": item["properties"].get("author", ""),
            "datePublished": item["properties"].get("datePublished", ""),
            "content": item["content"]["value"],
        }
    )


def update_coverage(coverage: EvalCoverage, eval_matches: list[EvalItem], item_id: str, content: str) -> None:
    for eval_item in eval_matches:
        coverage.matched_items.add(eval_item.id)
        coverage.matched_records[eval_item.id].append(item_id)
        for assertion in eval_item.assertions:
            if assertion and assertion in content:
                coverage.assertions_found[eval_item.id].add(assertion)


def collect_eval_field_counts(eval_items: list[EvalItem]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in eval_items:
        counts.update(item.supporting_facts.keys())
    return counts


def dataset_files(dataset_path: Path, extensions: set[str], exclude_path: Path | None = None, exclude_files: list[Path] | None = None) -> list[Path]:
    if dataset_path.is_file():
        return [dataset_path] if dataset_path.suffix.lower().lstrip(".") in extensions else []
    excluded_resolved = set()
    if exclude_files:
        for ef in exclude_files:
            if ef:
                excluded_resolved.add(ef.resolve())
    return sorted(
        path
        for path in dataset_path.rglob("*")
        if path.is_file()
        and path.suffix.lower().lstrip(".") in extensions
        and (exclude_path is None or not path.is_relative_to(exclude_path))
        and path.resolve() not in excluded_resolved
    )


def record_file_stats(relative_path: str, header: list[str]) -> FileStats:
    return FileStats(relative_path=relative_path, header=header)


def update_file_stats(stats: FileStats, row: dict[str, str], config: EnhancerConfig) -> None:
    stats.row_count += 1
    for key, value in row.items():
        if not is_empty(value):
            stats.non_empty_counts[key] += 1
    entity = find_first(row, config.key_field_candidates.get("entity", ()))
    year = find_first(row, config.key_field_candidates.get("year", ()))
    if entity:
        stats.entity_examples[entity] += 1
    if year:
        stats.year_values.add(year)


def item_url(relative_path: str, row_number: int | None = None, url_prefix: str = "") -> str:
    """Return a URL for a single-row or file-level item.

    When *url_prefix* is set (e.g. ``https://example.com/data``) the generated
    URL uses that base instead of ``file:///``, which is required for real Graph
    connector ingestion.  Trailing slashes on the prefix are normalised.
    """
    if url_prefix:
        prefix = url_prefix.rstrip("/")
        path = relative_path.replace("\\", "/").lstrip("/")
        base = f"{prefix}/{path}"
        return f"{base}#row={row_number}" if row_number is not None else base
    url = relative_path.replace("\\", "/")
    return f"file:///{url}#row={row_number}" if row_number is not None else f"file:///{url}"


def grouped_item_url(entity: str, year: str, iso: str, source_files: str, url_prefix: str = "") -> str:
    """Return a URL for a grouped long-format record.

    When *url_prefix* is set, a synthetic path ``/_grouped/{entity}/{year}``
    (optionally ``/{iso}``) is appended so each grouped record gets a unique,
    stable, human-readable HTTPS URL.  Without a prefix the raw *source_files*
    string is embedded in a ``file:///`` URL (legacy behaviour).
    """
    if url_prefix:
        prefix = url_prefix.rstrip("/")
        parts = [urlquote(x, safe="") for x in (entity, year, iso) if x]
        slug = "/".join(parts) if parts else "unknown"
        return f"{prefix}/_grouped/{slug}"
    path = source_files.replace("\\", "/")
    return f"file:///{path}"


def build_dataset_overview_content(stats: FileStats, eval_items: list[EvalItem], include_eval_prompts: bool, config: EnhancerConfig) -> str:
    populated = stats.non_empty_counts.most_common()
    entity_examples = ", ".join(entity for entity, _ in stats.entity_examples.most_common(8))
    years = sorted(stats.year_values, key=lambda value: (len(value), value))
    lines = [
        f"Title: Dataset guide — {stats.relative_path}",
        f"Source file: {stats.relative_path}",
        f"Rows: {stats.row_count}",
        f"Columns: {len(stats.header)}",
    ]
    if entity_examples:
        lines.append(f"Common entities: {entity_examples}")
    if years:
        lines.append(f"Year/date range: {years[0]} to {years[-1]}")

    lines.extend(["", "Column glossary:"])
    for field_name in stats.header:
        count = stats.non_empty_counts[field_name]
        lines.append(f"- {field_name}: {humanize_field(field_name, config)}; populated in {count} row(s)")

    if populated:
        lines.extend(["", "Most populated fields:"])
        lines.append("- " + ", ".join(field for field, _ in populated[:20]))

    if include_eval_prompts and eval_items:
        lines.extend(["", "Representative evaluation questions for this corpus:"])
        for item in eval_items[:8]:
            if item.prompt:
                lines.append(f"- {item.prompt}")

    lines.extend(
        [
            "",
            "Retrieval guidance:",
            "- Use row records for exact entity/year lookups and multi-field metric questions.",
            "- Use this dataset guide for field meanings, abbreviations, units, and available columns.",
        ]
    )
    return "\n".join(lines)


GRAPH_SCHEMA_NAME_MAX_LENGTH = 32


def graph_schema_property_name(source_name: str, used_names: set[str]) -> str:
    """Return a Graph-safe schema property name for an arbitrary source field."""
    parts = re.findall(r"[A-Za-z0-9]+", source_name)
    if parts:
        base = parts[0][:1].lower() + parts[0][1:]
        base += "".join(part[:1].upper() + part[1:] for part in parts[1:])
    else:
        base = "field"
    if not base[0].isalpha():
        base = "field" + base[:1].upper() + base[1:]
    base = base[:GRAPH_SCHEMA_NAME_MAX_LENGTH]

    candidate = base
    suffix = 2
    while candidate in used_names:
        suffix_text = str(suffix)
        candidate = f"{base[:GRAPH_SCHEMA_NAME_MAX_LENGTH - len(suffix_text)]}{suffix_text}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def schema_aliases(*aliases: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for alias in aliases:
        cleaned = " ".join(alias.split())
        if not cleaned or len(cleaned) > 128 or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 ]*", cleaned):
            continue
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def schema_suggestion(file_stats: list[FileStats], eval_field_counts: Counter[str], config: EnhancerConfig, *, has_nontabular: bool = False) -> dict[str, Any]:
    all_fields: Counter[str] = Counter()
    for stats in file_stats:
        all_fields.update({field: count for field, count in stats.non_empty_counts.items()})

    properties = [
        {
            "name": "title",
            "type": "String",
            "isSearchable": True,
            "isQueryable": True,
            "isRetrievable": True,
            "labels": ["title"],
            "aliases": ["name", "heading"],
        },
        {
            "name": "url",
            "type": "String",
            "isRetrievable": True,
            "labels": ["url"],
        },
        {
            "name": "iconUrl",
            "type": "String",
            "isRetrievable": True,
            "labels": ["iconUrl"],
        },
        {
            "name": "itemType",
            "type": "String",
            "isSearchable": False,
            "isQueryable": True,
            "isRetrievable": True,
            "isRefinable": True,
            "aliases": ["type", "recordType"],
        },
        {
            "name": "sourceFile",
            "type": "String",
            "isSearchable": False,
            "isQueryable": True,
            "isRetrievable": True,
            "isRefinable": True,
            "aliases": ["file", "dataset", "source"],
        },
        {
            "name": "sourceRow",
            "type": "Int64",
            "isQueryable": True,
            "isRetrievable": True,
            "aliases": ["row", "rowNumber"],
        },
        {
            "name": "entityName",
            "type": "String",
            "isSearchable": False,
            "isQueryable": True,
            "isRetrievable": True,
            "isRefinable": True,
            "aliases": ["entity", "country", "region", "organization", "location"],
        },
        {
            "name": "year",
            "type": "String",
            "isSearchable": False,
            "isQueryable": True,
            "isRetrievable": True,
            "isRefinable": True,
            "aliases": ["date", "period", "time"],
        },
        {
            "name": "isoCode",
            "type": "String",
            "isSearchable": False,
            "isQueryable": True,
            "isRetrievable": True,
            "isRefinable": True,
            "isExactMatchRequired": True,
            "aliases": ["iso", "countryCode"],
        },
        {
            "name": "rowCount",
            "type": "Int64",
            "isQueryable": True,
            "isRetrievable": True,
            "aliases": ["records", "recordCount"],
        },
    ]

    document_source_mappings: list[dict[str, str]] = []
    if has_nontabular:
        properties.extend([
            {
                "name": "documentId",
                "type": "String",
                "isQueryable": True,
                "isRetrievable": True,
                "aliases": ["document", "sourceDocument"],
            },
            {
                "name": "contentType",
                "type": "String",
                "isSearchable": False,
                "isQueryable": True,
                "isRetrievable": True,
                "isRefinable": True,
                "aliases": ["format", "fileType", "documentFormat", "mimeType"],
            },
            {
                "name": "sectionPath",
                "type": "String",
                "isSearchable": False,
                "isQueryable": True,
                "isRetrievable": True,
                "aliases": ["section", "heading", "headingPath"],
            },
            {
                "name": "chunkIndex",
                "type": "Int64",
                "isQueryable": True,
                "isRetrievable": True,
                "aliases": ["chunk"],
            },
            {
                "name": "chunkCount",
                "type": "Int64",
                "isQueryable": True,
                "isRetrievable": True,
                "aliases": ["totalParts", "totalSegments"],
            },
            {
                "name": "author",
                "type": "String",
                "isSearchable": False,
                "isQueryable": True,
                "isRetrievable": True,
                "aliases": ["creator", "writer"],
            },
            {
                "name": "datePublished",
                "type": "String",
                "isSearchable": False,
                "isQueryable": True,
                "isRetrievable": True,
                "aliases": ["publishedDate", "documentDate", "created"],
            },
        ])
        document_source_mappings = [
            {"sourceField": "documentId", "schemaProperty": "documentId", "displayName": "Document ID"},
            {"sourceField": "contentType", "schemaProperty": "contentType", "displayName": "Content type"},
            {"sourceField": "sectionPath", "schemaProperty": "sectionPath", "displayName": "Section path"},
            {"sourceField": "chunkIndex", "schemaProperty": "chunkIndex", "displayName": "Chunk index"},
            {"sourceField": "chunkCount", "schemaProperty": "chunkCount", "displayName": "Chunk count"},
            {"sourceField": "author", "schemaProperty": "author", "displayName": "Author"},
            {"sourceField": "datePublished", "schemaProperty": "datePublished", "displayName": "Date published"},
        ]

    value_col_cf = config.long_indicator_columns.get("valueColumn", "value").casefold()
    used_property_names = {prop["name"] for prop in properties}
    source_field_mappings = list(document_source_mappings)
    property_guidance = [
        {
            "name": prop["name"],
            "description": "Core connector property generated by the enhancer or populated by the connector pipeline.",
        }
        for prop in properties
    ]
    for field_name, _ in (eval_field_counts + all_fields).most_common(80):
        if field_name in used_property_names:
            continue
        property_name = graph_schema_property_name(field_name, used_property_names)
        display_name = humanize_field(field_name, config)
        aliases = schema_aliases(field_name, display_name) if display_name != property_name else schema_aliases(field_name)
        prop = {
            "name": property_name,
            "type": "String",
            "isSearchable": field_name.casefold() != value_col_cf,
            "isQueryable": True,
            "isRetrievable": True,
        }
        if aliases:
            prop["aliases"] = aliases[:10]
        source_field_mappings.append(
            {
                "sourceField": field_name,
                "schemaProperty": property_name,
                "displayName": display_name,
            }
        )
        property_guidance.append(
            {
                "name": property_name,
                "sourceField": field_name,
                "displayName": display_name,
                "description": "Source tabular field kept as a structured property for exact filtering or display. Keep richer narrative context in externalItem.content.",
            }
        )
        properties.append(
            prop
        )

    description = "Suggested Microsoft Graph connector schema for enhanced data."
    if has_nontabular and file_stats:
        description = "Suggested Microsoft Graph connector schema for enhanced tabular and document data."
    elif has_nontabular:
        description = "Suggested Microsoft Graph connector schema for enhanced document data."
    elif file_stats:
        description = "Suggested Microsoft Graph connector schema for enhanced tabular data."

    notes = [
        "This schema uses Graph connector labels arrays; register it before ingesting items and poll schema status until completed.",
        "No property is both searchable and refinable; those attributes are mutually exclusive.",
        "Refinable properties are intentionally limited to itemType, sourceFile, entityName, year, isoCode, and contentType because refinable cannot be added later via schema update.",
        "Populate url and iconUrl with valid absolute URLs in your connector pipeline before production ingestion.",
        "Use sourceFieldMappings to translate raw tabular column names to the Graph-safe schema property names during ingestion.",
        "Keep ACL assignment in the connector pipeline and use Entra object IDs or external groups according to source permissions.",
        "Keep exact source values as string properties when verbatim answers matter; precompute summary items for aggregate questions instead of relying on Copilot to sum across records.",
        "Use dataset guide and grouped long-format items to improve Copilot's understanding of tabular context.",
    ]
    if has_nontabular:
        notes.append("Document chunks use sectionPath and chunkIndex/chunkCount to preserve reading order and section context for Copilot retrieval.")

    return {
        "description": description,
        "baseType": "microsoft.graph.externalItem",
        "contentProperty": "Put the generated content.value text into the built-in externalItem content property; do not register content as a schema property.",
        "semanticLabels": {
            "title": "title",
            "url": "url",
            "iconUrl": "iconUrl",
        },
        "properties": properties,
        "sourceFieldMappings": source_field_mappings,
        "propertyGuidance": property_guidance,
        "notes": notes,
    }


def build_long_indicator_groups(
    rows_by_group: dict[tuple[str, str, str], list[dict[str, str]]],
    source_files_by_group: dict[tuple[str, str, str], set[str]],
    config: EnhancerConfig,
) -> Iterable[tuple[dict[str, str], list[str], list[str]]]:
    li = config.long_indicator_columns
    id_col = li["idColumn"]
    name_col = li["nameColumn"]
    entity_col = li["entityColumn"]
    year_col = li["yearColumn"]
    value_col = li["valueColumn"]
    iso_col = li.get("isoColumn", "")

    for (entity, year, iso), rows in sorted(rows_by_group.items()):
        group_row: dict[str, str] = {
            entity_col: entity,
            year_col: year,
        }
        if iso_col:
            group_row[iso_col] = iso
        indicator_lines: list[str] = []
        for row in sorted(rows, key=lambda item: item.get(id_col, "")):
            indicator_id = row.get(id_col, "")
            indicator_name = row.get(name_col, "")
            value = row.get(value_col, "")
            if is_empty(value):
                continue
            field_name = f"{indicator_id} value" if indicator_id else indicator_name
            group_row[field_name] = value
            if indicator_id and indicator_name:
                indicator_lines.append(f"- {indicator_id} ({indicator_name}): {display_value(value, value_col, config=config)}")
            elif indicator_name:
                indicator_lines.append(f"- {indicator_name}: {display_value(value, value_col, config=config)}")
            else:
                indicator_lines.append(f"- {value_col}: {display_value(value, value_col, config=config)}")
        if indicator_lines:
            yield group_row, indicator_lines, sorted(source_files_by_group[(entity, year, iso)])


def grouped_record_title(group_row: dict[str, str], source_files_display: str, config: EnhancerConfig) -> str:
    entity = find_first(group_row, config.key_field_candidates.get("entity", ()))
    year = find_first(group_row, config.key_field_candidates.get("year", ()))
    label = config.long_indicator_columns.get("groupLabel", "grouped long-format values")
    if entity and year:
        return f"{entity} ({year}) — {label}"
    if entity:
        return f"{entity} — {label}"
    return f"{source_files_display} — {label}"


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = EnhancerConfig.load(Path(args.config).resolve() if args.config else None)

    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset path not found: {dataset_path}")
    output_path = Path(args.output).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    eval_items = load_eval_items(Path(args.eval).resolve() if args.eval else None, encoding=getattr(args, "encoding", None))
    by_ref, by_entity_year = eval_indexes(eval_items, config)
    eval_field_counts = collect_eval_field_counts(eval_items)

    if args.include_eval_prompts and not args.eval:
        print("warning: --include-eval-prompts has no effect without --eval", file=sys.stderr)
    if args.include_eval_answers and not args.eval:
        print("warning: --include-eval-answers has no effect without --eval", file=sys.stderr)
    if args.focus_on_eval and not args.eval:
        print(
            "warning: --focus-on-eval without --eval will suppress all row output (no rows match an empty eval set)",
            file=sys.stderr,
        )

    extensions = {ext.lower().lstrip(".").strip() for ext in args.extensions.split(",") if ext.strip()}
    if not extensions:
        raise ValueError("--extensions must specify at least one file extension")

    url_prefix = getattr(args, "url_prefix", "")
    if url_prefix and not any(url_prefix.startswith(s) for s in ("http://", "https://", "file://")):
        raise ValueError(
            f"--url-prefix must start with http://, https://, or file://; got: {url_prefix!r}"
        )

    tabular_extensions = extensions & TABULAR_EXTENSIONS
    document_extensions = extensions & NON_TABULAR_EXTENSIONS

    # Exclude eval/config files from dataset discovery
    exclude_files: list[Path] = []
    if args.eval:
        exclude_files.append(Path(args.eval).resolve())
    if args.config:
        exclude_files.append(Path(args.config).resolve())

    csv_files = dataset_files(dataset_path, set(tabular_extensions), exclude_path=output_path, exclude_files=exclude_files) if tabular_extensions else []
    document_files = dataset_files(dataset_path, set(document_extensions), exclude_path=output_path, exclude_files=exclude_files) if document_extensions else []

    # Warn when eval flags are used with non-tabular files
    if document_files and args.eval:
        print(
            "warning: eval matching is only supported for tabular files; non-tabular files will not participate in eval matching",
            file=sys.stderr,
        )

    if not csv_files and not document_files:
        print(
            f"warning: no files with extension(s) {{{', '.join(sorted(extensions))}}} found under {dataset_path}",
            file=sys.stderr,
        )

    basename_counts: Counter[str] = Counter(f.name.casefold() for f in csv_files)
    duplicate_basenames = {name for name, count in basename_counts.items() if count > 1}
    if duplicate_basenames:
        print(
            f"warning: duplicate filenames detected ({', '.join(sorted(duplicate_basenames))}); "
            "eval row references by filename may match multiple files",
            file=sys.stderr,
        )

    file_stats: list[FileStats] = []
    skipped_files: list[dict[str, str]] = []
    coverage = EvalCoverage()
    nontabular_stats: list[dict[str, Any]] = []


    item_count = 0
    document_items_written = 0
    long_groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    long_group_sources: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    nontabular_content_types: list[str] = []

    jsonl_path = output_path / "enhanced-items.jsonl"
    csv_path = output_path / "enhanced-records.csv"
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as jsonl_handle, csv_path.open(
        "w", encoding="utf-8", newline=""
    ) as csv_handle:
        csv_writer = csv.DictWriter(
            csv_handle,
            fieldnames=[
                "id",
                "itemType",
                "title",
                "sourceFile",
                "sourceRow",
                "entityName",
                "year",
                "documentId",
                "contentType",
                "sectionPath",
                "chunkIndex",
                "chunkCount",
                "author",
                "datePublished",
                "content",
            ],
        )
        csv_writer.writeheader()

        for csv_file in csv_files:
            relative_path = str(csv_file.relative_to(dataset_path if dataset_path.is_dir() else dataset_path.parent))
            handle, reader = open_tabular_reader(csv_file, encoding=getattr(args, "encoding", None))
            with handle:
                header = list(reader.fieldnames or [])
                dup_header_names = {name for name, cnt in Counter(header).items() if cnt > 1}
                if dup_header_names:
                    print(
                        f"warning: {relative_path} has duplicate column name(s): "
                        f"{', '.join(sorted(dup_header_names))}; "
                        "later values will overwrite earlier ones for these columns",
                        file=sys.stderr,
                    )
                stats = record_file_stats(relative_path, header)
                long_indicator = is_long_indicator_csv(header, config)
                rows_generated_for_file = 0

                for row_number, row in enumerate(reader, start=1):
                    update_file_stats(stats, row, config)

                    entity = find_first(row, config.key_field_candidates.get("entity", ()))
                    year = find_first(row, config.key_field_candidates.get("year", ()))
                    basename = csv_file.name.casefold()
                    matches = compatible_eval_matches(
                        row,
                        basename,
                        row_number,
                        entity,
                        year,
                        by_ref,
                        by_entity_year,
                        config,
                    )
                    if args.focus_on_eval and not matches:
                        continue
                    if args.max_records_per_file and rows_generated_for_file >= args.max_records_per_file:
                        continue

                    if long_indicator and args.long_indicator_mode in {"grouped", "both"}:
                        iso = find_first(row, config.key_field_candidates.get("iso", ()))
                        if entity and year:
                            long_groups[(entity, year, iso)].append(dict(row))
                            long_group_sources[(entity, year, iso)].add(relative_path)
                            rows_generated_for_file += 1
                        if args.long_indicator_mode == "grouped":
                            continue

                    if not header or all(is_empty(value) for value in row.values()):
                        continue

                    title_entity = entity or csv_file.stem
                    title_year = f" ({year})" if year else ""
                    title = f"{title_entity}{title_year} — {csv_file.stem}"
                    item_id = stable_id("row", natural_key(row, relative_path, row_number, long_indicator, config))
                    content = build_record_content(
                        title=title,
                        relative_path=relative_path,
                        row_number=row_number,
                        row=row,
                        header=header,
                        eval_matches=matches,
                        eval_field_counts=eval_field_counts,
                        include_eval_prompts=args.include_eval_prompts,
                        include_eval_answers=args.include_eval_answers,
                        row_purpose="Self-contained tabular record for exact lookup and multi-field retrieval.",
                        config=config,
                    )
                    properties = {
                        "url": item_url(relative_path, row_number, url_prefix=getattr(args, "url_prefix", "")),
                        "sourceFile": relative_path,
                        "sourceRow": row_number,
                        "entityName": entity,
                        "year": year,
                        "isoCode": find_first(row, config.key_field_candidates.get("iso", ())),
                    }
                    for field_name in header:
                        if field_name in eval_field_counts and not is_empty(row.get(field_name)):
                            properties[field_name] = row[field_name]

                    item = graph_like_item(
                        item_id=item_id,
                        title=title,
                        item_type="record",
                        content=content,
                        properties=properties,
                        acl_mode=args.acl_mode,
                    )
                    write_item(jsonl_handle, csv_writer, item)
                    update_coverage(coverage, matches, item_id, content)
                    rows_generated_for_file += 1
                    item_count += 1

                if stats.row_count == 0:
                    stats.skipped_reason = "No data rows found"
                    skipped_files.append({"file": relative_path, "reason": stats.skipped_reason})
                file_stats.append(stats)

        li = config.long_indicator_columns
        entity_col = li["entityColumn"]
        year_col = li["yearColumn"]
        iso_col = li.get("isoColumn", "")

        for group_row, indicator_lines, source_file_list in build_long_indicator_groups(long_groups, long_group_sources, config):
            entity = group_row.get(entity_col, "")
            year = group_row.get(year_col, "")
            matches = by_entity_year.get((normalized(entity), normalized(year)), [])
            if args.focus_on_eval and not matches:
                continue
            primary_source = source_file_list[0] if source_file_list else ""
            source_files_display = ", ".join(source_file_list)
            title = grouped_record_title(group_row, source_files_display, config)
            header = list(group_row.keys())
            content = build_record_content(
                title=title,
                relative_path=source_files_display,
                row_number=None,
                row=group_row,
                header=header,
                eval_matches=matches,
                eval_field_counts=eval_field_counts,
                include_eval_prompts=args.include_eval_prompts,
                include_eval_answers=args.include_eval_answers,
                row_purpose="Grouped long-format record; multiple related values are co-located for the same key fields.",
                config=config,
            )
            content += "\n\nGrouped values:\n" + "\n".join(indicator_lines)
            item_id = stable_id("indicator-group", source_files_display, entity, year, group_row.get(iso_col, "") if iso_col else "")
            item = graph_like_item(
                item_id=item_id,
                title=title,
                item_type="grouped-record",
                content=content,
                properties={
                    "url": grouped_item_url(
                        entity,
                        year,
                        group_row.get(iso_col, "") if iso_col else "",
                        primary_source,
                        url_prefix=getattr(args, "url_prefix", ""),
                    ),
                    "sourceFile": source_files_display,
                    "entityName": entity,
                    "year": year,
                    "isoCode": group_row.get(iso_col, "") if iso_col else "",
                },
                acl_mode=args.acl_mode,
            )
            write_item(jsonl_handle, csv_writer, item)
            update_coverage(coverage, matches, item_id, content)
            item_count += 1

        if not args.no_overviews:
            for stats in file_stats:
                if stats.row_count == 0:
                    continue
                title = f"Dataset guide — {stats.relative_path}"
                content = build_dataset_overview_content(stats, eval_items, args.include_eval_prompts, config)
                item = graph_like_item(
                    item_id=stable_id("dataset-guide", stats.relative_path),
                    title=title,
                    item_type="dataset-guide",
                    content=content,
                    properties={
                        "url": item_url(stats.relative_path, url_prefix=getattr(args, "url_prefix", "")),
                        "sourceFile": stats.relative_path,
                        "rowCount": stats.row_count,
                    },
                    acl_mode=args.acl_mode,
                )
                write_item(jsonl_handle, csv_writer, item)
                item_count += 1

        # --- Non-tabular file processing ---
        for nt_file in document_files:
            relative_path = str(nt_file.relative_to(dataset_path if dataset_path.is_dir() else dataset_path.parent))
            doc, chunks = process_nontabular_file(
                nt_file,
                relative_path,
                CONTENT_TYPE_MAP.get(nt_file.suffix.lower().lstrip("."), "text"),
                encoding=getattr(args, "encoding", None),
                max_chunk_chars=2000,
                chunk_overlap=200,
                url_prefix=url_prefix,
            )
            if args.max_records_per_file:
                # Smoke-test cap: limit emitted chunks while preserving each chunk's
                # original chunk_count metadata so downstream consumers know the full
                # document size even when only a prefix is written.
                chunks = chunks[: args.max_records_per_file]
            if not chunks:
                skipped_files.append({"file": relative_path, "reason": "No extractable document content found"})
                continue
            mime_content_type = document_content_type_value(doc.content_type)
            nontabular_content_types.append(mime_content_type)
            nontabular_stats.append(
                {
                    "file": relative_path,
                    "contentType": mime_content_type,
                    "chunkCount": len(chunks),
                    "titles": [doc.title],
                }
            )

            for chunk in chunks:
                item = build_document_item(chunk, doc, args.acl_mode)
                write_item(jsonl_handle, csv_writer, item)
                item_count += 1
                document_items_written += 1

    unmatched_eval_items = [
        {
            "id": item.id,
            "prompt": item.prompt,
            "supportingFacts": item.supporting_facts,
            "referencedRows": [f"{filename}:row {row}" for filename, row in item.referenced_rows],
        }
        for item in eval_items
        if item.id not in coverage.matched_items
    ]
    assertion_gaps = []
    for item in eval_items:
        missing = sorted(set(item.assertions) - coverage.assertions_found.get(item.id, set()))
        if missing:
            assertion_gaps.append({"id": item.id, "prompt": item.prompt, "missingAssertions": missing})

    report = {
        "dataset": str(dataset_path),
        "eval": str(Path(args.eval).resolve()) if args.eval else None,
        "config": str(Path(args.config).resolve()) if args.config else None,
        "output": str(output_path),
        "itemsWritten": item_count,
        "filesProcessed": len(csv_files) + len(document_files),
        "tabularFilesProcessed": len(csv_files),
        "nontabularFilesProcessed": len(document_files),
        "nontabularContentTypes": sorted(set(nontabular_content_types)),
        "filesSkipped": skipped_files,
        "evalItems": len(eval_items),
        "evalItemsMatched": len(coverage.matched_items),
        "evalItemsUnmatched": len(unmatched_eval_items),
        "evalAssertionGaps": len(assertion_gaps),
        "longIndicatorMode": args.long_indicator_mode,
        "includeEvalPrompts": args.include_eval_prompts,
        "includeEvalAnswers": args.include_eval_answers,
        "outputs": {
            "jsonl": str(jsonl_path),
            "csv": str(csv_path),
            "report": str(output_path / "enhancement-report.json"),
            "schemaSuggestion": str(output_path / "schema-suggestion.json"),
        },
    }

    (output_path / "enhancement-report.json").write_text(
        json.dumps(
            {
                **report,
                "unmatchedEvalItems": unmatched_eval_items,
                "assertionGaps": assertion_gaps,
                "fileStats": [
                    {
                        "file": stats.relative_path,
                        "rows": stats.row_count,
                        "columns": stats.header,
                        "topEntities": stats.entity_examples.most_common(10),
                        "yearCount": len(stats.year_values),
                        "skippedReason": stats.skipped_reason,
                    }
                    for stats in file_stats
                ],
                "nontabularStats": nontabular_stats,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output_path / "schema-suggestion.json").write_text(
        json.dumps(schema_suggestion(file_stats, eval_field_counts, config, has_nontabular=document_items_written > 0), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_path / "unmatched-eval-items.json").write_text(
        json.dumps(unmatched_eval_items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Copilot-friendly enriched JSONL/CSV records from tabular and non-tabular datasets."
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    parser.add_argument(
        "--dataset",
        required=True,
        help="Tabular or document-like file or directory containing source datasets.",
    )
    parser.add_argument("--eval", help="Eval set JSON or CSV. Evalgen JSON is supported.")
    parser.add_argument("--output", required=True, help="Directory for generated enhanced data.")
    parser.add_argument(
        "--config",
        default=None,
        help="Optional JSON config file for field aliases, priority fields, key-field candidates, and long-format grouping columns.",
    )
    parser.add_argument(
        "--extensions",
        default="csv,tsv",
        help="Comma-separated file extensions to process. Default: csv,tsv. Non-tabular types (txt, md, markdown, html, htm, json, jsonl) are opt-in.",
    )
    parser.add_argument(
        "--long-indicator-mode",
        choices=["grouped", "row", "both"],
        default="grouped",
        help="How to handle long-format tables. 'grouped' (default) pivots rows by entity and time period; requires explicit longIndicatorColumns in a config file. 'row' keeps one item per source row. 'both' emits both.",
    )
    parser.add_argument(
        "--include-eval-prompts",
        action="store_true",
        help="Include matching eval prompts as example questions in content. Useful for experiments; avoid for holdout evals.",
    )
    parser.add_argument(
        "--include-eval-answers",
        action="store_true",
        help="Include expected eval answers. Requires --include-eval-prompts and should not be used with holdout tests.",
    )
    parser.add_argument(
        "--focus-on-eval",
        action="store_true",
        help="Only emit tabular records that match eval references or supporting facts, plus dataset guide items. Non-tabular files do not participate in eval matching.",
    )
    parser.add_argument(
        "--no-overviews",
        action="store_true",
        help="Do not emit dataset-guide overview/glossary items.",
    )
    parser.add_argument(
        "--max-records-per-file",
        type=int,
        default=0,
        help=(
            "Limit source rows processed per input file. "
            "For document-like files, the limit applies to generated chunks per source file. "
            "In 'grouped' mode this limits source rows consumed into groups; "
            "in 'both' mode each row counts toward the limit twice. "
            "Intended for smoke tests."
        ),
    )
    parser.add_argument(
        "--acl-mode",
        choices=["none", "everyone", "everyoneExceptGuests"],
        default="none",
        help="Optionally add a placeholder ACL grant. Default omits ACLs so your connector can apply source permissions.",
    )
    parser.add_argument(
        "--encoding",
        default=None,
        help=(
            "Input encoding for source dataset files and CSV eval files. "
            "Default: auto-detect (tries UTF-8 with BOM, then Windows-1252). "
            "Set explicitly when auto-detection fails, e.g. 'latin-1' or 'utf-8'."
        ),
    )
    parser.add_argument(
        "--url-prefix",
        default="",
        dest="url_prefix",
        help=(
            "HTTPS prefix for generated item URLs, e.g. 'https://example.com/data'. "
            "Without this option, URLs use 'file:///' paths which are not valid for "
            "real Graph connector ingestion. Grouped-record URLs are synthesised as "
            "{prefix}/_grouped/{entity}/{year}[/{iso}]."
        ),
    )
    args = parser.parse_args(argv)
    if args.include_eval_answers and not args.include_eval_prompts:
        parser.error("--include-eval-answers requires --include-eval-prompts")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        report = run(parse_args(argv or sys.argv[1:]))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
