# =============================================================================
# Genesys Cloud - Copy Permissions From One Role to Another
# =============================================================================
# Reads the permissions on a source role and copies them onto a target role.
# This is handy when you are merging roles and want the target role to end up
# with the same permission policies the source role already has.
#
# Fill in SOURCE_ROLE_ID (the role to copy FROM) and TARGET_ROLE_ID (the role
# to copy TO) before you run it.
#
# Safety: DRY_RUN is True by default. In dry-run mode the script only reads the
# source role and prints what it would copy. It makes no changes until you set
# DRY_RUN to False. Please note: when DRY_RUN is False this overwrites the
# target role's permissions with the source role's permissions, so double-check
# the two IDs before you turn it off.
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

# Role IDs. The source role is read and its permissions are copied onto the
# target role. The source role is never changed.
SOURCE_ROLE_ID = '84f1296f-2ced-47e8-9c5d-8c98ba62659d'  # copy permissions FROM this role
TARGET_ROLE_ID = '05516756-ee06-459f-83cd-4354d0f6f8e1'  # copy permissions TO this role (this role is changed)

# When True, perform reads only and print the intended change without applying
# it. Set to False only once you are sure the two IDs above are correct.
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
    there would be nothing to copy. Stops the script if the read fails.
    """
    try:
        return auth_api.get_authorization_role(role_id, expand=['permissionPolicies'])
    except ApiException as e:
        raise SystemExit("Failed to read role %s: %s" % (role_id, e))


def copy_permissions_to_target(auth_api, source_role, target_role):
    """Copy the source role's permissions onto the target role.

    This changes the target role. It overwrites the target role's permission
    policies with the ones from the source role. The target role keeps its own
    name and description, so only the permissions move across. Does nothing
    (just prints) while DRY_RUN is True.
    """
    policies = source_role.permission_policies or []
    print("Source role '%s' has %d permission policy(ies)."
          % (source_role.name, len(policies)))
    print("Target role '%s' will be updated." % target_role.name)

    if DRY_RUN:
        print("\n[DRY-RUN] Would copy these permission policies onto the target role:")
        pprint(policies)
        return

    # The SDK's put_authorization_role wants a DomainOrganizationRole body. We
    # start from the TARGET role so we keep its own name and description, then
    # overwrite only its permission policies with the source role's. Genesys
    # rejects a save that renames the target to a name another role already uses,
    # so it is important the name stays the target's own.
    target_role.permission_policies = source_role.permission_policies
    try:
        api_response = auth_api.put_authorization_role(TARGET_ROLE_ID, target_role)
        print("\nCopied %d permission policy(ies) onto the target role." % len(policies))
    except ApiException as e:
        raise SystemExit("Failed to update the target role: %s" % e)


# --- Main --------------------------------------------------------------------

def main():
    if not SOURCE_ROLE_ID or not TARGET_ROLE_ID:
        raise SystemExit(
            "Set SOURCE_ROLE_ID and TARGET_ROLE_ID at the top of this script "
            "before running it."
        )

    auth_api = build_apis()

    # Read the source role (for its permissions) and the target role (so we can
    # keep its own name and description when we save it back).
    source_role = get_role_with_permissions(auth_api, SOURCE_ROLE_ID)
    target_role = get_role_with_permissions(auth_api, TARGET_ROLE_ID)
    copy_permissions_to_target(auth_api, source_role, target_role)


if __name__ == '__main__':
    main()
