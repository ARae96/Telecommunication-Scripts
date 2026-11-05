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


from genesys_common import build_apis, get_user_role_ids, get_role_permission_strings



# --- Configuration -----------------------------------------------------------
# The role you want to check. Enter the role ID by hand. Its permissions are
# combined with the base roles below to form the role side of the comparison.
role_id = '84f1296f-2ced-47e8-9c5d-8c98ba62659d'

# The person whose permissions we compare against the roles. Enter the user ID
# by hand. We gather every permission this person has, across all their roles.
user_id = '6fd4c6ad-8f6f-4992-ac96-a52541522979'

# Base roles that are always part of the role side, on every run. Keeping these
# here as a constant means you only set role_id and user_id each time, and these
# roles are folded in for you. A permission counts as "in the roles" if role_id
# or any of these base roles grants it.
BASE_ROLES = [
    '4ab1c48a-5a6b-4962-a661-f5b4053cdbfe', # Employee Role
    ]


# --- Helpers -----------------------------------------------------------------
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

    authorization_api = build_apis('AuthorizationApi')

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