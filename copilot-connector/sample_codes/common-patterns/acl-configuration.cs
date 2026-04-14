// ACL configuration patterns: user, group, everyone, external groups, deny
using Microsoft.Graph;
using Microsoft.Graph.Models.ExternalConnectors;

public class AclConfiguration
{
    private readonly GraphServiceClient _graphClient;
    private readonly string _connectionId;

    public AclConfiguration(GraphServiceClient graphClient, string connectionId)
    {
        _graphClient = graphClient;
        _connectionId = connectionId;
    }

    /// <summary>
    /// Public item visible to all tenant users.
    /// </summary>
    public List<AclEntry> PublicAcl() => new()
    {
        new AclEntry
        {
            Type = AclType.Everyone,
            Value = "everyone",
            AccessType = AccessType.Grant
        }
    };

    /// <summary>
    /// Public item visible to all tenant users except guests.
    /// </summary>
    public List<AclEntry> InternalOnlyAcl() => new()
    {
        new AclEntry
        {
            Type = AclType.EveryoneExceptGuests,
            Value = "everyoneExceptGuests",
            AccessType = AccessType.Grant
        }
    };

    /// <summary>
    /// Item restricted to specific Entra ID users.
    /// Values MUST be Entra object IDs (GUIDs), not emails or UPNs.
    /// </summary>
    public List<AclEntry> UserRestrictedAcl(params string[] userEntraIds) =>
        userEntraIds.Select(id => new AclEntry
        {
            Type = AclType.User,
            Value = id,
            AccessType = AccessType.Grant
        }).ToList();

    /// <summary>
    /// Item restricted to members of specific Entra ID groups.
    /// Prefer group-based ACLs over user-based for maintainability.
    /// </summary>
    public List<AclEntry> GroupRestrictedAcl(params string[] groupEntraIds) =>
        groupEntraIds.Select(id => new AclEntry
        {
            Type = AclType.Group,
            Value = id,
            AccessType = AccessType.Grant
        }).ToList();

    /// <summary>
    /// Combination: grant to all, deny to specific users.
    /// Deny ALWAYS overrides grant.
    /// </summary>
    public List<AclEntry> EveryoneExceptAcl(params string[] deniedUserIds)
    {
        var acl = new List<AclEntry>
        {
            new AclEntry
            {
                Type = AclType.Everyone,
                Value = "everyone",
                AccessType = AccessType.Grant
            }
        };

        acl.AddRange(deniedUserIds.Select(id => new AclEntry
        {
            Type = AclType.User,
            Value = id,
            AccessType = AccessType.Deny
        }));

        return acl;
    }

    /// <summary>
    /// Item restricted to an external group (for non-Entra ID permissions).
    /// External groups must be created first via the group sync API.
    /// </summary>
    public List<AclEntry> ExternalGroupAcl(string externalGroupId) => new()
    {
        new AclEntry
        {
            Type = AclType.ExternalGroup,
            Value = externalGroupId,
            AccessType = AccessType.Grant
        }
    };

    // --- External Group Management ---

    /// <summary>
    /// Create an external group for non-Entra ID permission structures.
    /// Use for Salesforce roles, ServiceNow groups, custom RBAC, etc.
    /// </summary>
    public async Task<ExternalGroup> CreateExternalGroupAsync(
        string groupId, string displayName, string? description = null)
    {
        var group = new ExternalGroup
        {
            Id = groupId,
            DisplayName = displayName,
            Description = description
        };

        return await _graphClient.External.Connections[_connectionId]
            .Groups
            .PostAsync(group) ?? throw new Exception("Failed to create external group");
    }

    /// <summary>
    /// Add an Entra ID user to an external group.
    /// </summary>
    public async Task AddUserToExternalGroupAsync(
        string groupId, string userEntraId)
    {
        var member = new Identity
        {
            OdataType = "#microsoft.graph.externalConnectors.identity",
            Id = userEntraId,
            Type = IdentityType.User
        };

        await _graphClient.External.Connections[_connectionId]
            .Groups[groupId]
            .Members
            .PostAsync(member);
    }

    /// <summary>
    /// Add an Entra ID group to an external group (nested groups).
    /// </summary>
    public async Task AddGroupToExternalGroupAsync(
        string externalGroupId, string entraGroupId)
    {
        var member = new Identity
        {
            OdataType = "#microsoft.graph.externalConnectors.identity",
            Id = entraGroupId,
            Type = IdentityType.Group
        };

        await _graphClient.External.Connections[_connectionId]
            .Groups[externalGroupId]
            .Members
            .PostAsync(member);
    }
}
