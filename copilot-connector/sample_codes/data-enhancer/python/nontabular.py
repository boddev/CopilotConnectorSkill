"""Compatibility wrapper for legacy non-tabular helpers.

The document pipeline now lives in enhance_for_copilot.py. This module keeps the
older helper names importable for callers that still reference nontabular.py.
"""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enhance_for_copilot import (
    CONTENT_TYPE_ALIASES,
    CONTENT_TYPE_MAP,
    NON_TABULAR_EXTENSIONS,
    DocumentInfo,
    _HTMLDocumentParser,
    _json_object_lines,
    _json_object_metadata,
    _json_scalar_text,
    _markdown_frontmatter_values,
    _section_entries_from_headings,
    _split_text_with_overlap,
    build_document_chunk_content,
    chunk_document,
    clean_content,
    extract_html_document as _extract_html_document_path,
    extract_json_document as _extract_json_document_path,
    extract_jsonl_document as _extract_jsonl_document_path,
    extract_markdown_document as _extract_markdown_document_path,
    extract_text_document as _extract_text_document_path,
    process_nontabular_file as _process_nontabular_file,
)


NONTABULAR_EXTENSIONS = NON_TABULAR_EXTENSIONS
DEFAULT_CHUNK_MAX_CHARS = 2000
DEFAULT_CHUNK_OVERLAP = 200


@dataclass
class DocumentMetadata:
    title: str = ""
    author: str = ""
    date_published: str = ""
    source_url: str = ""


@dataclass
class DocumentChunk:
    source_file: str
    title: str
    content_type: str
    section_path: str
    chunk_index: int
    chunk_count: int
    content: str
    document_id: str
    author: str = ""
    date_published: str = ""
    url: str = ""
    icon_url: str = ""
    item_id: str = ""


def cleanup_content(text: str) -> str:
    return clean_content(text)


def chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_MAX_CHARS, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    return _split_text_with_overlap(text, max_chars=max_chars, overlap_chars=overlap)


def parse_markdown_metadata(content: str) -> tuple[str, DocumentMetadata]:
    frontmatter, body = _markdown_frontmatter_values(content)
    return body, DocumentMetadata(
        title=frontmatter.get("title", ""),
        author=frontmatter.get("author", ""),
        date_published=frontmatter.get("date", ""),
        source_url=frontmatter.get("url", ""),
    )


def extract_text_document(content: str, file_path: str) -> tuple[str, DocumentMetadata]:
    author = ""
    date = ""
    source_url = ""
    for line in content.splitlines()[:12]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().casefold()
        cleaned_value = value.strip()
        if normalized in {"author", "byline"} and not author:
            author = cleaned_value
        elif normalized in {"date", "published"} and not date:
            date = cleaned_value
        elif normalized in {"source", "url"} and not source_url:
            source_url = cleaned_value
    body = clean_content(content)
    title = next((line.strip() for line in content.splitlines() if line.strip()), Path(file_path).stem)
    if len(title) > 120:
        title = Path(file_path).stem
    return body, DocumentMetadata(title=title, author=author, date_published=date, source_url=source_url)


def extract_markdown_document(content: str, file_path: str) -> tuple[str, DocumentMetadata]:
    body, metadata = parse_markdown_metadata(content)
    cleaned = clean_content(body)
    if not metadata.title:
        for line in cleaned.splitlines():
            if line.startswith("# "):
                metadata.title = line[2:].strip()
                break
    metadata.title = metadata.title or Path(file_path).stem
    return cleaned, metadata


def extract_html_document(content: str, file_path: str) -> tuple[str, DocumentMetadata]:
    parser = _HTMLDocumentParser()
    parser.feed(content)
    parser.close()
    return clean_content(parser.text), DocumentMetadata(
        title=parser.title or parser.first_h1 or Path(file_path).stem,
        author=parser.author,
        date_published=parser.date,
        source_url=parser.url,
    )


