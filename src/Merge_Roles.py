# =============================================================================
# Genesys Cloud - Merge Permissions From One or More Roles Into a Target Role
# =============================================================================
# Reads the permissions on one or more source roles and merges them into a
# target role. The target role keeps every permission it already has and gains
# any permissions the source roles add. This is handy when you are combining
# roles and want the target role to end up with the permissions from all of
# them, not just a copy of one.
#
# This script used to overwrite the target role, so the target lost its own
# permissions. It now merges instead: it starts from the target's current
# permissions and adds the source permissions on top, so nothing the target
# already had is dropped.
#
# Fill in SOURCE_ROLE_IDS (a list of one or more roles to copy FROM) and
# TARGET_ROLE_ID (the one role to merge INTO) before you run it.
#
# Safety: DRY_RUN is True by default. In dry-run mode the script only reads the
# roles and prints what it would add to the target. It makes no changes until
# you set DRY_RUN to False. Please note: when DRY_RUN is False this updates the
# target role, so double-check the IDs before you turn it off. The source roles
# are never changed.
#
# Local runs need `pip install -r requirements.txt` and a populated .env with
# GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET.
#
# Related script: Role_Removal.py removes duplicate users from an old role after
# a role change.
# =============================================================================

# --- Imports -----------------------------------------------------------------

import os
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
from dotenv import load_dotenv


# --- Configuration -----------------------------------------------------------

# Source role IDs. Each of these roles is read and its permissions are merged
# into the target role. You can list one role or several. The source roles are
# never changed. The order does not matter, because merging combines everything.
SOURCE_ROLE_IDS = [
    '57d27899-8f78-44e2-b959-1a081d4ddc47',  # merge permissions FROM this role
    # Add more source role IDs here, one per line, to merge several roles at once.
]

# The one role we merge everything into. This role is changed: it keeps its own
# permissions and gains the permissions from every source role above.
TARGET_ROLE_ID = '84f1296f-2ced-47e8-9c5d-8c98ba62659d'  # merge permissions INTO this role

# When True, perform reads only and print the intended change without applying
# it. Set to False only once you are sure the IDs above are correct.
DRY_RUN = False


# --- Setup -------------------------------------------------------------------

def build_apis():
    """Sign in to Genesys Cloud and return the Authorization API client.

    Reads GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET from the .env
    file at the workspace root (one folder up from this script). Stops the
    script with a helpful message if either value is missing.
    """
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
    client_id = os.environ.get('GENESYS_CLOUD_CLIENT_ID')
    client_secret = os.environ.get('GENESYS_CLOUD_CLIENT_SECRET')
    if not client_id or not client_secret:
        raise SystemExit(
            "Missing Genesys Cloud credentials. Copy .env.example to .env and set "
            "GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET."
        )

    apiclient = PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(
        client_id, client_secret
    )
    return PureCloudPlatformClientV2.AuthorizationApi(apiclient)


# --- Helpers -----------------------------------------------------------------

def get_role_with_permissions(auth_api, role_id):
    """Return a single role, with its permission policies filled in.

    We pass expand=['permissionPolicies'] so Genesys includes the role's full
    permission list in the response. Without it the policies come back empty and
    there would be nothing to merge. Stops the script if the read fails.
    """
    try:
        return auth_api.get_authorization_role(role_id, expand=['permissionPolicies'])
    except ApiException as e:
        raise SystemExit("Failed to read role %s: %s" % (role_id, e))


def policy_key(policy):
    """Return the key that identifies which permission a policy is about.

    Two policies describe the same permission when they share the same domain
    and entity name (for example, the "directory" domain and the "user" entity).
    We use that pair as the key so we can spot when a source role and the target
    role both set the same permission and need to be combined.
    """
    return (getattr(policy, 'domain', None), getattr(policy, 'entity_name', None))


def union_keep_order(first_list, second_list):
    """Return one list with the items from both lists and no duplicates.

    Keeps the items from the first list in their original order, then adds any
    items from the second list that were not already there. We use this to
    combine the action sets and named resources from two policies without
    losing any and without listing the same one twice.
    """
    combined = list(first_list or [])
    for item in (second_list or []):
        if item not in combined:
            combined.append(item)
    return combined


