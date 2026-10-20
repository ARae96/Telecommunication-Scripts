# =============================================================================
# Genesys Cloud - Compare Role Permissions Against a User's Permissions
# =============================================================================
# Compares the permissions from a set of roles against every permission one
# person actually has, then writes the differences to an Excel workbook you can
# open in Excel. The idea is to see, at a glance, where a person's access does
# not line up with the roles you expect them to match.
#
# What goes into each side of the comparison:
#   - Role side: the permissions from the role you are checking (role_id) plus
#     the base roles in BASE_ROLES. We combine all of these into one set, so a
#     permission counts as "in the roles" if any one of those roles grants it.
#   - User side: every permission the person has, gathered from all the roles
#     granted to them and combined into one set.
#
# We compare plain permission strings. A Genesys role stores its access as
# permission policies, where each policy has a domain (like "routing"), an
# entity inside that domain (like "queue"), and the actions allowed on it (like
# "view" or "edit"). We flatten each policy into one string per action, in the
# form domain:entity:action (for example, routing:queue:view). The comparison
# is done on those strings.
#
# Output (one timestamped Excel workbook written at the workspace root):
#   Permission_Comparison_<MM_DD_YYYY_hh-mm-ss_AM/PM>.xlsx
#      A workbook with two sheets, each a plain list of permission strings:
#        - "Missing From User": permissions the roles grant that the user does
#          not have.
#        - "Extra On User": permissions the user has that the roles do not
#          grant.
#      Permissions both sides share are left out, because they are not a
#      difference worth acting on.
#
# This script only reads from Genesys. It changes nothing, so there is no
# DRY_RUN flag. A sibling script, Merge_Role_Permissions.py, rolls a user's
# role permissions up onto a single role.
#
# Run locally with:
#   pip install -r requirements.txt
# and a populated .env (GENESYS_CLOUD_CLIENT_ID / GENESYS_CLOUD_CLIENT_SECRET).
# =============================================================================


# --- Imports -----------------------------------------------------------------
import os
import time
import openpyxl

import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from dotenv import load_dotenv



# --- Configuration -----------------------------------------------------------
# The role you want to check. Enter the role ID by hand. Its permissions are
# combined with the base roles below to form the role side of the comparison.
role_id = '57d27899-8f78-44e2-b959-1a081d4ddc47'

# The person whose permissions we compare against the roles. Enter the user ID
# by hand. We gather every permission this person has, across all their roles.
user_id = '4b080942-d01e-49c8-822f-08ff47b3d78f'

# Base roles that are always part of the role side, on every run. Keeping these
# here as a constant means you only set role_id and user_id each time, and these
# roles are folded in for you. A permission counts as "in the roles" if role_id
# or any of these base roles grants it.
BASE_ROLES = ['4ab1c48a-5a6b-4962-a661-f5b4053cdbfe', '25e1a293-aaa0-4fdd-a15a-90955dc7fb13']


# --- Authentication ----------------------------------------------------------
def build_apis():
    """Sign in to Genesys Cloud and return the API client this script needs.

    Reads GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET from the .env
    file at the workspace root (one folder up from this script). Stops the
    script with a helpful message if either value is missing. Returns the
    AuthorizationApi client, which covers reading a user's roles and reading
    each role's permissions.
    """
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
    return PureCloudPlatformClientV2.AuthorizationApi(apiclient)


# --- Helpers -----------------------------------------------------------------
def get_user_role_ids(authorization_api, user_id):
    """Return the IDs of the roles granted to one person, with no repeats.

    Reads the person's authorization grants from Genesys Cloud. Each grant
    pairs one role with one division, so a role the person has in two divisions
    shows up twice. We only care about which roles they have, not the division,
    so we return each role ID once.

    Returns a list of role ID strings. Returns an empty list if the call fails,
    so the caller can decide what to do next.
    """
    role_ids = []
    seen = set()

    try:
        # Genesys API call: AuthorizationApi.get_authorization_subject - lists
        # every role and division granted to one user.
        subject = authorization_api.get_authorization_subject(user_id)
    except ApiException as e:
        print("Exception when calling AuthorizationApi->get_authorization_subject: %s\n" % e)
        return role_ids

    for grant in getattr(subject, 'grants', None) or []:
        role = getattr(grant, 'role', None)
        role_id_value = getattr(role, 'id', None)
        # Keep each role once, even when the user holds it in several divisions.
        if role_id_value and role_id_value not in seen:
            seen.add(role_id_value)
            role_ids.append(role_id_value)
    return role_ids


