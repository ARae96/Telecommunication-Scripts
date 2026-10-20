# =============================================================================
# Genesys Cloud - Merge One User's Role Permissions Into a Single Role
# =============================================================================
# Reads all the roles granted to one person (the source user), collects the
# permission policies from those roles, and copies the full combined set onto
# one target role. The idea is to roll up everything the source user can do
# into a single role you can then hand to other people.
#
# How it works, in plain terms:
#   1. We read the source user's roles. Genesys gives us the role IDs the user
#      has, one per grant.
#   2. For each role, we read the role itself to get its permission policies. A
#      permission policy is one block of access: a domain (like "routing"), an
#      entity inside that domain (like "queue"), and the set of actions allowed
#      on it (like "view" or "edit").
#   3. We merge all those policies into one set. Two policies for the same
#      domain and entity are combined into one, and their action lists are
#      joined so no action is lost.
#   4. We build a blacklist from the roles listed in ROLE_BLACKLIST. These are
#      the baseline roles every user already has (for example, the default
#      employee role), so their permissions should never be copied onto the
#      target role. We read each blacklist role and collect every action it
#      grants, keyed by domain and entity.
#   5. We subtract the blacklist from the merged set. For each permission the
#      blacklist covers, we remove those actions from the merged policy. If a
#      policy loses all of its actions, we drop the whole policy. What is left
#      is everything the source user can do that the baseline roles do not
#      already grant.
#   6. We write the subtracted set onto the target role (new_role).
#
# A role update needs the role's name, so we read the target role first and
# keep its current name and description. We only replace its permission
# policies.
#
# Retired permissions: older roles can still carry an action that Genesys has
# since retired, like 'searchAny' on quality/evaluation or 'access' on
# recording/recording. Reading that action back is fine, but writing it onto
# the target role fails with a 400 such as "The actions 'access' are not
# allowed for domain 'recording', entity name 'recording'". Rather than list
# every dead action by hand, the write step reacts to the error: it reads which
# actions Genesys rejected, drops just those from the policy set, and tries the
# write again. It keeps doing this until the write succeeds or there is nothing
# left to drop. Every action it removes is collected and printed in a summary
# at the end of the run, so you have a clean list of permissions to remove from
# the source roles by hand.
#
# Safety: this script changes a Genesys role, so it uses a DRY_RUN flag that
# defaults to True. On a dry run it only reads and prints the policies it would
# write, each line marked with a [DRY-RUN] prefix. Set DRY_RUN to False to
# actually write the change to the target role. Leave it True until you have
# reviewed the dry-run output.
#
# Run locally with:
#   pip install -r requirements.txt
# and a populated .env (GENESYS_CLOUD_CLIENT_ID / GENESYS_CLOUD_CLIENT_SECRET).
# =============================================================================


# --- Imports -----------------------------------------------------------------
import json
import os
import re

import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from dotenv import load_dotenv


# --- Configuration -----------------------------------------------------------
# The person whose roles we read and roll up. Enter the user ID by hand. Do not
# add a trailing slash; the ID is used as-is in the API call.
source_user = ''

# Baseline roles every user already has, used as a blacklist. We read these
# roles, collect every action they grant, and remove those actions from the
# merged set before writing. The point is that these roles are handed to all
# users already, so their permissions should never be duplicated onto the
# target role. Enter the role IDs by hand. These roles are still read; we use
# their permissions as the thing to subtract, not as roles to ignore.
ROLE_BLACKLIST = [
    #'4ab1c48a-5a6b-4962-a661-f5b4053cdbfe', # Communicate-User
    #'25e1a293-aaa0-4fdd-a15a-90955dc7fb13', # Purecloud User
    '4ab1c48a-5a6b-4962-a661-f5b4053cdbfe', # Employee
]

# The role we write the merged permissions onto. Enter the role ID by hand.
new_role = ''

# The most times we will retry the role write while dropping retired actions.
# Each failed write tells us about one permission's bad actions, so we retry,
# drop them, and write again. This cap just stops a runaway loop if Genesys
# ever returns an error we cannot act on. In practice only a handful of
# permissions are ever retired, so the real number of retries is small.
MAX_WRITE_RETRIES = 50

