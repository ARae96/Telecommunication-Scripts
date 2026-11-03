# =============================================================================
# Genesys Cloud - Add a List of Permissions to a List of Roles
# =============================================================================
# Adds the same set of permissions to every role you list. Each role keeps all
# the permissions it already has and gains any new ones from your list. Nothing
# a role already had is removed, so it is safe to run on roles that are already
# in use.
#
# You control two lists at the top of this file before you run it:
#   PERMISSIONS_TO_ADD  - the permissions you want to grant.
#   ROLE_URLS           - the roles that should receive those permissions.
#
# For the roles, paste the whole page URL straight from your browser while you
# are looking at the role in Genesys. The script pulls the role ID out of the
# end of the URL for you, so you do not have to find the ID by hand. If you
# already have a bare role ID, you can paste that instead and it still works.
#
# A Genesys permission is written as three parts joined by colons:
#   domain:entity:action        (for example, "directory:user:view")
# The domain is the broad area (like "directory"), the entity is the thing in
# that area (like "user"), and the action is what you can do (like "view").
# Some actions allow a wildcard "*", which means "every action for that entity".
#
# Safety: the script always does a read-only preview first. It reads the roles,
# works out exactly which new permissions each one would gain, and shows you
# that plan. Nothing is saved until you confirm. If you say no, or if no role
# would change, the script stops and leaves every role as it was. There is no
# flag to set; the preview and confirm happen every run.
#
# The confirm step shows a macOS dialog box with Apply and Cancel buttons, so it
# is easy to read even outside a terminal. If the dialog cannot be shown (for
# example on Databricks or Linux, or when AppleScript is missing), it falls back
# to a typed "yes" prompt in the terminal instead.
#
# Local runs need `pip install -r requirements.txt` and a populated .env with
# GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET.
#
# Related script: Merge_Roles.py merges all permissions from whole source roles
# into one target role, rather than adding a hand-picked list like this one.
# =============================================================================

# --- Imports -----------------------------------------------------------------

import os
import re
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from dotenv import load_dotenv

from confirm_prompt import ask_to_confirm


# --- Configuration -----------------------------------------------------------

# The permissions you want to add. Write each one as "domain:entity:action".
# You can use "*" as the action to grant every action for that entity. Edit this
# list before each run. The same list is added to every role in ROLE_URLS below.
PERMISSIONS_TO_ADD = [
    'wfm:agentSelfScheduleActivityMove:view',
    'wfm:agentSelfScheduleJob:add',
    'wfm:agentSelfScheduleOffers:view',
    'wfm:agentSelfScheduleQuery:view',
    'wfm:agentSelfScheduleSettings:view',
    # Add more permissions here, one per line, for example:
    # 'analytics:conversationDetail:view',
    # 'routing:queue:view',
]

# The roles that should receive the permissions above. Paste the whole role
# page URL from your browser, like the example below, and the script pulls the
# role ID off the end for you. A bare role ID works too. Every role in this list
# gets every permission in PERMISSIONS_TO_ADD.
ROLE_URLS = [
    'https://apps.mypurecloud.com/directory/#/admin/people-permissions/roles/fed9bca6-8dc3-4cec-8151-5ebd2be08f0d',
    # Add more role URLs here, one per line.
]


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

def parse_permission(permission_text):
    """Split one "domain:entity:action" string into its three parts.

    Returns a (domain, entity, action) tuple. Stops the script if the text does
    not have exactly three parts, because a malformed permission would be
    silently ignored by Genesys and the role would not get what you expected.
    """
    parts = permission_text.split(':')
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise SystemExit(
            "Permission '%s' is not valid. Write each one as "
            "'domain:entity:action', for example 'directory:user:view'."
            % permission_text
        )
    domain, entity, action = parts
    return domain.strip(), entity.strip(), action.strip()


