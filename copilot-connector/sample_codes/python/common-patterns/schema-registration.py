# Schema registration with status polling
# Shows all property types, attributes, semantic labels, and aliases
# Prerequisites: pip install msgraph-sdk azure-identity

import asyncio
from datetime import datetime, timedelta

from msgraph import GraphServiceClient
from msgraph.generated.models.external_connectors.schema import Schema
from msgraph.generated.models.external_connectors.property_ import Property_
from msgraph.generated.models.external_connectors.property_type import PropertyType
from msgraph.generated.models.external_connectors.label import Label
from msgraph.generated.models.external_connectors.connection_operation_status import ConnectionOperationStatus


class SchemaRegistration:
    """Manages schema registration and polling for a Copilot Connector."""

    def __init__(self, graph_client: GraphServiceClient, connection_id: str) -> None:
        self._graph_client = graph_client
        self._connection_id = connection_id

    async def register_schema(self) -> None:
        """Register a schema with all supported property types and attributes."""
        schema = Schema(
            base_type="microsoft.graph.externalItem",
            properties=[
                # Searchable + Queryable + Retrievable — for full-text and filtered search
                Property_(
                    name="title",
                    type=PropertyType.String,
                    is_searchable=True,
                    is_queryable=True,
                    is_retrievable=True,
                    labels=[Label.Title],
                ),
                # Searchable text (but NOT refinable — they are mutually exclusive)
                Property_(
                    name="description",
                    type=PropertyType.String,
                    is_searchable=True,
                    is_queryable=False,
                    is_retrievable=False,
                ),
                # Refinable (but NOT searchable — mutually exclusive)
                # Must be set in initial schema — cannot add refinable via update
                Property_(
                    name="status",
                    type=PropertyType.String,
                    is_searchable=False,
                    is_queryable=True,
                    is_retrievable=True,
                    is_refinable=True,
                    aliases=["state"],
                ),
                # Numeric refinable property
                Property_(
                    name="priority",
                    type=PropertyType.Int64,
                    is_queryable=True,
                    is_retrievable=True,
                    is_refinable=True,
                ),
                # ExactMatchRequired — only on non-searchable properties
                Property_(
                    name="ticketId",
                    type=PropertyType.String,
                    is_searchable=False,
                    is_queryable=True,
                    is_retrievable=True,
                    is_exact_match_required=True,
                    aliases=["ID", "incidentNumber"],
                ),
                # StringCollection with refinable + exact match
                Property_(
                    name="tags",
                    type=PropertyType.StringCollection,
                    is_queryable=True,
                    is_retrievable=True,
                    is_refinable=True,
                    is_exact_match_required=True,
                    aliases=["labels", "categories"],
                ),
                # DateTime properties with semantic labels
                Property_(
                    name="createdDate",
                    type=PropertyType.DateTime,
                    is_queryable=True,
                    is_retrievable=True,
                    is_refinable=True,
                    labels=[Label.CreatedDateTime],
                ),
                Property_(
                    name="lastModifiedDate",
                    type=PropertyType.DateTime,
                    is_queryable=True,
                    is_retrievable=True,
                    labels=[Label.LastModifiedDateTime],
                ),
                # URL and icon — critical for Copilot surfacing
                Property_(
                    name="itemUrl",
                    type=PropertyType.String,
                    is_retrievable=True,
                    labels=[Label.Url],
                ),
                Property_(
                    name="iconUrl",
                    type=PropertyType.String,
                    is_retrievable=True,
                    labels=[Label.IconUrl],
                ),
                # Boolean property
                Property_(
                    name="isResolved",
                    type=PropertyType.Boolean,
                    is_queryable=True,
                    is_retrievable=True,
                ),
                # Double property
                Property_(
                    name="estimatedHours",
                    type=PropertyType.Double,
                    is_queryable=True,
                    is_retrievable=True,
                ),
            ],
        )

        # Schema registration is async — returns 202 Accepted
        await self._graph_client.external.connections.by_external_connection_id(
            self._connection_id
        ).schema.patch(schema)

        print("Schema registration started.")

    async def wait_for_schema(self, timeout_minutes: float = 15.0) -> bool:
        """
        Poll schema status until completed or failed.
        Schema registration can take up to 10 minutes.

        Returns:
            True if schema registration completed successfully.
        """
        deadline = datetime.utcnow() + timedelta(minutes=timeout_minutes)

        while datetime.utcnow() < deadline:
            schema = (
                await self._graph_client.external.connections.by_external_connection_id(
                    self._connection_id
                ).schema.get()
            )

            status = schema.status.state
            print(f"  Schema status: {status}")

            if status == ConnectionOperationStatus.Completed:
                return True

            if status == ConnectionOperationStatus.Failed:
                print("Schema registration failed.", flush=True)
                return False

            await asyncio.sleep(30)

        raise TimeoutError("Schema registration timed out")
