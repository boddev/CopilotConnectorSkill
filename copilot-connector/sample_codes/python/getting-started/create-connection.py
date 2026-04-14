# Complete Python example: Create a Copilot Connector end-to-end
# Prerequisites: pip install msgraph-sdk azure-identity
#
# Demonstrates: authenticate → create connection → register schema →
# poll schema status → ingest item → configure urlToItemResolver

import asyncio

from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.external_connectors.external_connection import ExternalConnection
from msgraph.generated.models.external_connectors.schema import Schema
from msgraph.generated.models.external_connectors.property_ import Property_
from msgraph.generated.models.external_connectors.property_type import PropertyType
from msgraph.generated.models.external_connectors.label import Label
from msgraph.generated.models.external_connectors.external_item import ExternalItem
from msgraph.generated.models.external_connectors.external_item_content import ExternalItemContent
from msgraph.generated.models.external_connectors.external_item_content_type import ExternalItemContentType
from msgraph.generated.models.external_connectors.acl import Acl
from msgraph.generated.models.external_connectors.acl_type import AclType
from msgraph.generated.models.external_connectors.access_type import AccessType
from msgraph.generated.models.external_connectors.properties import Properties
from msgraph.generated.models.external_connectors.connection_operation_status import ConnectionOperationStatus
from msgraph.generated.models.external_connectors.activity_settings import ActivitySettings
from msgraph.generated.models.external_connectors.item_id_resolver import ItemIdResolver
from msgraph.generated.models.external_connectors.url_match_info import UrlMatchInfo


async def main() -> None:
    # --- Step 1: Authenticate with Microsoft Graph ---
    credential = ClientSecretCredential(
        tenant_id="YOUR_TENANT_ID",
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
    )
    graph_client = GraphServiceClient(credential)

    # --- Step 2: Create the connection ---
    connection = ExternalConnection(
        id="contosohelpdesk",  # 3-128 alphanumeric chars, unique per tenant
        name="Contoso Helpdesk",
        description=(
            "Internal IT helpdesk tickets from the Contoso Helpdesk system. "
            "Contains incident reports, service requests, and change requests. "
            "Used by IT support staff and employees to track and resolve technical issues."
        ),
    )

    created_connection = await graph_client.external.connections.post(connection)
    print(f"Connection created: {created_connection.id}")

    # --- Step 3: Register the schema ---
    schema = Schema(
        base_type="microsoft.graph.externalItem",
        properties=[
            Property_(
                name="ticketId",
                type=PropertyType.String,
                is_queryable=True,
                is_retrievable=True,
                is_exact_match_required=True,
                aliases=["ID"],
            ),
            Property_(
                name="title",
                type=PropertyType.String,
                is_searchable=True,
                is_queryable=True,
                is_retrievable=True,
                labels=[Label.Title],
            ),
            Property_(
                name="status",
                type=PropertyType.String,
                is_queryable=True,
                is_retrievable=True,
                is_refinable=True,
                aliases=["state"],
            ),
            Property_(
                name="priority",
                type=PropertyType.Int64,
                is_queryable=True,
                is_retrievable=True,
                is_refinable=True,
            ),
            Property_(
                name="assignedTo",
                type=PropertyType.String,
                is_searchable=True,
                is_queryable=True,
                is_retrievable=True,
                aliases=["assignee", "owner"],
            ),
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
        ],
    )

    await graph_client.external.connections.by_external_connection_id(
        "contosohelpdesk"
    ).schema.patch(schema)

    # --- Step 3b: Poll until schema registration completes ---
    print("Schema registration started. Polling for completion...")
    while True:
        current_schema = (
            await graph_client.external.connections.by_external_connection_id(
                "contosohelpdesk"
            ).schema.get()
        )

        status = current_schema.status.state
        print(f"Schema status: {status}")

        if status == ConnectionOperationStatus.Completed:
            break

        if status == ConnectionOperationStatus.Failed:
            raise RuntimeError("Schema registration failed")

        await asyncio.sleep(30)

    # --- Step 4: Ingest items ---
    external_item = ExternalItem(
        id="TICKET-001",
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
                "title": "VPN Connection Drops After Windows Update",
                "status": "Open",
                "priority": 2,
                "assignedTo": "jane.smith@contoso.com",
                "createdDate": "2026-03-15T10:30:00Z",
                "lastModifiedDate": "2026-03-20T14:15:00Z",
                "itemUrl": "https://helpdesk.contoso.com/tickets/TICKET-001",
                "iconUrl": "https://helpdesk.contoso.com/icons/ticket.png",
            }
        ),
        content=ExternalItemContent(
            value=(
                "Title: VPN Connection Drops After Windows Update\n"
                "Status: Open | Priority: P2\n"
                "Assigned to: Jane Smith\n\n"
                "Description: Multiple users report VPN disconnections after installing "
                "KB5034441 Windows update. Affects GlobalProtect VPN client v6.1.\n\n"
                "Root Cause: Windows update modified network adapter settings, causing "
                "MTU mismatch with VPN tunnel configuration.\n\n"
                "Workaround: Reset network adapter MTU to 1400 via 'netsh interface ipv4 "
                'set subinterface "Ethernet" mtu=1400 store=persistent\''
            ),
            type=ExternalItemContentType.Text,
        ),
    )

    await graph_client.external.connections.by_external_connection_id(
        "contosohelpdesk"
    ).items.by_external_item_id("TICKET-001").put(external_item)

    print("Item ingested successfully!")

    # --- Step 5: Configure urlToItemResolver ---
    resolver = ItemIdResolver(
        url_match_info=UrlMatchInfo(
            base_urls=["https://helpdesk.contoso.com"],
            url_pattern="/tickets/(?<itemId>[A-Za-z0-9-]+)",
        )
    )

    activity_settings = ActivitySettings(url_to_item_resolvers=[resolver])

    await graph_client.external.connections.by_external_connection_id(
        "contosohelpdesk"
    ).patch(ExternalConnection(activity_settings=activity_settings))

    print("Connector setup complete!")
    print(
        "Next: Enable inline results in M365 Admin Center > "
        "Search & intelligence > Verticals"
    )


if __name__ == "__main__":
    asyncio.run(main())
