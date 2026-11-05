# =============================================================================
# Genesys Cloud - Remove Duplicate Users From an Old Role
# =============================================================================
# Finds users who are in BOTH an old role and a new role, then removes those
# duplicate users from the old role only. The users keep the new role. This is
# handy after a role change, when some people ended up in both roles.
#
# Safety: the script always reads first and shows you a summary before it
# changes anything. It names the role users are removed from, the role they
# keep, and how many duplicate users will be removed. Then it asks you to
# confirm in a pop-up dialog (with a typed fallback if the dialog cannot be
# shown). No users are removed unless you confirm. Fill in old_role_id and
# new_role_id before you run it.
#
# Local runs need `pip install -r requirements.txt` and a populated .env with
# GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET.
# =============================================================================

from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint

from confirm_prompt import ask_to_confirm
from genesys_common import build_apis, get_role_user_ids, get_role_name


# --- Configuration ---------------------------------------------------------

# Role IDs
old_role_id = ''  # duplicates removed from here
new_role_id = ''  # kept intact (current role)





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

    The users remain assigned to the new/current role. Call this only after the
    person has confirmed.
    """
    if not duplicates:
        print("\nNo duplicates to remove from the old role.")
        return
    try:
        auth_api.put_authorization_role_users_remove(old_role_id, duplicates)
        print("\nRemoved %d duplicate user(s) from the old role." % len(duplicates))
    except ApiException as e:
        raise SystemExit("Failed to remove users from the old role: %s" % e)


def format_removal_for_confirm(duplicate_count, old_role_name, new_role_name):
    """Build the confirm message that describes the duplicate removal.

    Names the role users are removed from, the role they keep, and how many
    duplicate users will be removed. Returns one block of text with real new
    lines, shown in the confirm dialog and the typed fallback.
    """
    lines = []

    lines.append("This will remove %d duplicate user(s) from one role." % duplicate_count)

    lines.append("")
    lines.append("Remove them from this role:")
    lines.append(old_role_name)

    lines.append("")
    lines.append("They keep this role:")
    lines.append(new_role_name)

    lines.append("")
    lines.append("Only users who are in BOTH roles are removed from the old role.")
    lines.append("Nothing else is changed.")

    return '\n'.join(lines)


# --- Main ------------------------------------------------------------------

def main():
    auth_api = build_apis('AuthorizationApi')

    old_users, new_users = collect_role_members(auth_api)
    duplicates = find_duplicates(old_users, new_users)

    # Nothing is in both roles, so there is nothing to remove. Stop before the
    # confirm so we do not ask about a removal of zero users.
    if not duplicates:
        print("\nNo duplicate users found in both roles, so there is nothing to remove.")
        return

    # Show the plan and ask you to confirm before removing anyone. If you do not
    # confirm, no users are removed.
    old_role_name = get_role_name(auth_api, old_role_id)
    new_role_name = get_role_name(auth_api, new_role_id)
    question = format_removal_for_confirm(len(duplicates), old_role_name, new_role_name)
    if not ask_to_confirm(question, "Remove Duplicate Users From a Role"):
        raise SystemExit("Stopped at your request. No users were removed.")

    remove_duplicates_from_old_role(auth_api, duplicates)


if __name__ == '__main__':
    main()