def policy_to_permission_strings(policy):
    """Turn one permission policy into a list of plain permission strings.

    A permission policy has a domain (like "routing"), an entity inside that
    domain (like "queue"), and an action set (the list of actions allowed, like
    "view" or "edit"). We build one string per action, in the form
    domain:entity:action, which is how Genesys writes a permission string.

    Returns a list of strings. Returns an empty list if the policy is missing
    its domain or entity, so a half-filled policy does not create junk strings.
    """
    domain = getattr(policy, 'domain', None)
    entity_name = getattr(policy, 'entity_name', None)
    if not domain or not entity_name:
        return []

    permission_strings = []
    for action in getattr(policy, 'action_set', None) or []:
        permission_strings.append("%s:%s:%s" % (domain, entity_name, action))
    return permission_strings


def get_role_permission_strings(authorization_api, role_id):
    """Return the set of plain permission strings for one role.

    Reads the role from Genesys to get its permission policies, then flattens
    each policy into permission strings in the form domain:entity:action. We
    return a set so repeats within a role are removed.

    Returns an empty set if the read fails or the role has no policies, so one
    bad role does not stop the whole run.
    """
    try:
        # Genesys API call: AuthorizationApi.get_authorization_role - reads one
        # role, including its permission policies.
        role = authorization_api.get_authorization_role(role_id)
    except ApiException as e:
        print("Exception reading role %s: %s\n" % (role_id, e))
        return set()

    permission_strings = set()
    for policy in getattr(role, 'permission_policies', None) or []:
        for permission in policy_to_permission_strings(policy):
            permission_strings.add(permission)
    return permission_strings


def collect_permissions_for_roles(authorization_api, role_ids):
    """Return the combined set of permission strings across several roles.

    Reads each role's permissions and unions them into one set, so a permission
    counts as present if any one of the roles grants it. Skips a blank role ID,
    so an unset role_id does not cause an API error. Returns a set of permission
    strings, empty if none of the roles grant anything.
    """
    combined = set()
    for role_id_value in role_ids:
        # Skip a blank ID. role_id may be unset, and an empty ID would fail at
        # the API call with a confusing error instead of just being left out.
        if not role_id_value:
            continue
        combined |= get_role_permission_strings(authorization_api, role_id_value)
    return combined


# --- Steps -------------------------------------------------------------------
def find_differences(role_permissions, user_permissions):
    """Split the two permission sets into the two lists of differences.

    Takes the combined role permissions and the user's permissions, both as
    sets of plain strings. Returns a tuple of two sorted lists:
      - missing_from_user: permissions the roles grant that the user does not
        have (role side minus user side).
      - extra_on_user: permissions the user has that the roles do not grant
        (user side minus role side).

    Permissions both sides share are left out of both lists, because they are
    not a difference. Each list is sorted so the workbook reads in a
    predictable order.
    """
    missing_from_user = sorted(role_permissions - user_permissions)
    extra_on_user = sorted(user_permissions - role_permissions)
    return (missing_from_user, extra_on_user)


def write_one_sheet(worksheet, header, permissions):
    """Fill one worksheet with a header and a plain list of permissions.

    Writes the header text in the first cell, then one permission string per row
    below it. Writes nothing but the header when the list is empty, so a sheet
    with no differences still shows its title. Changes the worksheet in place
    and returns nothing.
    """
    worksheet["A1"] = header
    row_number = 2
    for permission in permissions:
        worksheet.cell(row=row_number, column=1, value=permission)
        row_number += 1


