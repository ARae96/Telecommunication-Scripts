# =============================================================================
# Genesys Cloud - Compare Roles
# =============================================================================
# Compares the permissions of one or more Genesys Cloud roles against a
# different role. You enter the base role (the one you compare against) and the
# list of roles to compare near the top of the file. You can paste the role page
# link from your browser or just the role ID. The script signs in to
# Genesys Cloud, reads each role with its permissions, and shows what each
# compared role has more of or less of than the base role.
#
# This script only reads. It never changes anything in Genesys Cloud, so it
# does not ask you to confirm.
#
# Output:
#   - A short summary printed in the terminal for each compared role.
#   - One CSV file you can open in Excel, written next to this script:
#       compare_roles_<timestamp>.csv
#     It has one row per permission. The first column is the permission, written
#     as domain:entity:action. Next is a column for the base role, then one
#     column for each compared role. A cell says "Yes" when that role has the
#     permission and is blank when it does not. The last column says "Same in
#     all roles" or "Different".
#
# Please note: Genesys can store a permission with an action of "*", which means
# every action for that entity. We expand it into the real actions. For example,
# "directory:user:*" becomes "directory:user:view", "directory:user:edit", and so
# on. The "*" rows themselves are not in the CSV. To know which real actions
# exist, the script reads the full permission list from Genesys Cloud first.
#
# Run locally with:
#   pip install -r requirements.txt
# and a populated .env (GENESYS_CLOUD_CLIENT_ID / GENESYS_CLOUD_CLIENT_SECRET).
# =============================================================================


# --- Imports -----------------------------------------------------------------
import os
from datetime import datetime

from PureCloudPlatformClientV2.rest import ApiException

from genesys_common import (
    build_apis,
    get_role_id_from_link,
    get_role_with_permissions,
    write_csv_file,
)


# --- Configuration -----------------------------------------------------------
# Paste the role links by hand before running. Open a role in Genesys Cloud and
# copy the link from your browser. It ends in the role ID, for example:
#   https://apps.mypurecloud.com/directory/#/admin/people-permissions/roles/888af629-4949-44b8-9ee1-082217284110
# A bare role ID works too. The base role is the one we compare against. The
# compared roles are the ones checked against it.
BASE_ROLE_LINK = 'https://apps.mypurecloud.com/directory/#/admin/people-permissions/roles/888af629-4949-44b8-9ee1-082217284110'
ROLE_LINKS_TO_COMPARE = [
    'https://apps.mypurecloud.com/directory/#/admin/people-permissions/roles/35698114-d1b8-4fd4-b0ba-0eb7657a642b',
    'https://apps.mypurecloud.com/directory/#/admin/people-permissions/roles/25e1a293-aaa0-4fdd-a15a-90955dc7fb13'
]

# The CSV is written in the same folder as this script.
OUTPUT_FOLDER = os.path.dirname(os.path.abspath(__file__))

# How many permission domains to ask Genesys for in each page.
PAGE_SIZE = 100

# The words used in the CSV.
HAS_PERMISSION_TEXT = 'Yes'
SAME_TEXT = 'Same in all roles'
DIFFERENT_TEXT = 'Different'


# --- Helpers -----------------------------------------------------------------
def get_all_permission_parts(authorization_api):
    """Return every real permission in Genesys Cloud as (domain, entity, action) tuples.

    We use this list to expand a "*" into the actual actions. Entries whose
    action is "*" are left out, because we only want the real actions. Stops
    the script if the read fails, since the comparison cannot be trusted
    without it.
    """
    all_permissions = []
    page_number = 1
    while True:
        try:
            # Genesys API call: get_authorization_permissions - lists every
            # permission defined in the system, grouped by domain.
            response = authorization_api.get_authorization_permissions(
                page_size=PAGE_SIZE, page_number=page_number)
        except ApiException as e:
            raise SystemExit("Failed to read the permission list: %s" % e)

        for domain_collection in (response.entities or []):
            permission_map = domain_collection.permission_map or {}
            for entity_name, permission_list in permission_map.items():
                for permission in permission_list:
                    if permission.action == '*':
                        continue
                    all_permissions.append(
                        (domain_collection.domain, entity_name, permission.action))

        if page_number >= (response.page_count or 0):
            break
        page_number += 1
    return all_permissions


def part_matches(role_value, real_value):
    """Return True when a role's value is the real value or a "*" wildcard."""
    return role_value == '*' or role_value == real_value


