# =============================================================================
# Genesys Cloud - Remove Duplicate Users From an Old Role
# =============================================================================
# Finds users who are in BOTH an old role and a new role, then removes those
# duplicate users from the old role only. The users keep the new role. This is
# handy after a role change, when some people ended up in both roles.
#
# Safety: DRY_RUN is True by default. In dry-run mode the script only reads data
# and prints what it would change. It makes no changes until you set DRY_RUN to
# False. Fill in old_role_id and new_role_id before you run it.
#
# Local runs need `pip install -r requirements.txt` and a populated .env with
# GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET.
# =============================================================================

import os
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
from dotenv import load_dotenv


# --- Configuration ---------------------------------------------------------

# Role IDs
old_role_id = ''  # duplicates removed from here
new_role_id = ''  # kept intact (current role)

# When True, perform reads only and print intended changes without applying them.
DRY_RUN = True

PAGE_SIZE = 100


# --- Setup -----------------------------------------------------------------

def build_apis():
    """Authenticate and return the Authorization API client."""
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


# --- Helpers ---------------------------------------------------------------

def get_role_user_ids(auth_api, role_id):
    """Return every user ID assigned to a role, paging through all results."""
    user_ids = []
    page = 1
    while True:
        response = auth_api.get_authorization_role_users(
            role_id, page_size=PAGE_SIZE, page_number=page
        )
        entities = response.entities or []
        for entity in entities:
            user_ids.append(entity.id)
        if page >= (response.page_count or 0):
            break
        page += 1
    return user_ids


# --- Steps -----------------------------------------------------------------

def collect_role_members(auth_api):
    """Step 1: collect the list of user IDs assigned to each role."""
    try:
        old_users = get_role_user_ids(auth_api, old_role_id)
        new_users = get_role_user_ids(auth_api, new_role_id)
    except ApiException as e:
        raise SystemExit("Failed to read role membership: %s" % e)

    print("Old role: %d user(s) | New role: %d user(s)"
          % (len(old_users), len(new_users)))
    return old_users, new_users


def find_duplicates(old_users, new_users):
    """Step 2: identify users who are in BOTH roles (duplicates)."""
    # Users assigned to both roles. Build the set once for fast membership tests.
    new_user_set = set(new_users)
    duplicates = []
    for uid in old_users:
        if uid in new_user_set:
            duplicates.append(uid)

    print("\n%d duplicate user(s) found in both roles:" % len(duplicates))
    pprint(duplicates)
    return duplicates


def remove_duplicates_from_old_role(auth_api, duplicates):
    """Step 3: remove the duplicate users from the old role only.

    The users remain assigned to the new/current role.
    """
    if not duplicates:
        print("\nNo duplicates to remove from the old role.")
        return
    if DRY_RUN:
        print("\n[DRY-RUN] Would remove %d duplicate user(s) from the old role:"
              % len(duplicates))
        pprint(duplicates)
        return
    try:
        auth_api.put_authorization_role_users_remove(old_role_id, duplicates)
        print("\nRemoved %d duplicate user(s) from the old role." % len(duplicates))
    except ApiException as e:
        raise SystemExit("Failed to remove users from the old role: %s" % e)


# --- Main ------------------------------------------------------------------

def main():
    auth_api = build_apis()

    old_users, new_users = collect_role_members(auth_api)
    duplicates = find_duplicates(old_users, new_users)
    remove_duplicates_from_old_role(auth_api, duplicates)


if __name__ == '__main__':
    main()
