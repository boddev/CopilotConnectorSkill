// ACL configuration patterns: user, group, everyone, external groups, deny
//
// Prerequisites:
//   Maven: com.microsoft.graph:microsoft-graph:6.x, com.azure:azure-identity:1.x
//   Gradle: implementation 'com.microsoft.graph:microsoft-graph:6.+'
//           implementation 'com.azure:azure-identity:1.+'

import com.microsoft.graph.GraphServiceClient;
import com.microsoft.graph.models.externalconnectors.*;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Demonstrates all ACL patterns for Copilot Connector items.
 * Covers public, internal-only, user-restricted, group-restricted,
 * everyone-except (deny), external group ACLs, and external group management.
 */
public class AclConfiguration {

    private final GraphServiceClient graphClient;
    private final String connectionId;

    public AclConfiguration(GraphServiceClient graphClient, String connectionId) {
        this.graphClient = graphClient;
        this.connectionId = connectionId;
    }

    /**
     * Public item visible to all tenant users.
     */
    public List<Acl> publicAcl() {
        Acl acl = new Acl();
        acl.setType(AclType.Everyone);
        acl.setValue("everyone");
        acl.setAccessType(AccessType.Grant);
        return List.of(acl);
    }

    /**
     * Internal item visible to all tenant users except guests.
     */
    public List<Acl> internalOnlyAcl() {
        Acl acl = new Acl();
        acl.setType(AclType.EveryoneExceptGuests);
        acl.setValue("everyoneExceptGuests");
        acl.setAccessType(AccessType.Grant);
        return List.of(acl);
    }

    /**
     * Item restricted to specific Entra ID users.
     * Values MUST be Entra object IDs (GUIDs), not emails or UPNs.
     *
     * @param userEntraIds one or more Entra ID user GUIDs
     */
    public List<Acl> userRestrictedAcl(String... userEntraIds) {
        return Arrays.stream(userEntraIds)
                .map(id -> {
                    Acl acl = new Acl();
                    acl.setType(AclType.User);
                    acl.setValue(id);
                    acl.setAccessType(AccessType.Grant);
                    return acl;
                })
                .collect(Collectors.toList());
    }

    /**
     * Item restricted to members of specific Entra ID groups.
     * Prefer group-based ACLs over user-based for maintainability.
     *
     * @param groupEntraIds one or more Entra ID group GUIDs
     */
    public List<Acl> groupRestrictedAcl(String... groupEntraIds) {
        return Arrays.stream(groupEntraIds)
                .map(id -> {
                    Acl acl = new Acl();
                    acl.setType(AclType.Group);
                    acl.setValue(id);
                    acl.setAccessType(AccessType.Grant);
                    return acl;
                })
                .collect(Collectors.toList());
    }

    /**
     * Combination: grant to all, deny to specific users.
     * Deny ALWAYS overrides grant.
     *
     * @param deniedUserIds Entra ID GUIDs of users to deny
     */
    public List<Acl> everyoneExceptAcl(String... deniedUserIds) {
        var aclList = new ArrayList<Acl>();

        Acl grantAll = new Acl();
        grantAll.setType(AclType.Everyone);
        grantAll.setValue("everyone");
        grantAll.setAccessType(AccessType.Grant);
        aclList.add(grantAll);

        for (String id : deniedUserIds) {
            Acl deny = new Acl();
            deny.setType(AclType.User);
            deny.setValue(id);
            deny.setAccessType(AccessType.Deny);
            aclList.add(deny);
        }

        return aclList;
    }

    /**
     * Item restricted to an external group (for non-Entra ID permissions).
     * External groups must be created first via the group sync API.
     *
     * @param externalGroupId the external group ID
     */
    public List<Acl> externalGroupAcl(String externalGroupId) {
        Acl acl = new Acl();
        acl.setType(AclType.ExternalGroup);
        acl.setValue(externalGroupId);
        acl.setAccessType(AccessType.Grant);
        return List.of(acl);
    }

    // --- External Group Management ---

    /**
     * Create an external group for non-Entra ID permission structures.
     * Use for Salesforce roles, ServiceNow groups, custom RBAC, etc.
     *
     * @param groupId     unique ID for the external group
     * @param displayName human-readable name
     * @param description optional description
     * @return the created external group
     */
    public ExternalGroup createExternalGroup(
            String groupId, String displayName, String description) {

        ExternalGroup group = new ExternalGroup();
        group.setId(groupId);
        group.setDisplayName(displayName);
        group.setDescription(description);

        ExternalGroup created = graphClient.external().connections()
                .byExternalConnectionId(connectionId)
                .groups()
                .post(group);

        if (created == null) {
            throw new RuntimeException("Failed to create external group");
        }
        return created;
    }

    /**
     * Add an Entra ID user to an external group.
     *
     * @param groupId     the external group ID
     * @param userEntraId the Entra ID (GUID) of the user
     */
    public void addUserToExternalGroup(String groupId, String userEntraId) {
        Identity member = new Identity();
        member.setOdataType("#microsoft.graph.externalConnectors.identity");
        member.setId(userEntraId);
        member.setType(IdentityType.User);

        graphClient.external().connections()
                .byExternalConnectionId(connectionId)
                .groups()
                .byExternalGroupId(groupId)
                .members()
                .post(member);
    }

    /**
     * Add an Entra ID group to an external group (nested groups).
     *
     * @param externalGroupId the external group ID
     * @param entraGroupId    the Entra ID (GUID) of the group to add
     */
    public void addGroupToExternalGroup(String externalGroupId, String entraGroupId) {
        Identity member = new Identity();
        member.setOdataType("#microsoft.graph.externalConnectors.identity");
        member.setId(entraGroupId);
        member.setType(IdentityType.Group);

        graphClient.external().connections()
                .byExternalConnectionId(connectionId)
                .groups()
                .byExternalGroupId(externalGroupId)
                .members()
                .post(member);
    }
}