def merge_two_policies(target_policy, source_policy):
    """Add the source policy's actions and resources into the target policy.

    Both policies are about the same domain and entity. This grows the target
    policy so it allows everything either policy allowed: the actions are
    combined and the named resources are combined, with no duplicates. The
    target policy is changed in place and returned.
    """
    target_policy.action_set = union_keep_order(
        getattr(target_policy, 'action_set', None),
        getattr(source_policy, 'action_set', None),
    )
    target_policy.named_resources = union_keep_order(
        getattr(target_policy, 'named_resources', None),
        getattr(source_policy, 'named_resources', None),
    )
    return target_policy


def merge_source_policies_into(merged_by_key, source_role):
    """Merge one source role's permission policies into the running result.

    The running result is a dictionary keyed by domain and entity name. For each
    policy on the source role, if the result already has a policy for the same
    domain and entity, we combine the two so the target keeps and gains every
    action and resource. If it is a brand new permission, we add it as-is.
    Changes the dictionary in place.
    """
    for source_policy in (source_role.permission_policies or []):
        key = policy_key(source_policy)
        if key in merged_by_key:
            merge_two_policies(merged_by_key[key], source_policy)
        else:
            merged_by_key[key] = source_policy


def build_merged_policies(target_role, source_roles):
    """Return the full permission list for the target after merging in sources.

    Starts from the target role's own permissions so nothing it already has is
    lost. Then merges in the permissions from every source role, combining any
    that cover the same domain and entity. Returns the merged list of policies,
    ready to save back onto the target role.
    """
    # Start the result with the target's own policies, keyed by domain and
    # entity so we can find and combine matching source policies quickly.
    merged_by_key = {}
    for target_policy in (target_role.permission_policies or []):
        merged_by_key[policy_key(target_policy)] = target_policy

    for source_role in source_roles:
        merge_source_policies_into(merged_by_key, source_role)

    return list(merged_by_key.values())


def merge_permissions_into_target(auth_api, source_roles, target_role):
    """Merge the source roles' permissions into the target role.

    This changes the target role. It keeps the target's own permission policies
    and adds the ones from every source role, combining any that cover the same
    domain and entity. The target role keeps its own name and description, so
    only the permissions change. Does nothing (just prints) while DRY_RUN is
    True.
    """
    for source_role in source_roles:
        count = len(source_role.permission_policies or [])
        print("Source role '%s' has %d permission policy(ies)." % (source_role.name, count))

    before_count = len(target_role.permission_policies or [])
    merged_policies = build_merged_policies(target_role, source_roles)
    after_count = len(merged_policies)
    print("Target role '%s' has %d permission policy(ies) now and will have %d after the merge."
          % (target_role.name, before_count, after_count))

    if DRY_RUN:
        print("\n[DRY-RUN] Would save these merged permission policies onto the target role:")
        pprint(merged_policies)
        return

    # The SDK's put_authorization_role wants a DomainOrganizationRole body. We
    # start from the TARGET role so we keep its own name and description, then
    # set its permission policies to the merged list. Genesys rejects a save
    # that renames the target to a name another role already uses, so it is
    # important the name stays the target's own.
    target_role.permission_policies = merged_policies
    try:
        auth_api.put_authorization_role(TARGET_ROLE_ID, target_role)
        print("\nMerged permissions saved. The target role now has %d permission policy(ies)."
              % after_count)
    except ApiException as e:
        raise SystemExit("Failed to update the target role: %s" % e)


# --- Main --------------------------------------------------------------------

def main():
    if not SOURCE_ROLE_IDS or not TARGET_ROLE_ID:
        raise SystemExit(
            "Set SOURCE_ROLE_IDS (a list of one or more role IDs) and "
            "TARGET_ROLE_ID at the top of this script before running it."
        )

    # The target must not also be listed as a source. Merging a role into itself
    # would do nothing useful and is almost always a copy-and-paste mistake, so
    # we stop and point it out rather than run anyway.
    if TARGET_ROLE_ID in SOURCE_ROLE_IDS:
        raise SystemExit(
            "TARGET_ROLE_ID also appears in SOURCE_ROLE_IDS. Remove it from the "
            "source list so the target is only merged into, not from itself."
        )

    auth_api = build_apis()

    # Read every source role (for its permissions) and the target role (so we
    # can keep its own name and description, and its current permissions, when
    # we save it back).
    source_roles = []
    for source_role_id in SOURCE_ROLE_IDS:
        source_roles.append(get_role_with_permissions(auth_api, source_role_id))
    target_role = get_role_with_permissions(auth_api, TARGET_ROLE_ID)

    merge_permissions_into_target(auth_api, source_roles, target_role)


if __name__ == '__main__':
    main()