def write_comparison_workbook(missing_from_user, extra_on_user):
    """Write the two difference lists to a timestamped Excel workbook.

    Writes one workbook at the workspace root (one folder up from this script),
    named Permission_Comparison_<ts>.xlsx. The timestamp uses the format
    MM_DD_YYYY_hh-mm-ss_AM/PM (for example, 10_14_2026_09-51-34_AM). We use
    dashes in the time instead of colons on purpose, because macOS and Windows
    do not allow a colon in a file name. The timestamp also means each run
    writes a new file instead of overwriting the last one.

    The workbook has two sheets, each a plain list of permission strings:
      - "Missing From User": permissions the roles grant that the user lacks.
      - "Extra On User": permissions the user has that the roles do not grant.

    Returns the full path to the file it wrote.
    """
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    timestamp = time.strftime("%m_%d_%Y_%I-%M-%S_%p")
    output_path = os.path.join(workspace_root, "Permission_Comparison_%s.xlsx" % timestamp)

    workbook = openpyxl.Workbook()

    # A new workbook comes with one empty sheet. Reuse it as the first sheet
    # rather than leaving a blank "Sheet" tab behind.
    missing_sheet = workbook.active
    missing_sheet.title = "Missing From User"
    write_one_sheet(missing_sheet, "Permissions the roles grant that the user is missing", missing_from_user)

    extra_sheet = workbook.create_sheet(title="Extra On User")
    write_one_sheet(extra_sheet, "Permissions the user has that the roles do not grant", extra_on_user)

    workbook.save(output_path)
    return output_path


# --- Main --------------------------------------------------------------------
def main():
    """Compare the role permissions against the user's permissions and save a CSV.

    Step 1: Read the person's roles, then gather every permission across those
            roles into one set. This is the user side of the comparison.
    Step 2: Gather the permissions from role_id plus the BASE_ROLES into one
            set. This is the role side of the comparison.
    Step 3: Split the two sets into the two difference lists: permissions
            missing from the user, and permissions extra on the user.
    Step 4: Write the two lists to a timestamped Excel workbook (one sheet
            each) at the workspace root.

    Stops early with a clear message if role_id or user_id is blank, so we never
    call the API with an empty ID.
    """
    # Stop early if either ID is blank. Without this, a blank ID would fail
    # later at the API call with a confusing error instead of a clear one.
    if not role_id or not user_id:
        raise SystemExit(
            "Set both 'role_id' (the role to check) and 'user_id' (the person to "
            "compare) near the top of the script before running."
        )

    authorization_api = build_apis()

    # Step 1: gather every permission the user has, across all their roles.
    user_role_ids = get_user_role_ids(authorization_api, user_id)
    if not user_role_ids:
        raise SystemExit(
            "The user has no roles, or the read failed. Check the 'user_id' and "
            "that the read above did not fail."
        )
    user_permissions = collect_permissions_for_roles(authorization_api, user_role_ids)

    # Step 2: gather the role-side permissions from role_id plus the base roles.
    role_side_ids = [role_id] + BASE_ROLES
    role_permissions = collect_permissions_for_roles(authorization_api, role_side_ids)

    print(
        "User %s has %d role(s) granting %d unique permission(s). The role side "
        "(role_id + %d base role(s)) grants %d unique permission(s)." % (
            user_id,
            len(user_role_ids),
            len(user_permissions),
            len(BASE_ROLES),
            len(role_permissions),
        )
    )

    # Step 3: split the two sets into the two difference lists.
    missing_from_user, extra_on_user = find_differences(role_permissions, user_permissions)

    # Step 4: write the two lists to an Excel workbook, one sheet each.
    output_path = write_comparison_workbook(missing_from_user, extra_on_user)

    print(
        "Wrote the comparison to %s\n"
        "  Missing From User: %d permission(s), Extra On User: %d permission(s)" % (
            output_path,
            len(missing_from_user),
            len(extra_on_user),
        )
    )


if __name__ == '__main__':
    main()