def group_actions_by_domain_and_entity(permissions):
    """Group the action for each permission under its domain and entity.

    Genesys stores permissions as policies, where one policy covers a single
    domain and entity and holds a list of allowed actions. So "directory:user:
    view" and "directory:user:edit" belong together in one "directory/user"
    policy with two actions. This reads the flat permission list and returns a
    dictionary keyed by (domain, entity), where each value is the list of
    actions for that pair, in the order you listed them and with no duplicates.
    """
    actions_by_key = {}
    for permission_text in permissions:
        domain, entity, action = parse_permission(permission_text)
        key = (domain, entity)
        if key not in actions_by_key:
            actions_by_key[key] = []
        if action not in actions_by_key[key]:
            actions_by_key[key].append(action)
    return actions_by_key


def looks_like_role_id(text):
    """True if the text looks like a Genesys role ID (a GUID).

    A role ID is a GUID: five groups of hex digits joined by dashes, like
    81425a3b-38fa-4f29-9e3c-1e1b991576d2. We check the shape so a bad paste is
    caught here instead of being sent to Genesys as a junk ID.
    """
    return bool(re.fullmatch(r'[0-9a-fA-F-]{36}', text)) and text.count('-') == 4


def role_id_from_url(role_url):
    """Pull the role ID out of a role page URL (or accept a bare ID).

    When you open a role in Genesys, the ID is the last part of the page URL,
    right after the final slash, for example:
      .../roles/81425a3b-38fa-4f29-9e3c-1e1b991576d2
    This takes whatever you pasted, trims any trailing slash, and keeps the part
    after the last slash. If you pasted a bare role ID with no slashes, that
    comes back unchanged. Stops the script if the result does not look like a
    role ID, so a wrong paste is caught before we call Genesys.
    """
    cleaned = role_url.strip().rstrip('/')
    last_part = cleaned.split('/')[-1]
    if not looks_like_role_id(last_part):
        raise SystemExit(
            "Could not find a role ID in '%s'. Paste the full role page URL from "
            "your browser (it ends in the role ID), or paste the bare role ID."
            % role_url
        )
    return last_part


def get_role_with_permissions(auth_api, role_id):
    """Return a single role, with its permission policies filled in.

    We pass expand=['permissionPolicies'] so Genesys includes the role's full
    permission list in the response. Without it the policies come back empty and
    we could not tell what the role already has. Stops the script if the read
    fails.
    """
    try:
        return auth_api.get_authorization_role(role_id, expand=['permissionPolicies'])
    except ApiException as e:
        raise SystemExit("Failed to read role %s: %s" % (role_id, e))


def add_actions_to_existing_policy(policy, actions_to_add):
    """Add the given actions to a policy that already exists, with no duplicates.

    Changes the policy in place. Keeps the actions the policy already allowed in
    their original order, then adds any new ones from your list that were not
    already there. Returns the number of actions that were actually new, so the
    caller can tell the reader how much changed.
    """
    existing_actions = list(getattr(policy, 'action_set', None) or [])
    added_count = 0
    for action in actions_to_add:
        if action not in existing_actions:
            existing_actions.append(action)
            added_count += 1
    policy.action_set = existing_actions
    return added_count


def make_new_policy(domain, entity, actions):
    """Build a brand new permission policy for one domain and entity.

    Used when a role does not yet have any policy for this domain and entity, so
    there is nothing to add onto and we create the policy from scratch with the
    actions you listed. These SDK model constructors take no arguments, so the
    fields are set one at a time after the object is made.
    """
    policy = PureCloudPlatformClientV2.DomainPermissionPolicy()
    policy.domain = domain
    policy.entity_name = entity
    policy.action_set = list(actions)
    return policy


def add_permissions_to_role_policies(role, actions_by_key):
    """Add the wanted permissions onto one role's existing policy list.

    Goes through each (domain, entity) pair you want to grant. If the role
    already has a policy for that pair, we add the missing actions onto it. If
    it does not, we build a new policy and add it to the role. Changes the
    role's permission_policies list in place and returns the total number of new
    actions added, so a return of 0 means the role already had everything.
    """
    # Build a quick lookup from (domain, entity) to the role's own policy, so we
    # can find a matching policy without scanning the whole list each time.
    policy_by_key = {}
    for policy in (role.permission_policies or []):
        key = (getattr(policy, 'domain', None), getattr(policy, 'entity_name', None))
        policy_by_key[key] = policy

    policies = list(role.permission_policies or [])
    total_added = 0
    for key, actions in actions_by_key.items():
        domain, entity = key
        if key in policy_by_key:
            total_added += add_actions_to_existing_policy(policy_by_key[key], actions)
        else:
            new_policy = make_new_policy(domain, entity, actions)
            policies.append(new_policy)
            policy_by_key[key] = new_policy
            total_added += len(actions)

    role.permission_policies = policies
    return total_added


