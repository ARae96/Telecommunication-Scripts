# =============================================================================
# Genesys Cloud - Migrate Users From an Old Role to a New Role (by Division)
# =============================================================================
# Moves users from an old role to a new role, but only for the divisions you
# choose. The new role is granted scoped to each user's own division.
#
# Steps:
#   1. Find users who have the old role but not the new one.
#   2. Keep only those whose home division is in DIVISION_IDS. As part of this
#      step we also check every role each user holds. If a user has a role in
#      any division outside their home division, we leave them alone and write
#      them to a CSV to review by hand. This protects senior leaders and support
#      staff who are given access to more than one division on purpose.
#   3. Grant the new role to each matched user, scoped to their own division.
#   4. Confirm every matched user now has the new role. Stop if any are missing.
#   5. Remove the matched users from the old role.
#
# Output (written next to this script only when someone is skipped in step 2):
#   role_migration_multi_division_<ts>.csv
#      One row per skipped user, listing the extra divisions they hold roles in.
#
# Safety: the script always reads first and shows you a summary before it
# changes anything. It names the old and new role, how many users will be
# migrated, and how many were skipped for holding roles in more than one
# division. Then it asks you to confirm in a pop-up dialog (with a typed
# fallback if the dialog cannot be shown). Nothing is granted or removed unless
# you confirm. Fill in old_role_id and new_role_id before you run it.
#
# Even after you confirm, the old role is removed only after the script checks
# that every migrated user already has the new role. If that check fails, it
# stops before removing anything.
#
# Local runs need `pip install -r requirements.txt` and a populated .env with
# GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET.
# =============================================================================

import os
import csv
import time
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
from dotenv import load_dotenv

from confirm_prompt import ask_to_confirm


# --- Configuration ---------------------------------------------------------

# Role IDs
old_role_id = 'c8287a29-b49e-417c-979b-541056cde2fa'  # role being replaced
new_role_id = '764ff8e7-0601-4248-a9fe-2321b9c6eaf8'  # role being assigned

# Only users whose division is in this list are touched. Those users get the
# new role and lose the old one. Everyone else is left alone. Put the division
# IDs you want to migrate here. Change this list to reuse the script for other
# divisions.
DIVISION_IDS = [
    '563abcbe-1c9e-4c03-abc1-2e74278d6652', '94eea55f-6aa3-4975-97be-df57de4148c8', 'ab2c49bc-1607-4fa7-a33d-db5ee1ce5fe6', '88a40f1f-0fa2-4a2e-a6a7-473491456d1d',
]

# Every user is expected to also belong to this shared division, so having it is
# normal and does not make someone "multi-division." We ignore it when we check
# whether a user holds roles outside their home division. If we did not ignore
# it, every user would look multi-division and get skipped by mistake.
SHARED_DIVISION_ID = 'df1b7ef4-744c-4b47-8aad-9dc6b2ecb9e0'

PAGE_SIZE = 100


# --- Setup -----------------------------------------------------------------

def build_apis():
    """Authenticate and return the Authorization and Users API clients."""
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
    client_id = os.environ.get('GENESYS_CLOUD_CLIENT_ID')
    client_secret = os.environ.get('GENESYS_CLOUD_CLIENT_SECRET')
    if not client_id or not client_secret:
        raise SystemExit(
            "Missing Genesys Cloud credentials. Copy .env.example to .env and set "
            "GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET."
        )

    # Genesys API call: ApiClient.get_client_credentials_token - signs in with
    # the client ID and secret and returns an authenticated client.
    apiclient = PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(
        client_id, client_secret
    )
    return (
        PureCloudPlatformClientV2.AuthorizationApi(apiclient),
        PureCloudPlatformClientV2.UsersApi(apiclient),
    )


# --- Helpers ---------------------------------------------------------------

def get_role_user_ids(auth_api, role_id):
    """Return every user ID assigned to a role, paging through all results."""
    user_ids = []
    page = 1
    while True:
        # Genesys API call: AuthorizationApi.get_authorization_role_users -
        # lists the users assigned to one role, one page at a time.
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


def division_matches(division_id):
    """True if the division ID is in the DIVISION_IDS list."""
    return bool(division_id) and division_id in DIVISION_IDS


def get_user_grant_division_ids(auth_api, user_id):
    """Return the set of division IDs a user holds roles in.

    Calls get_authorization_subject, which lists every role and division granted
    to the user. We read the division ID from each grant and return them as a
    set, so a user with roles in three divisions gives back three IDs.

    Genesys can grant a role across all divisions at once. That shows up as the
    special division ID "*". We keep that ID as-is, so the caller can treat "all
    divisions" as more than one division and skip the user.
    """
    # Genesys API call: AuthorizationApi.get_authorization_subject - lists every
    # role and division granted to one user.
    subject = auth_api.get_authorization_subject(user_id)
    grants = getattr(subject, 'grants', None) or []

    division_ids = set()
    for grant in grants:
        division = getattr(grant, 'division', None)
        if division is not None and division.id:
            division_ids.add(division.id)
    return division_ids


