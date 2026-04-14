# ACL configuration patterns: user, group, everyone, external groups, deny
# Prerequisites: pip install msgraph-sdk azure-identity

from msgraph import GraphServiceClient
from msgraph.generated.models.external_connectors.acl import Acl
from msgraph.generated.models.external_connectors.acl_type import AclType
from msgraph.generated.models.external_connectors.access_type import AccessType
from msgraph.generated.models.external_connectors.external_group import ExternalGroup
from msgraph.generated.models.external_connectors.identity import Identity
from msgraph.generated.models.external_connectors.identity_type import IdentityType


class AclConfiguration:
    """ACL configuration patterns for Copilot Connector items."""

    def __init__(self, graph_client: GraphServiceClient, connection_id: str) -> None:
        self._graph_client = graph_client
        self._connection_id = connection_id

    # --- ACL Patterns ---

    @staticmethod
    def public_acl() -> list[Acl]:
        """Public item visible to all tenant users."""
        return [
            Acl(
                type=AclType.Everyone,
                value="everyone",
                access_type=AccessType.Grant,
            )
        ]

    @staticmethod
    def internal_only_acl() -> list[Acl]:
        """Public item visible to all tenant users except guests."""
        return [
            Acl(
                type=AclType.EveryoneExceptGuests,
                value="everyoneExceptGuests",
                access_type=AccessType.Grant,
            )
        ]

    @staticmethod
    def user_restricted_acl(*user_entra_ids: str) -> list[Acl]:
        """
        Item restricted to specific Entra ID users.
        Values MUST be Entra object IDs (GUIDs), not emails or UPNs.
        """
        return [
            Acl(
                type=AclType.User,
                value=user_id,
                access_type=AccessType.Grant,
            )
            for user_id in user_entra_ids
        ]

    @staticmethod
    def group_restricted_acl(*group_entra_ids: str) -> list[Acl]:
        """
        Item restricted to members of specific Entra ID groups.
        Prefer group-based ACLs over user-based for maintainability.
        """
        return [
            Acl(
                type=AclType.Group,
                value=group_id,
                access_type=AccessType.Grant,
            )
            for group_id in group_entra_ids
        ]

    @staticmethod
    def everyone_except_acl(*denied_user_ids: str) -> list[Acl]:
        """
        Combination: grant to all, deny to specific users.
        Deny ALWAYS overrides grant.
        """
        acl: list[Acl] = [
            Acl(
                type=AclType.Everyone,
                value="everyone",
                access_type=AccessType.Grant,
            )
        ]

        acl.extend(
            Acl(
                type=AclType.User,
                value=user_id,
                access_type=AccessType.Deny,
            )
            for user_id in denied_user_ids
        )

        return acl

    @staticmethod
    def external_group_acl(external_group_id: str) -> list[Acl]:
        """
        Item restricted to an external group (for non-Entra ID permissions).
        External groups must be created first via the group sync API.
        """
        return [
            Acl(
                type=AclType.ExternalGroup,
                value=external_group_id,
                access_type=AccessType.Grant,
            )
        ]

    # --- External Group Management ---

    async def create_external_group(
        self,
        group_id: str,
        display_name: str,
        description: str | None = None,
    ) -> ExternalGroup:
        """
        Create an external group for non-Entra ID permission structures.
        Use for Salesforce roles, ServiceNow groups, custom RBAC, etc.
        """
        group = ExternalGroup(
            id=group_id,
            display_name=display_name,
            description=description,
        )

        result = await self._graph_client.external.connections.by_external_connection_id(
            self._connection_id
        ).groups.post(group)

        if result is None:
            raise RuntimeError("Failed to create external group")
        return result

    async def add_user_to_external_group(
        self, group_id: str, user_entra_id: str
    ) -> None:
        """Add an Entra ID user to an external group."""
        member = Identity(
            odata_type="#microsoft.graph.externalConnectors.identity",
            id=user_entra_id,
            type=IdentityType.User,
        )

        await self._graph_client.external.connections.by_external_connection_id(
            self._connection_id
        ).groups.by_external_group_id(group_id).members.post(member)

    async def add_group_to_external_group(
        self, external_group_id: str, entra_group_id: str
    ) -> None:
        """Add an Entra ID group to an external group (nested groups)."""
        member = Identity(
            odata_type="#microsoft.graph.externalConnectors.identity",
            id=entra_group_id,
            type=IdentityType.Group,
        )

        await self._graph_client.external.connections.by_external_connection_id(
            self._connection_id
        ).groups.by_external_group_id(external_group_id).members.post(member)