def plan_new_permissions_for_role(role, actions_by_key):
    """Return the permissions a role would gain, without changing the role.

    Looks at what the role already has and works out which permissions from your
    list are new to it. Returns them as a list of "domain:entity:action" strings
    so they read the same way you typed them. The role is not changed, so this
    is safe to use for the read-only preview. An empty list means the role
    already has every permission in your list.
    """
    # Collect the actions the role already allows for each (domain, entity), so
    # we can tell which of your actions are genuinely new.
    existing_actions_by_key = {}
    for policy in (role.permission_policies or []):
        key = (getattr(policy, 'domain', None), getattr(policy, 'entity_name', None))
        existing_actions_by_key[key] = set(getattr(policy, 'action_set', None) or [])

    new_permissions = []
    for key, actions in actions_by_key.items():
        domain, entity = key
        already_have = existing_actions_by_key.get(key, set())
        for action in actions:
            if action not in already_have:
                new_permissions.append("%s:%s:%s" % (domain, entity, action))
    return new_permissions


# --- Steps -------------------------------------------------------------------

def format_plan_for_confirm(roles_to_change):
    """Build the confirm message: the permissions once, then the roles once.

    roles_to_change is the list of role objects that will actually be changed
    (the ones that would gain at least one permission). This returns one block
    of text, with real new lines, laid out in two parts: first the full list of
    permissions from PERMISSIONS_TO_ADD, then the roles that will receive them,
    each shown as "name (id)". The same text is used by the macOS dialog and the
    typed prompt, so you read the same message either way.
    """
    lines = []

    lines.append("The following Permissions will be added:")
    for permission_text in PERMISSIONS_TO_ADD:
        lines.append(permission_text)

    lines.append("")  # blank line between the two sections

    lines.append("The following roles will receive the above permissions:")
    for role in roles_to_change:
        lines.append("%s (%" % (role.name))

    # Join with new lines. applescript_quote turns these into real line breaks
    # for the dialog, and the typed prompt prints them as-is.
    return '\n'.join(lines)


def preview_changes(plan_by_role):
    """Print the read-only preview of what would change, and return if anything would.

    plan_by_role is a list of (role, new_permissions) pairs, where
    new_permissions is the list of "domain:entity:action" strings that role
    would gain. For each role that would gain something, this prints the role
    name and the exact permissions it would get, so you can check the plan
    before anything is saved. Roles that already have everything are listed
    together at the end so you know they were seen but need no change.

    Returns True if at least one role would gain a permission, so the caller
    knows whether it is worth asking you to confirm.
    """
    roles_with_changes = []
    roles_unchanged = []
    for role, new_permissions in plan_by_role:
        if new_permissions:
            roles_with_changes.append((role, new_permissions))
        else:
            roles_unchanged.append(role)

    print("\n=== Preview (nothing has been saved yet) ===")

    for role, new_permissions in roles_with_changes:
        print("\nRole '%s' would gain %d permission(s):" % (role.name, len(new_permissions)))
        for permission_text in new_permissions:
            print("  - %s" % permission_text)

    if roles_unchanged:
        print("\nThese role(s) already have every permission and would not change:")
        for role in roles_unchanged:
            print("  - %s" % role.name)

    if not roles_with_changes:
        print("\nNo role would change. Every role already has all of these permissions.")

    return bool(roles_with_changes)