def extract_json_document(content: str, file_path: str) -> list[tuple[str, DocumentMetadata]]:
    payload = json.loads(content)
    if isinstance(payload, list):
        documents: list[tuple[str, DocumentMetadata]] = []
        for index, item in enumerate(payload):
            if isinstance(item, dict):
                title, author, date, source_url, _ = _json_object_metadata(item)
                documents.append(
                    (
                        clean_content("\n".join(_json_object_lines(item))),
                        DocumentMetadata(
                            title=title or f"{Path(file_path).stem} item {index + 1}",
                            author=author,
                            date_published=date,
                            source_url=source_url,
                        ),
                    )
                )
            else:
                documents.append((clean_content(_json_scalar_text(item)), DocumentMetadata(title=f"{Path(file_path).stem} item {index + 1}")))
        return documents
    if isinstance(payload, dict):
        title, author, date, source_url, _ = _json_object_metadata(payload)
        return [(
            clean_content("\n".join(_json_object_lines(payload))),
            DocumentMetadata(
                title=title or Path(file_path).stem,
                author=author,
                date_published=date,
                source_url=source_url,
            ),
        )]
    return [(clean_content(_json_scalar_text(payload)), DocumentMetadata(title=Path(file_path).stem))]


def extract_jsonl_document(content: str, file_path: str) -> list[tuple[str, DocumentMetadata]]:
    documents: list[tuple[str, DocumentMetadata]] = []
    for index, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            title, author, date, source_url, _ = _json_object_metadata(payload)
            body = clean_content("\n".join(_json_object_lines(payload)))
            documents.append(
                (
                    body,
                    DocumentMetadata(
                        title=title or f"Line {index}",
                        author=author,
                        date_published=date,
                        source_url=source_url,
                    ),
                )
            )
        else:
            documents.append((clean_content(_json_scalar_text(payload)), DocumentMetadata(title=f"Line {index}")))
    return documents


def split_into_sections(content: str, content_type: str) -> list[tuple[str, str]]:
    normalized = CONTENT_TYPE_ALIASES.get(content_type, content_type)
    if normalized in {"markdown", "html"}:
        return [(section_path, text) for section_path, _, text in _section_entries_from_headings(content)]
    return [("", clean_content(content))]


def semantic_chunk_document(
    content: str,
    content_type: str,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    for section_path, text in split_into_sections(content, content_type):
        for chunk in chunk_text(text, max_chars=max_chars, overlap=overlap):
            chunks.append((section_path, chunk))
    return chunks


def stable_document_id(source_file: str, document_index: int, title: str) -> str:
    digest = hashlib.sha256(f"{source_file}\x1f{document_index}\x1f{title}".encode("utf-8")).hexdigest()[:24]
    return f"docsrc-{digest}"


def stable_chunk_id(source_file: str, document_id: str, chunk_index: int, section_path: str) -> str:
    digest = hashlib.sha256(
        f"{source_file}\x1f{document_id}\x1f{chunk_index}\x1f{section_path}".encode("utf-8")
    ).hexdigest()[:24]
    return f"doc-{digest}"


def process_nontabular_file(
    file_path: Path,
    relative_path: str,
    content_type: str,
    *,
    encoding: str | None = None,
    max_chunk_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    url_prefix: str = "",
) -> list[DocumentChunk]:
    doc, chunks = _process_nontabular_file(
        file_path,
        relative_path,
        content_type,
        encoding=encoding,
        max_chunk_chars=max_chunk_chars,
        chunk_overlap=chunk_overlap,
        url_prefix=url_prefix,
    )
    document_id = stable_document_id(relative_path, 0, doc.title)
    converted: list[DocumentChunk] = []
    for chunk in chunks:
        title = f"{doc.title} — {chunk.heading}" if chunk.heading else f"{doc.title} [{chunk.chunk_index + 1}/{chunk.chunk_count}]"
        converted.append(
            DocumentChunk(
                source_file=doc.relative_path,
                title=title,
                content_type=doc.content_type,
                section_path=chunk.section_path,
                chunk_index=chunk.chunk_index,
                chunk_count=chunk.chunk_count,
                content=chunk.text,
                document_id=document_id,
                author=doc.author,
                date_published=doc.date,
                url=f"{doc.url}#chunk={chunk.chunk_index}",
                icon_url="",
                item_id=chunk.item_id,
            )
        )
    return converted
