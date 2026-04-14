// ACL configuration patterns: user, group, everyone, external groups, deny
//
// Prerequisites: npm install @microsoft/microsoft-graph-client @azure/identity

import { Client } from "@microsoft/microsoft-graph-client";

/** ACL entry controlling who can see an item. */
interface AclEntry {
  type: "everyone" | "everyoneExceptGuests" | "user" | "group" | "externalGroup";
  value: string;
  accessType: "grant" | "deny";
}

/** An external group definition. */
interface ExternalGroup {
  id: string;
  displayName: string;
  description?: string;
}

/**
 * Provides ACL configuration helpers and external group management
 * for Microsoft Graph external connections.
 */
class AclConfiguration {
  constructor(
    private readonly graphClient: Client,
    private readonly connectionId: string
  ) {}

  // --- ACL Builders ---

  /** Public item visible to all tenant users. */
  publicAcl(): AclEntry[] {
    return [
      {
        type: "everyone",
        value: "everyone",
        accessType: "grant",
      },
    ];
  }

  /** Public item visible to all tenant users except guests. */
  internalOnlyAcl(): AclEntry[] {
    return [
      {
        type: "everyoneExceptGuests",
        value: "everyoneExceptGuests",
        accessType: "grant",
      },
    ];
  }

  /**
   * Item restricted to specific Entra ID users.
   * Values MUST be Entra object IDs (GUIDs), not emails or UPNs.
   */
  userRestrictedAcl(...userEntraIds: string[]): AclEntry[] {
    return userEntraIds.map((id) => ({
      type: "user" as const,
      value: id,
      accessType: "grant" as const,
    }));
  }

  /**
   * Item restricted to members of specific Entra ID groups.
   * Prefer group-based ACLs over user-based for maintainability.
   */
  groupRestrictedAcl(...groupEntraIds: string[]): AclEntry[] {
    return groupEntraIds.map((id) => ({
      type: "group" as const,
      value: id,
      accessType: "grant" as const,
    }));
  }

  /**
   * Combination: grant to all, deny to specific users.
   * Deny ALWAYS overrides grant.
   */
  everyoneExceptAcl(...deniedUserIds: string[]): AclEntry[] {
    const acl: AclEntry[] = [
      {
        type: "everyone",
        value: "everyone",
        accessType: "grant",
      },
    ];

    for (const id of deniedUserIds) {
      acl.push({
        type: "user",
        value: id,
        accessType: "deny",
      });
    }

    return acl;
  }

  /**
   * Item restricted to an external group (for non-Entra ID permissions).
   * External groups must be created first via the group sync API.
   */
  externalGroupAcl(externalGroupId: string): AclEntry[] {
    return [
      {
        type: "externalGroup",
        value: externalGroupId,
        accessType: "grant",
      },
    ];
  }

  // --- External Group Management ---

  /**
   * Create an external group for non-Entra ID permission structures.
   * Use for Salesforce roles, ServiceNow groups, custom RBAC, etc.
   */
  async createExternalGroup(
    groupId: string,
    displayName: string,
    description?: string
  ): Promise<ExternalGroup> {
    const group = await this.graphClient
      .api(`/external/connections/${this.connectionId}/groups`)
      .post({
        id: groupId,
        displayName,
        description,
      });

    return group as ExternalGroup;
  }

  /**
   * Add an Entra ID user to an external group.
   */
  async addUserToExternalGroup(
    groupId: string,
    userEntraId: string
  ): Promise<void> {
    await this.graphClient
      .api(
        `/external/connections/${this.connectionId}/groups/${groupId}/members`
      )
      .post({
        "@odata.type": "#microsoft.graph.externalConnectors.identity",
        id: userEntraId,
        type: "user",
      });
  }

  /**
   * Add an Entra ID group to an external group (nested groups).
   */
  async addGroupToExternalGroup(
    externalGroupId: string,
    entraGroupId: string
  ): Promise<void> {
    await this.graphClient
      .api(
        `/external/connections/${this.connectionId}/groups/${externalGroupId}/members`
      )
      .post({
        "@odata.type": "#microsoft.graph.externalConnectors.identity",
        id: entraGroupId,
        type: "group",
      });
  }
}

export { AclConfiguration, AclEntry, ExternalGroup };