def apply_permissions_to_one_role(auth_api, role, actions_by_key):
    """Add the permissions onto one role and save it. Call this only after confirm.

    Takes a role object that was already read with its permissions (so we do not
    fetch it twice). Adds the wanted permissions onto it and saves it back. The
    role keeps its own name and description, so only its permissions change.

    Returns True when the role was saved and False when it was left alone, either
    because it already had every permission or because the save failed. The
    caller uses this to build one summary at the end, so a role we did not change
    is not reported as a success.
    """
    role_id = role.id
    added_count = add_permissions_to_role_policies(role, actions_by_key)

    # The role already had every permission in the list, so there is nothing to
    # save. Report it as "not updated" so the summary does not claim we changed
    # a role we left alone.
    if added_count == 0:
        return False

    # Save the role back. We start from the role we read, so we keep its own
    # name and description. Genesys rejects a save that renames a role to a name
    # another role already uses, which is why we never change the name here.
    try:
        # Genesys API call: AuthorizationApi.put_authorization_role - saves the
        # role, including its updated permission policies.
        auth_api.put_authorization_role(role_id, role)
        return True
    except ApiException as e:
        # Log and move on so one failed role does not stop the others, but
        # report it as not updated so it is left out of the success summary.
        print("Failed to update role '%s' (%s): %s" % (role.name, role_id, e))
        return False


# --- Main --------------------------------------------------------------------

def main():
    if not PERMISSIONS_TO_ADD:
        raise SystemExit(
            "PERMISSIONS_TO_ADD is empty. Add one or more permissions at the top "
            "of this script, each written as 'domain:entity:action'."
        )
    if not ROLE_URLS:
        raise SystemExit(
            "ROLE_URLS is empty. Add one or more role page URLs at the top of "
            "this script to say which roles should receive the permissions."
        )

    # Step 1: pull the role ID off the end of each URL up front, so a bad paste
    # is caught before we sign in or change anything.
    role_ids = []
    for role_url in ROLE_URLS:
        role_ids.append(role_id_from_url(role_url))

    # Turn the flat permission list into policies grouped by domain and entity
    # once, up front, so every role is checked and updated with the same set.
    actions_by_key = group_actions_by_domain_and_entity(PERMISSIONS_TO_ADD)

    print("Checking %d permission(s) across %d domain/entity group(s) for %d role(s)."
          % (len(PERMISSIONS_TO_ADD), len(actions_by_key), len(role_ids)))

    auth_api = build_apis()

    # Step 2: read each role once, with its current permissions. We reuse these
    # same role objects for the preview and the save, so we never fetch a role
    # twice.
    roles = []
    for role_id in role_ids:
        roles.append(get_role_with_permissions(auth_api, role_id))

    # Step 3: work out what each role would gain, without changing anything yet.
    # This is the read-only part of the run and feeds the preview below.
    plan_by_role = []
    for role in roles:
        new_permissions = plan_new_permissions_for_role(role, actions_by_key)
        plan_by_role.append((role, new_permissions))

    # Step 4: show the preview. If nothing would change, stop here; there is
    # nothing to confirm or save.
    anything_would_change = preview_changes(plan_by_role)
    if not anything_would_change:
        return

    # Step 5: ask you to confirm. The message lists the permissions once and
    # then the roles that will receive them, right in the dialog, so you can
    # check the whole plan there. This is the only gate before we save, so a
    # "no" here leaves every role exactly as it was.
    roles_to_change = []
    for role, new_permissions in plan_by_role:
        if new_permissions:
            roles_to_change.append(role)

    question = format_plan_for_confirm(roles_to_change)
    if not ask_to_confirm(question, "Add Permissions to Roles"):
        raise SystemExit("Stopped at your request. No roles were changed.")

    # Step 6: save the changes. We only touch the roles that would gain
    # something, and we collect the names that actually saved so the summary is
    # honest about what changed.
    updated_role_names = []
    for role, new_permissions in plan_by_role:
        if not new_permissions:
            continue
        was_updated = apply_permissions_to_one_role(auth_api, role, actions_by_key)
        if was_updated:
            updated_role_names.append(role.name)

    # Step 7: print one final summary of what was added and where.
    print_summary(updated_role_names)


def print_summary(updated_role_names):
    """Print one final summary of what was added and to which roles.

    Lists the permissions from PERMISSIONS_TO_ADD once, then names the roles
    that were changed. Prints a short note instead when, despite the confirm,
    no role ended up changing (for example if every save failed).
    """
    if not updated_role_names:
        print("\nNo roles were changed.")
        return

    print("\nYou have successfully added %d permission(s) to %d role(s)."
          % (len(PERMISSIONS_TO_ADD), len(updated_role_names)))

if __name__ == '__main__':
    main()