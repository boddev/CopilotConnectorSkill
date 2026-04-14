# Throttle-resilient ingestion with batch concurrency control
# Prerequisites: pip install msgraph-sdk azure-identity

import asyncio
import json
from typing import Callable, Optional

from msgraph import GraphServiceClient
from msgraph.generated.models.external_connectors.external_item import ExternalItem
from msgraph.generated.models.external_connectors.external_item_content import ExternalItemContent
from msgraph.generated.models.external_connectors.external_item_content_type import ExternalItemContentType
from msgraph.generated.models.external_connectors.properties import Properties
from msgraph.generated.models.o_data_errors.o_data_error import ODataError


class ResilientIngestion:
    """Manages throttle-resilient item ingestion with concurrency control."""

    def __init__(self, graph_client: GraphServiceClient, connection_id: str) -> None:
        self._graph_client = graph_client
        self._connection_id = connection_id

    async def ingest_with_retry(
        self, item: ExternalItem, max_retries: int = 5
    ) -> None:
        """Ingest a single item with exponential backoff retry on throttling."""
        for attempt in range(max_retries + 1):
            try:
                await self._graph_client.external.connections.by_external_connection_id(
                    self._connection_id
                ).items.by_external_item_id(item.id).put(item)
                return  # Success
            except ODataError as e:
                if e.response_status_code != 429:
                    raise

                if attempt == max_retries:
                    raise

                # Respect Retry-After header if available, otherwise exponential backoff
                retry_after = 2**attempt
                if e.response_headers:
                    retry_values = e.response_headers.get("Retry-After", [])
                    if retry_values:
                        try:
                            retry_after = int(retry_values[0])
                        except (ValueError, IndexError):
                            pass

                print(
                    f"Throttled on item {item.id}. "
                    f"Retry {attempt + 1}/{max_retries} after {retry_after}s"
                )
                await asyncio.sleep(retry_after)

    async def batch_ingest(
        self,
        items: list[ExternalItem],
        max_concurrency: int = 4,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """
        Batch ingest items with controlled concurrency.
        Uses a semaphore to limit parallel requests (recommended: 4-8,
        never exceeding the 25 concurrent operations per connection limit).
        """
        semaphore = asyncio.Semaphore(max_concurrency)
        completed = 0

        async def _ingest_one(item: ExternalItem) -> None:
            nonlocal completed
            async with semaphore:
                await self.ingest_with_retry(item)
                completed += 1
                if on_progress:
                    on_progress(completed, len(items))

        await asyncio.gather(*[_ingest_one(item) for item in items])

    async def ingest_with_auto_chunk(self, item: ExternalItem) -> None:
        """
        Check payload size before ingestion and auto-chunk if needed.
        The 4 MB limit applies to the full serialized request body.
        """
        byte_size = _estimate_payload_size(item)

        if byte_size > 3_800_000:  # Leave 200KB buffer below 4MB limit
            print(
                f"Item {item.id} is {byte_size / 1_000_000:.1f}MB — chunking required."
            )

            chunks = _chunk_content(
                item.content.value if item.content else "",
                max_chunk_bytes=3_500_000,
            )

            for i, chunk in enumerate(chunks):
                chunked_item = _clone_item_with_chunk(item, chunk, i, len(chunks))
                await self.ingest_with_retry(chunked_item)
        else:
            await self.ingest_with_retry(item)


def _estimate_payload_size(item: ExternalItem) -> int:
    """Estimate the serialized payload size in bytes."""
    payload: dict = {}
    if item.id:
        payload["id"] = item.id
    if item.properties and item.properties.additional_data:
        payload["properties"] = item.properties.additional_data
    if item.content and item.content.value:
        payload["content"] = item.content.value
    return len(json.dumps(payload, default=str).encode("utf-8"))


def _chunk_content(content: str, max_chunk_bytes: int) -> list[str]:
    """Split content at paragraph boundaries, respecting byte size limits."""
    paragraphs = content.split("\n\n")
    chunks: list[str] = []
    current_parts: list[str] = []
    current_size = 0

    for para in paragraphs:
        if not para.strip():
            continue

        para_size = len(para.encode("utf-8"))

        if current_size + para_size > max_chunk_bytes and current_parts:
            chunks.append("\n\n".join(current_parts))
            current_parts = []
            current_size = 0

        current_parts.append(para)
        current_size += para_size

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


def _clone_item_with_chunk(
    original: ExternalItem, chunk_content: str, chunk_index: int, total_chunks: int
) -> ExternalItem:
    """Create a chunked version of an item with a unique ID and title context."""
    original_props = (
        dict(original.properties.additional_data)
        if original.properties and original.properties.additional_data
        else {}
    )

    original_title = original_props.get("title", "Document")

    props = dict(original_props)
    props["title"] = f"{original_title} (Part {chunk_index + 1} of {total_chunks})"
    props["parentDocumentId"] = original.id or ""
    props["chunkIndex"] = chunk_index
    props["totalChunks"] = total_chunks

    # Prepend contextual header for self-contained chunks
    context_header = (
        f"Document: {original_title}\n"
        f"Part {chunk_index + 1} of {total_chunks}\n\n"
    )

    return ExternalItem(
        id=f"{original.id}_chunk_{chunk_index}",
        acl=original.acl,
        properties=Properties(additional_data=props),
        content=ExternalItemContent(
            value=context_header + chunk_content,
            type=(
                original.content.type
                if original.content
                else ExternalItemContentType.Text
            ),
        ),
    )