def write_multi_division_csv(rows):
    """Write skipped multi-division users to a timestamped CSV next to this script.

    Each row is one user we left alone because they hold a role outside their
    home division. Writes nothing and returns None when there are no rows.
    Returns the CSV path when a file is written.
    """
    if not rows:
        return None

    timestamp = time.strftime('%Y%m%d_%H%M%S')
    filename = 'role_migration_multi_division_%s.csv' % timestamp
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user_id', 'home_division_id', 'all_division_ids'])
        for row in rows:
            # Join the division IDs into one cell so the list fits in a single
            # CSV column and opens cleanly in Excel.
            all_ids = ', '.join(sorted(row['all_division_ids']))
            writer.writerow([row['user_id'], row['home_division_id'], all_ids])

    return csv_path


# --- Steps -----------------------------------------------------------------

def find_users_to_migrate(auth_api):
    """Step 1: users who have the old role but are missing the new one."""
    try:
        old_users = get_role_user_ids(auth_api, old_role_id)
        new_users = set(get_role_user_ids(auth_api, new_role_id))
    except ApiException as e:
        raise SystemExit("Failed to read role membership: %s" % e)

    # Users who have the old role but are not yet in the new role.
    missing = []
    for uid in old_users:
        if uid not in new_users:
            missing.append(uid)

    print("Old role: %d user(s) | New role: %d user(s) | Missing new role: %d"
          % (len(old_users), len(new_users), len(missing)))
    return missing


def match_users_by_division(auth_api, users_api, user_ids):
    """Step 2: keep users whose home division is in the list and who only hold
    roles in that one division.

    Takes user_ids, the list of users with the old role from Step 1. For each
    user we look at their home division. If it is
    not in DIVISION_IDS, we skip them. If it is, we then check every role they
    hold. A user who holds a role in any division other than their home division
    is left alone and saved for the multi-division CSV, because they were given
    that extra access on purpose (for example, senior leaders and support staff).

    Returns a tuple of two things:
      matched: {user_id: {"division_id", "division_name"}} for users we will migrate.
      multi_division_rows: a list of rows for users skipped for having roles in
        more than one division. Each row has "user_id", "home_division_id", and
        "all_division_ids" (a set of every division ID they hold roles in).
    """
    matched = {}
    skipped_wrong_division = []
    multi_division_rows = []

    for uid in user_ids:
        try:
            # Genesys API call: UsersApi.get_user - reads one user, including
            # their home division.
            user = users_api.get_user(uid)
        except ApiException as e:
            print("Could not fetch user %s: %s" % (uid, e))
            continue

        division = getattr(user, 'division', None)
        if division is None:
            print("User %s has no division; skipping." % uid)
            continue

        # Skip anyone whose home division is not one we are migrating.
        if not division_matches(division.id):
            skipped_wrong_division.append(uid)
            continue

        # The home division is in scope. Now make sure this user does not also
        # hold a role in some other division. If they do, they need multi-
        # division access on purpose, so we leave them alone and log them.
        try:
            all_division_ids = get_user_grant_division_ids(auth_api, uid)
        except ApiException as e:
            # If we cannot read a user's grants, do not guess. Skip them and log
            # it so someone can check by hand instead of migrating them blindly.
            print("Could not read roles for user %s; skipping: %s" % (uid, e))
            continue

        # Ignore the user's home division and the shared division everyone has.
        # Anything left over means the user holds a role in a division we did
        # not expect, which is the case we want to catch.
        expected_division_ids = {division.id, SHARED_DIVISION_ID}
        extra_division_ids = all_division_ids - expected_division_ids
        if extra_division_ids:
            multi_division_rows.append({
                "user_id": uid,
                "home_division_id": division.id,
                "all_division_ids": all_division_ids,
            })
            continue

        matched[uid] = {"division_id": division.id, "division_name": division.name}

    print("\n%d user(s) matched for migration; %d skipped (wrong division); "
          "%d skipped (multiple divisions)."
          % (len(matched), len(skipped_wrong_division), len(multi_division_rows)))
    pprint(matched)
    if skipped_wrong_division:
        print("Skipped (home division not in the division list):")
        pprint(skipped_wrong_division)
    if multi_division_rows:
        print("Skipped (roles in more than one division):")
        pprint([row["user_id"] for row in multi_division_rows])
    return matched, multi_division_rows


def grant_new_role(auth_api, matched):
    """Step 3: grant the new role to each matched user, scoped to their division.

    Call this only after the person has confirmed.
    """
    for uid, division in matched.items():
        try:
            # Genesys API call: AuthorizationApi.post_authorization_subject_bulkadd
            # - grants the new role to one user, scoped to their division.
            auth_api.post_authorization_subject_bulkadd(
                uid, _grant_body(division["division_id"]), subject_type='PC_USER'
            )
        except ApiException as e:
            print("Failed to grant role to %s: %s" % (uid, e))

    print("\nGranted the new role (with division) to %d user(s)." % len(matched))


