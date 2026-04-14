# Incremental sync pattern: track changes and only re-ingest modified items
# Prerequisites: pip install msgraph-sdk azure-identity

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from msgraph import GraphServiceClient
from msgraph.generated.models.external_connectors.external_item import ExternalItem
from msgraph.generated.models.external_connectors.external_item_content import ExternalItemContent
from msgraph.generated.models.external_connectors.external_item_content_type import ExternalItemContentType
from msgraph.generated.models.external_connectors.acl import Acl
from msgraph.generated.models.external_connectors.acl_type import AclType
from msgraph.generated.models.external_connectors.access_type import AccessType
from msgraph.generated.models.external_connectors.properties import Properties
from msgraph.generated.models.o_data_errors.o_data_error import ODataError


@dataclass
class SourceItem:
    """Represents an item from the external data source."""

    id: str
    title: str
    status: str
    full_content: str
    url: str
    icon_url: Optional[str] = None
    last_modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SyncCheckpoint:
    """Tracks sync state between incremental sync runs."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    known_item_ids: set[str] = field(default_factory=set)


class IncrementalSync:
    """Manages incremental sync for a Copilot Connector."""

    def __init__(self, graph_client: GraphServiceClient, connection_id: str) -> None:
        self._graph_client = graph_client
        self._connection_id = connection_id

    async def run_incremental_sync(
        self,
        current_source_items: list[SourceItem],
        last_checkpoint: SyncCheckpoint,
    ) -> SyncCheckpoint:
        """
        Perform incremental sync by comparing source items against a checkpoint.
        Only ingests new/modified items and deletes removed items.

        Returns:
            A new SyncCheckpoint reflecting the current state.
        """
        source_by_id = {item.id: item for item in current_source_items}
        previous_ids = last_checkpoint.known_item_ids

        # 1. Find new and modified items
        to_upsert = [
            item
            for item in current_source_items
            if item.id not in previous_ids
            or item.last_modified > last_checkpoint.timestamp
        ]

        # 2. Find deleted items (in previous checkpoint but not in current source)
        to_delete = [
            item_id for item_id in previous_ids if item_id not in source_by_id
        ]

        print(
            f"Incremental sync: {len(to_upsert)} upserts, {len(to_delete)} deletes"
        )

        # 3. Upsert new/modified items
        for source_item in to_upsert:
            external_item = _map_to_external_item(source_item)
            await self._graph_client.external.connections.by_external_connection_id(
                self._connection_id
            ).items.by_external_item_id(source_item.id).put(external_item)

        # 4. Delete removed items
        for item_id in to_delete:
            try:
                await self._graph_client.external.connections.by_external_connection_id(
                    self._connection_id
                ).items.by_external_item_id(item_id).delete()
            except ODataError as e:
                if e.response_status_code == 404:
                    pass  # Item already deleted — safe to ignore
                else:
                    raise

        # 5. Return updated checkpoint
        new_checkpoint = SyncCheckpoint(
            timestamp=datetime.now(timezone.utc),
            known_item_ids=set(source_by_id.keys()),
        )
        await self._save_checkpoint(new_checkpoint)
        return new_checkpoint

    async def run_hash_based_sync(
        self,
        current_source_items: list[SourceItem],
        previous_hashes: dict[str, str],
    ) -> dict[str, str]:
        """
        Hash-based change detection: only re-ingest items whose content hash changed.
        More efficient than timestamp-based when source doesn't track modification dates.

        Returns:
            Updated hash dictionary reflecting the current state.
        """
        updated_hashes = dict(previous_hashes)

        for source_item in current_source_items:
            current_hash = _compute_content_hash(source_item)

            if previous_hashes.get(source_item.id) == current_hash:
                continue  # No changes — skip

            external_item = _map_to_external_item(source_item)
            await self._graph_client.external.connections.by_external_connection_id(
                self._connection_id
            ).items.by_external_item_id(source_item.id).put(external_item)

            updated_hashes[source_item.id] = current_hash

        return updated_hashes

    async def _save_checkpoint(self, checkpoint: SyncCheckpoint) -> None:
        """Save checkpoint to persistent storage (database, blob storage, or file)."""
        # Implement: save to database, blob storage, or local file
        print(
            f"Checkpoint saved: {checkpoint.timestamp}, "
            f"{len(checkpoint.known_item_ids)} items"
        )


def _map_to_external_item(source: SourceItem) -> ExternalItem:
    """Convert a source item to a Microsoft Graph ExternalItem."""
    return ExternalItem(
        id=source.id,
        acl=[
            Acl(
                type=AclType.Everyone,
                value="everyone",
                access_type=AccessType.Grant,
            )
        ],
        properties=Properties(
            additional_data={
                "title": source.title,
                "status": source.status,
                "lastModifiedDate": source.last_modified.isoformat(),
                "itemUrl": source.url,
                "iconUrl": source.icon_url or "",
            }
        ),
        content=ExternalItemContent(
            value=source.full_content,
            type=ExternalItemContentType.Text,
        ),
    )


def _compute_content_hash(item: SourceItem) -> str:
    """Compute a SHA-256 hash of item content for change detection."""
    combined = (
        f"{item.title}|{item.status}|{item.full_content}|{item.last_modified.isoformat()}"
    )
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