# Safety switch. While this is True the script only reads and prints what it
# would write, and makes no change in Genesys. Set it to False to actually
# write the merged policies onto the target role. Leave it True until you have
# reviewed the dry-run output.
DRY_RUN = False


# --- Authentication ----------------------------------------------------------
def build_apis():
    """Sign in to Genesys Cloud and return the API client this script needs.

    Reads GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET from the .env
    file at the workspace root (one folder up from this script). Stops the
    script with a helpful message if either value is missing. Returns the
    AuthorizationApi client, which covers both reading roles and updating a
    role.
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
def get_source_role_ids(authorization_api, user_id):
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
        role_id = getattr(role, 'id', None)
        # Keep each role once, even when the user holds it in several divisions.
        if role_id and role_id not in seen:
            seen.add(role_id)
            role_ids.append(role_id)
    return role_ids


def get_role_permission_policies(authorization_api, role_id):
    """Return the permission policies for one role.

    The grant list from the source user gives us only role IDs, not the
    policies inside each role. So for every role we keep, we read the role
    itself here to get its permission policies.

    Returns a list of DomainPermissionPolicy objects. Returns an empty list if
    the read fails or the role has no policies, so one bad role does not stop
    the whole run.
    """
    try:
        # Genesys API call: AuthorizationApi.get_authorization_role - reads one
        # role, including its permission policies.
        role = authorization_api.get_authorization_role(role_id)
    except ApiException as e:
        print("Exception reading role %s: %s\n" % (role_id, e))
        return []
    return getattr(role, 'permission_policies', None) or []


def policy_key(policy):
    """Return the (domain, entity) pair that identifies a permission policy.

    We treat a permission policy as "the same permission" when it covers the
    same domain and the same entity inside that domain. For example, the
    "routing" domain and the "queue" entity. The actions allowed on it can
    differ between roles, and we join those actions in the merge step. Returns
    a (domain, entity_name) tuple we can use as a dictionary key.
    """
    domain = getattr(policy, 'domain', None)
    entity_name = getattr(policy, 'entity_name', None)
    return (domain, entity_name)


def parse_not_allowed_actions(api_exception):
    """Read which actions Genesys rejected out of a 400 error, if it is that kind.

    When we try to write a retired action, Genesys returns a 400 whose message
    reads like "The actions 'access' are not allowed for domain 'recording',
    entity name 'recording'". This function pulls those pieces out so the write
    step knows exactly what to drop and try again.

    Returns a (domain, entity_name, actions) tuple, where actions is a list of
    the action names Genesys named (one message can list more than one, comma
    separated). Returns None when the error is not this "actions not allowed"
    kind, so the caller knows it cannot fix this one by dropping actions.
    """
    # The SDK puts the raw JSON response on the exception's 'body' attribute.
    body = getattr(api_exception, 'body', None)
    if not body:
        return None

    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return None

    message = parsed.get('message') or ''

    # Match the exact shape Genesys uses for this error. The actions part can
    # list several names, so we capture the whole quoted group and split it
    # below. Example: "The actions 'view', 'edit' are not allowed for domain
    # 'recording', entity name 'recording'".
    pattern = (
        r"The actions? (?P<actions>.+?) are not allowed for domain "
        r"'(?P<domain>[^']+)', entity name '(?P<entity>[^']+)'"
    )
    match = re.search(pattern, message)
    if not match:
        return None

    # Pull each quoted action name out of the captured group so a message that
    # lists several actions is handled in one pass.
    actions = re.findall(r"'([^']+)'", match.group('actions'))
    domain = match.group('domain')
    entity_name = match.group('entity')
    return (domain, entity_name, actions)


def drop_actions_from_policies(policies, domain, entity_name, actions_to_drop):
    """Remove the named actions from the matching policy, in place.

    Finds the policy in the merged list that covers the given domain and
    entity, then removes each action in actions_to_drop from its action set.
    This is how we react to a Genesys "actions not allowed" error: we take the
    exact domain, entity, and actions it named and strip them before retrying
    the write.

    Returns a list of the actions it actually removed, so the caller can record
    them for the end-of-run summary. Returns an empty list if nothing matched,
    which tells the caller it cannot fix this error by dropping actions.
    """
    removed = []
    for policy in policies:
        if policy_key(policy) != (domain, entity_name):
            continue

        actions = getattr(policy, 'action_set', None) or []
        kept_actions = []
        for action in actions:
            if action in actions_to_drop:
                removed.append(action)
            else:
                kept_actions.append(action)
        policy.action_set = kept_actions

    return removed


def merge_action_sets(first_actions, second_actions):
    """Join two action lists into one sorted list with no repeats.

    Each permission policy has an action set, which is the list of actions
    allowed (like "view", "edit", or the wildcard "*"). When two roles cover
    the same domain and entity, we combine their actions so no allowed action
    is lost. Returns a new sorted list of action strings.
    """
    combined = set(first_actions or [])
    for action in second_actions or []:
        combined.add(action)
    return sorted(combined)


# --- Steps -------------------------------------------------------------------
def collect_merged_policies(authorization_api, role_ids):
    """Collect and merge the permission policies from a list of roles.

    Takes a list of role IDs. Reads each role's permission policies and merges
    them into one set. Two policies for the same domain and entity are combined
    into one, and their action lists
    are joined so no action is lost. All other fields (named resources,
    condition flags, condition tree) are kept from the first policy we see for
    that domain and entity.

    Returns a list of DomainPermissionPolicy objects, one per unique domain and
    entity across all the roles.
    """
    # Keyed by (domain, entity_name) so we keep one policy per permission and
    # grow its action set as we see the same permission in other roles.
    merged_by_key = {}

    for role_id in role_ids:
        policies = get_role_permission_policies(authorization_api, role_id)
        for policy in policies:
            key = policy_key(policy)
            existing = merged_by_key.get(key)
            if existing is None:
                # First time we have seen this permission. Keep the policy
                # as-is; later roles with the same permission only add actions.
                merged_by_key[key] = policy
            else:
                # Same permission from another role. Join the two action lists
                # so the merged role allows every action either role allowed.
                existing.action_set = merge_action_sets(
                    getattr(existing, 'action_set', None),
                    getattr(policy, 'action_set', None),
                )

    return list(merged_by_key.values())


def build_blacklist(authorization_api, blacklist_role_ids):
    """Collect every action the blacklist roles grant, keyed by permission.

    These are the baseline roles every user already has (listed in
    ROLE_BLACKLIST), so their permissions should never be copied onto the
    target role. We read each one and record which actions it grants for each
    domain and entity, so the next step can subtract them from the merged set.

    The wildcard action "*" means "every action for this permission". When a
    blacklist role grants "*" on a domain and entity, we treat that as blocking
    the whole permission, so the subtract step drops it entirely.

    Returns a dictionary keyed by (domain, entity_name). Each value is a set of
    action strings to block. A value that contains "*" means block the whole
    permission. Returns an empty dictionary when the blacklist is empty.
    """
    blacklist_by_key = {}

    for role_id in blacklist_role_ids:
        policies = get_role_permission_policies(authorization_api, role_id)
        for policy in policies:
            key = policy_key(policy)
            actions = getattr(policy, 'action_set', None) or []
            blocked_actions = blacklist_by_key.setdefault(key, set())
            for action in actions:
                blocked_actions.add(action)

    return blacklist_by_key


def subtract_blacklist(merged_policies, blacklist_by_key):
    """Remove the blacklisted actions from the merged policies.

    Walks the merged policies and, for each one the blacklist covers, removes
    the blocked actions from its action set. The wildcard "*" in the blacklist
    blocks the whole permission, so a policy matched by a wildcard is dropped
    outright. A policy that loses all of its actions is also dropped, because a
    permission with no actions grants nothing.

    Returns a (kept_policies, removed_items) pair. kept_policies is the list of
    policies to write to the target role. removed_items is a list of
    (domain, entity_name, action) tuples describing every action removed, so
    the caller can print a summary of what the blacklist took out.
    """
    kept_policies = []
    removed_items = []

    for policy in merged_policies:
        key = policy_key(policy)
        domain, entity_name = key
        blocked_actions = blacklist_by_key.get(key)

        # This permission is not on the blacklist at all, so keep it unchanged.
        if not blocked_actions:
            kept_policies.append(policy)
            continue

        actions = getattr(policy, 'action_set', None) or []

        # A wildcard on the blacklist blocks the whole permission, so we drop
        # the policy and record each action it would have granted.
        if '*' in blocked_actions:
            for action in actions:
                removed_items.append((domain, entity_name, action))
            continue

        # Otherwise remove just the blocked actions and keep the rest.
        kept_actions = []
        for action in actions:
            if action in blocked_actions:
                removed_items.append((domain, entity_name, action))
            else:
                kept_actions.append(action)

        # Drop the whole policy if nothing is left, since a permission with no
        # actions grants nothing and does not belong on the role.
        if kept_actions:
            policy.action_set = kept_actions
            kept_policies.append(policy)

    return (kept_policies, removed_items)


def update_target_role(authorization_api, role_id, merged_policies):
    """Write the merged permission policies onto the target role.

    A role update must include the role's name, so we read the target role
    first and reuse its current name and description. We only replace its
    permission policies with the merged set; everything else about the role
    stays the same.

    Retired permissions: a write can fail with a 400 saying some actions are
    "not allowed" for a domain and entity, because an older role carried an
    action Genesys has since retired. When that happens we read which actions
    it named, drop just those from the policy set, and write again. We keep
    doing this until the write succeeds or there is nothing left to drop, so
    one dead action does not sink the whole run.

    Prints what it would do and makes no change when DRY_RUN is True. Returns a
    list of (domain, entity_name, action) tuples for every action it had to
    drop to get the write to succeed, so the caller can print a cleanup list at
    the end. Returns an empty list when nothing had to be dropped.
    """
    dropped_permissions = []

    try:
        # Read the target role first so we can keep its name and description.
        # The update API requires the name, so we must not send it empty.
        target_role = authorization_api.get_authorization_role(role_id)
    except ApiException as e:
        print("Exception reading the target role %s: %s\n" % (role_id, e))
        return dropped_permissions

    role_name = getattr(target_role, 'name', None)
    role_description = getattr(target_role, 'description', None)

    if DRY_RUN:
        print("[DRY-RUN] Would set %d permission policy(ies) on role '%s' (%s):"
              % (len(merged_policies), role_name, role_id))
        for policy in merged_policies:
            domain = getattr(policy, 'domain', None)
            entity_name = getattr(policy, 'entity_name', None)
            actions = getattr(policy, 'action_set', None) or []
            print("            %s / %s -> actions: %s"
                  % (domain, entity_name, ', '.join(actions)))
        return dropped_permissions

    body = PureCloudPlatformClientV2.DomainOrganizationRoleUpdate()
    body.name = role_name
    body.description = role_description
    body.permission_policies = merged_policies

    # Try the write, and if Genesys rejects a retired action, drop it and try
    # again. We cap the attempts so a 400 we cannot act on does not loop here
    # forever.
    for attempt in range(1, MAX_WRITE_RETRIES + 1):
        try:
            # Genesys API call: AuthorizationApi.put_authorization_role -
            # updates the target role with the merged permission policies.
            authorization_api.put_authorization_role(role_id, body)
            print("Set %d permission policy(ies) on role '%s' (%s)."
                  % (len(merged_policies), role_name, role_id))
            return dropped_permissions
        except ApiException as e:
            # See if this is the "actions not allowed" error we can fix by
            # dropping the named actions. If it is not, we cannot recover.
            parsed = parse_not_allowed_actions(e)
            if parsed is None:
                print("Exception when calling AuthorizationApi->put_authorization_role: %s\n" % e)
                return dropped_permissions

            domain, entity_name, actions_to_drop = parsed
            removed = drop_actions_from_policies(
                merged_policies, domain, entity_name, actions_to_drop
            )

            # If we could not actually remove anything, retrying would just hit
            # the same error, so we stop here instead of looping.
            if not removed:
                print("Genesys rejected actions %s on %s / %s, but none of them "
                      "were found in the merged policies to drop. Stopping."
                      % (', '.join(actions_to_drop), domain, entity_name))
                return dropped_permissions

            for action in removed:
                print("Dropping retired action '%s' from %s / %s and retrying "
                      "the write." % (action, domain, entity_name))
                dropped_permissions.append((domain, entity_name, action))

            # The body points at the same policy objects we just changed, so
            # the next attempt sends the trimmed action sets.

    # We used up every retry and the write still failed. Tell the caller
    # plainly rather than letting it look like the write succeeded.
    print("Gave up after %d attempts; the target role was not updated. See the "
          "errors above." % MAX_WRITE_RETRIES)
    return dropped_permissions


# --- Main --------------------------------------------------------------------
def main():
    """Roll up the source user's role permissions onto the target role.

    Step 1: Read the roles granted to the source user.
    Step 2: Read each role's permission policies and merge them into one set,
            joining the actions when two roles share the same permission.
    Step 3: Build a blacklist from the roles in ROLE_BLACKLIST, collecting every
            action those baseline roles grant.
    Step 4: Subtract the blacklist from the merged set, so no permission the
            baseline roles already grant is copied onto the target role.
    Step 5: Write the subtracted set onto the target role (new_role). If Genesys
            rejects any retired actions, drop them and retry, then print a
            summary of everything dropped so you can clean up the source roles.

    While DRY_RUN is True this only reads and prints the policies it would
    write. The reads still run, so the dry-run output shows exactly what would
    be applied.
    """
    authorization_api = build_apis()

    if DRY_RUN:
        print("DRY_RUN is True: reading only, no changes will be made in Genesys.\n")

    # Step 1: read the source user's roles.
    source_role_ids = get_source_role_ids(authorization_api, source_user)
    if not source_role_ids:
        raise SystemExit(
            "The source user has no roles, or the read failed. Check the "
            "'source_user' ID and that the read above did not fail."
        )

    # Step 2: read and merge the permission policies from every one of the
    # source user's roles. We merge all of them; the blacklist step below is
    # what removes the baseline permissions, not this step.
    merged_policies = collect_merged_policies(authorization_api, source_role_ids)
    print("Source user has %d role(s), merged into %d unique permission "
          "policy(ies)." % (len(source_role_ids), len(merged_policies)))

    if not merged_policies:
        raise SystemExit(
            "The source user's roles had no permission policies to merge. "
            "Nothing was written to the target role."
        )

    # Step 3: build the blacklist from the baseline roles. We collect every
    # action those roles grant so we can subtract them next.
    blacklist_by_key = build_blacklist(authorization_api, ROLE_BLACKLIST)
    print("Built a blacklist from %d baseline role(s) covering %d permission(s)."
          % (len(ROLE_BLACKLIST), len(blacklist_by_key)))

    # Step 4: subtract the blacklist from the merged set. This removes any
    # action the baseline roles already grant, and drops a policy that loses
    # all of its actions.
    kept_policies, removed_by_blacklist = subtract_blacklist(merged_policies, blacklist_by_key)
    print("After removing baseline permissions: %d permission policy(ies) left, "
          "%d action(s) removed by the blacklist.\n"
          % (len(kept_policies), len(removed_by_blacklist)))

    if not kept_policies:
        raise SystemExit(
            "Every permission was removed by the blacklist, so there is nothing "
            "to write. Check ROLE_BLACKLIST against the source user's roles."
        )

    # Step 5: write the subtracted set onto the target role. This drops any
    # retired actions Genesys rejects and returns the list of what it dropped.
    dropped_permissions = update_target_role(authorization_api, new_role, kept_policies)

    # Print a cleanup summary so you have a clear list of permissions to remove
    # from the source roles by hand. We print one line per dropped action.
    if dropped_permissions:
        print("\nRetired actions dropped to let the write succeed. Remove these "
              "from the source roles by hand:")
        for domain, entity_name, action in dropped_permissions:
            print("    %s / %s -> %s" % (domain, entity_name, action))
    else:
        print("\nNo retired actions had to be dropped.")


if __name__ == '__main__':
    main()