def get_permission_strings(role, all_permission_parts):
    """Return the set of permission strings (domain:entity:action) for a role.

    The role must have been read with its permission policies filled in. A "*"
    in the domain, entity, or action is expanded into every real permission it
    covers. If a policy names a permission that is not in the Genesys list, we
    still keep it as written so nothing is silently lost.
    """
    permission_strings = set()
    for policy in (getattr(role, 'permission_policies', None) or []):
        domain = getattr(policy, 'domain', None)
        entity_name = getattr(policy, 'entity_name', None)
        if not domain or not entity_name:
            continue
        for action in (getattr(policy, 'action_set', None) or []):
            found_match = False
            for real_domain, real_entity, real_action in all_permission_parts:
                if (part_matches(domain, real_domain)
                        and part_matches(entity_name, real_entity)
                        and part_matches(action, real_action)):
                    permission_strings.add("%s:%s:%s" % (real_domain, real_entity, real_action))
                    found_match = True
            if not found_match and '*' not in (domain, entity_name, action):
                permission_strings.add("%s:%s:%s" % (domain, entity_name, action))
    return permission_strings


def make_unique_column_names(role_names):
    """Return the role names as CSV column names, with no repeats.

    Two roles can share a name. A repeat gets " (2)", " (3)", and so on added,
    because a CSV row cannot have two columns with the same name.
    """
    column_names = []
    for name in role_names:
        column_name = name
        number = 2
        while column_name in column_names or column_name in ('Permission', 'Result'):
            column_name = "%s (%d)" % (name, number)
            number += 1
        column_names.append(column_name)
    return column_names


# --- Steps -------------------------------------------------------------------
def read_roles(authorization_api):
    """Step 1: Read the base role and every compared role.

    Reads the full permission list once first, so every "*" can be expanded.

    Returns a list of (role name, set of permission strings) tuples. The base
    role is first, then the compared roles in the order you entered them.
    """
    all_permission_parts = get_all_permission_parts(authorization_api)
    role_links = [BASE_ROLE_LINK] + ROLE_LINKS_TO_COMPARE
    role_ids = []
    for role_link in role_links:
        role_ids.append(get_role_id_from_link(role_link))

    roles = []
    for role_id in role_ids:
        role = get_role_with_permissions(authorization_api, role_id)
        roles.append((role.name, get_permission_strings(role, all_permission_parts)))
    return roles


def print_summary(roles):
    """Step 2: Print how each compared role differs from the base role."""
    base_name, base_permissions = roles[0]
    print("\nBase role: %s (%d permissions)" % (base_name, len(base_permissions)))

    for role_name, role_permissions in roles[1:]:
        only_in_base = base_permissions - role_permissions
        only_in_role = role_permissions - base_permissions
        shared = base_permissions & role_permissions
        print("\nCompared role: %s (%d permissions)" % (role_name, len(role_permissions)))
        print("  In both roles:                 %d" % len(shared))
        print("  Only in the base role:         %d" % len(only_in_base))
        print("  Only in %s: %d" % (role_name, len(only_in_role)))


def build_csv_rows(roles, column_names):
    """Step 3: Return the CSV rows, one per permission, sorted by permission.

    Each row is a dict. The keys are "Permission", one key per role column, and
    "Result".
    """
    all_permissions = set()
    for role_name, role_permissions in roles:
        all_permissions.update(role_permissions)

    rows = []
    for permission in sorted(all_permissions):
        row = {'Permission': permission}
        roles_with_permission = 0
        for index, (role_name, role_permissions) in enumerate(roles):
            if permission in role_permissions:
                row[column_names[index]] = HAS_PERMISSION_TEXT
                roles_with_permission += 1
            else:
                row[column_names[index]] = ''
        if roles_with_permission == len(roles):
            row['Result'] = SAME_TEXT
        else:
            row['Result'] = DIFFERENT_TEXT
        rows.append(row)
    return rows


# --- Main --------------------------------------------------------------------
def main():
    """Read the roles, print a summary, and write the comparison CSV."""
    if not ROLE_LINKS_TO_COMPARE:
        raise SystemExit("Add at least one role link to ROLE_LINKS_TO_COMPARE.")

    authorization_api = build_apis('AuthorizationApi')

    roles = read_roles(authorization_api)
    print_summary(roles)

    role_names = [name for name, permissions in roles]
    column_names = make_unique_column_names(role_names)
    rows = build_csv_rows(roles, column_names)

    field_names = ['Permission'] + column_names + ['Result']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_name = 'compare_roles_%s.csv' % timestamp
    file_path = write_csv_file(OUTPUT_FOLDER, file_name, field_names, rows)
    print("\nWrote %d permission rows to %s" % (len(rows), file_path))


if __name__ == '__main__':
    main()