def _grant_body(division_id):
    """Build the RoleDivisionGrants body for a single new-role/division pair.

    These SDK model constructors take no arguments, so fields are set directly.
    """
    pair = PureCloudPlatformClientV2.RoleDivisionPair()
    pair.role_id = new_role_id
    pair.division_id = division_id
    body = PureCloudPlatformClientV2.RoleDivisionGrants()
    body.grants = [pair]
    return body


def confirm_migration(auth_api, target_ids):
    """Step 4: verify all target users now have the new role; stop if any don't."""
    time.sleep(5)  # allow the role assignment to propagate
    try:
        new_users = set(get_role_user_ids(auth_api, new_role_id))
    except ApiException as e:
        raise SystemExit("Failed to re-read new role membership: %s" % e)

    missing = [uid for uid in target_ids if uid not in new_users]
    if missing:
        print("\nSTOP: %d target user(s) still missing the new role. "
              "The old role will NOT be removed:" % len(missing))
        pprint(missing)
        raise SystemExit(1)

    print("\nConfirmed: all %d target user(s) now have the new role." % len(target_ids))


def remove_old_role(auth_api, target_ids):
    """Step 5: remove the matched users from the old role."""
    if not target_ids:
        print("No matching users to remove from the old role.")
        return
    try:
        # Genesys API call: AuthorizationApi.put_authorization_role_users_remove
        # - removes the matched users from the old role.
        auth_api.put_authorization_role_users_remove(old_role_id, target_ids)
        print("Removed %d user(s) from the old role." % len(target_ids))
    except ApiException as e:
        raise SystemExit("Failed to remove users from the old role: %s" % e)


def get_role_name(auth_api, role_id):
    """Return a role's name, or a fallback label if we cannot read it.

    We show this name in the confirm dialog so you can check you picked the
    right role. If the read fails we return a short "(name unavailable)" label
    instead of stopping, because a missing name should not block the summary.
    """
    try:
        role = auth_api.get_authorization_role(role_id)
    except ApiException as e:
        print("Could not read role name for %s: %s" % (role_id, e))
        return "(name unavailable)"
    return getattr(role, 'name', None) or "(name unavailable)"


def format_migration_for_confirm(migrate_count, skipped_count, old_role_name, new_role_name):
    """Build the confirm message that describes the role migration.

    Names the old role (removed) and the new role (granted), how many users will
    be migrated, and how many were skipped for holding roles in more than one
    division. The skipped paragraph is left out when no one was skipped, so the
    message never mentions a CSV that was not written. Returns one block of text
    with real new lines, shown in the confirm dialog and the typed fallback.
    """
    lines = []

    lines.append("You are migrating %d user(s) to a new role." % migrate_count)

    lines.append("")
    lines.append("The removed role is:")
    lines.append(old_role_name)

    lines.append("")
    lines.append("The new role is:")
    lines.append(new_role_name)

    if skipped_count:
        lines.append("")
        lines.append("%d user(s) were skipped due to division count." % skipped_count)
        lines.append("Nothing was changed for them and they were written to a CSV.")

    lines.append("")
    lines.append(
        "Note: This removes the role from every migrated user. It runs after "
        "confirming each has the new role."
    )

    return '\n'.join(lines)


# --- Main ------------------------------------------------------------------

def main():
    auth_api, users_api = build_apis()

    users_to_migrate = find_users_to_migrate(auth_api)
    matched, multi_division_rows = match_users_by_division(
        auth_api, users_api, users_to_migrate
    )
    target_ids = list(matched)

    # Save the multi-division users to a CSV so someone can review them by hand.
    csv_path = write_multi_division_csv(multi_division_rows)
    if csv_path:
        print("\nWrote %d multi-division user(s) to %s"
              % (len(multi_division_rows), csv_path))

    # Nothing matched, so there is nothing to grant or remove. Stop before the
    # confirm so we do not ask about a migration of zero users.
    if not target_ids:
        print("\nNo users matched for migration, so there is nothing to change.")
        return

    # Show the plan and ask you to confirm before any grant or removal. If you
    # do not confirm, no role is granted or removed.
    old_role_name = get_role_name(auth_api, old_role_id)
    new_role_name = get_role_name(auth_api, new_role_id)
    question = format_migration_for_confirm(
        len(target_ids), len(multi_division_rows), old_role_name, new_role_name
    )
    if not ask_to_confirm(question, "Migrate Users to a New Role"):
        raise SystemExit("Stopped at your request. No roles were granted or removed.")

    grant_new_role(auth_api, matched)
    confirm_migration(auth_api, target_ids)
    remove_old_role(auth_api, target_ids)


if __name__ == '__main__':
    main()
    
    
#--- Correct APIs to Use -----------
