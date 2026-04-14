# Item ingestion patterns: single items, content building, HTML, delete, and activities
# Prerequisites: pip install msgraph-sdk azure-identity

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
from msgraph.generated.models.external_connectors.external_activity import ExternalActivity
from msgraph.generated.models.external_connectors.external_activity_type import ExternalActivityType
from msgraph.generated.models.external_connectors.identity import Identity
from msgraph.generated.models.external_connectors.identity_type import IdentityType
from msgraph.generated.external.connections.item.items.item.microsoft_graph_external_connectors_add_activities.add_activities_post_request_body import (
    AddActivitiesPostRequestBody,
)


class ItemIngestion:
    """Manages item ingestion for a Copilot Connector."""

    def __init__(self, graph_client: GraphServiceClient, connection_id: str) -> None:
        self._graph_client = graph_client
        self._connection_id = connection_id

    async def ingest_simple_item(self) -> None:
        """Ingest a single item with text content and everyone ACL."""
        item = ExternalItem(
            id="TICKET-001",  # Must be URL-safe (no #, ?, &, /)
            acl=[
                Acl(
                    type=AclType.Everyone,
                    value="everyone",
                    access_type=AccessType.Grant,
                )
            ],
            properties=Properties(
                additional_data={
                    "ticketId": "TICKET-001",
                    "title": "Payment Gateway Timeout",
                    "status": "Open",
                    "priority": 1,
                    "assignedTo": "john.doe@contoso.com",
                    "createdDate": "2026-03-15T10:30:00Z",
                    "lastModifiedDate": "2026-03-20T14:15:00Z",
                    "itemUrl": "https://helpdesk.contoso.com/tickets/TICKET-001",
                    "iconUrl": "https://helpdesk.contoso.com/icons/ticket.png",
                    # StringCollection requires @odata.type annotation
                    "tags@odata.type": "Collection(Edm.String)",
                    "tags": ["payments", "infrastructure", "P1"],
                }
            ),
            content=ExternalItemContent(
                value=build_ticket_content(
                    title="Payment Gateway Timeout",
                    status="Open",
                    priority="P1",
                    assignee="John Doe",
                    description="Payment gateway returning 504 errors during peak hours.",
                    root_cause="Database connection pool exhaustion under load.",
                    resolution="Increased pool size from 100 to 250 connections.",
                ),
                type=ExternalItemContentType.Text,
            ),
        )

        # PUT is an upsert — creates or updates the item
        await self._graph_client.external.connections.by_external_connection_id(
            self._connection_id
        ).items.by_external_item_id("TICKET-001").put(item)

    async def ingest_html_item(self) -> None:
        """Ingest an item with HTML content (for rich documents)."""
        item = ExternalItem(
            id="WIKI-042",
            acl=[
                Acl(
                    type=AclType.Everyone,
                    value="everyone",
                    access_type=AccessType.Grant,
                )
            ],
            properties=Properties(
                additional_data={
                    "title": "VPN Setup Guide",
                    "itemUrl": "https://wiki.contoso.com/articles/vpn-setup",
                    "iconUrl": "https://wiki.contoso.com/icons/wiki.png",
                }
            ),
            content=ExternalItemContent(
                value=(
                    "<html><body>"
                    "<h1>VPN Setup Guide</h1>"
                    "<h2>Prerequisites</h2>"
                    "<ul>"
                    "<li>Windows 10/11 or macOS 12+</li>"
                    "<li>GlobalProtect client v6.1+</li>"
                    "</ul>"
                    "<h2>Installation Steps</h2>"
                    "<ol>"
                    "<li>Download GlobalProtect from the internal portal</li>"
                    "<li>Run the installer with admin privileges</li>"
                    "<li>Enter portal address: vpn.contoso.com</li>"
                    "</ol>"
                    "</body></html>"
                ),
                type=ExternalItemContentType.Html,
            ),
        )

        await self._graph_client.external.connections.by_external_connection_id(
            self._connection_id
        ).items.by_external_item_id("WIKI-042").put(item)

    async def delete_item(self, item_id: str) -> None:
        """Delete an item from the index."""
        await self._graph_client.external.connections.by_external_connection_id(
            self._connection_id
        ).items.by_external_item_id(item_id).delete()

    async def send_activity(self, item_id: str, user_entra_id: str) -> None:
        """
        Send user activities to boost item relevance.
        Supported types: created, modified, commented, viewed.
        Activities older than 7 days don't surface in the M365 app.
        """
        activity = ExternalActivity(
            odata_type="#microsoft.graph.externalConnectors.externalActivity",
            type=ExternalActivityType.Viewed,
            start_date_time=datetime.now(timezone.utc),
            performed_by=Identity(
                odata_type="#microsoft.graph.externalConnectors.identity",
                id=user_entra_id,
                type=IdentityType.User,
            ),
        )

        request_body = AddActivitiesPostRequestBody(activities=[activity])

        await self._graph_client.external.connections.by_external_connection_id(
            self._connection_id
        ).items.by_external_item_id(
            item_id
        ).microsoft_graph_external_connectors_add_activities.post(request_body)


def build_ticket_content(
    title: str,
    status: str,
    priority: str,
    assignee: str,
    description: str,
    root_cause: Optional[str] = None,
    resolution: Optional[str] = None,
    comments: Optional[list[tuple[str, str, str]]] = None,
) -> str:
    """
    Build rich, concatenated content from multiple source fields.
    Lead with the most important information for Copilot summarization.

    Args:
        title: Ticket title.
        status: Current ticket status.
        priority: Priority level (e.g. "P1").
        assignee: Person assigned to the ticket.
        description: Full ticket description.
        root_cause: Identified root cause (optional).
        resolution: Applied resolution (optional).
        comments: List of (author, date, text) tuples (optional).
    """
    lines: list[str] = [
        f"Title: {title}",
        f"Status: {status} | Priority: {priority}",
        f"Assigned to: {assignee}",
        "",
        f"Description: {description}",
    ]

    if root_cause:
        lines.append(f"\nRoot Cause: {root_cause}")

    if resolution:
        lines.append(f"\nResolution: {resolution}")

    if comments:
        lines.append("\nComments:")
        for author, date, text in comments:
            lines.append(f"  [{author} - {date}]: {text}")

    return "\n".join(lines)
