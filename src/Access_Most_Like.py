# =============================================================================
# Genesys Cloud - "Access Most Like" (AML) Access Copy - v5
# =============================================================================
# Makes one person's Genesys Cloud access match another person's exactly. AML
# stands for "Access Most Like". You pick the person whose access is already
# correct (the aml) and the person who should match them (the target). The
# script then makes the target match the aml across six things:
#   - the home division (the division that owns the user as an object)
#   - roles and the division each role is granted in
#   - groups
#   - ACD (Automatic Call Distribution) skills, including each skill's
#     proficiency rating
#   - queues the person is joined to
#   - utilization settings (how many interactions of each media type the agent
#     can handle at once)
#
# You enter two user IDs by hand near the top of the file: the person to copy
# from (aml) and the person to copy onto (target). The script signs in to
# Genesys Cloud, clears the target's access, and builds it back up to match the
# aml.
#
# Please note: this REPLACES the target's access. It first removes the roles,
# groups, skills, and queue memberships the target has now. Then it applies only
# what the aml has, and it also matches the target's utilization to the aml's.
# Anything the target had that the aml does not have is removed, and this is on
# purpose. A new hire starts with nothing, so there is nothing to lose. An
# internal transfer should keep only the access for their new job, not the
# access from their old one. Either way, no one keeps access their current role
# does not need.
#
# How groups and roles fit together:
#   - A role given straight to a person is a "direct" role. When we read the
#     aml's roles, we get only their direct roles.
#   - A role can also be attached to a group. Anyone in that group gets the role
#     just by being a member. A role like this is stored on the group, not on
#     the person, so it never shows up in the person's direct roles.
#   The two sets never overlap. So we can copy the aml's direct roles and add
#   the target to the aml's groups without granting anything twice. The direct
#   roles come from the copy. The group roles come from being in the group.
#
# Why queues are joined last:
#   A person can only be joined to a queue they already have access to, and that
#   access comes from their roles and groups. So we must apply roles and groups
#   first, then join queues. Genesys may also take a moment to apply the new
#   role and group access, so a queue join right after can be ignored if the
#   access has not caught up yet. The script joins the queues, checks which
#   joins the API accepted, and warns about any it did not, instead of assuming
#   they all worked.
#
# Safety: this script changes Genesys, so it uses a DRY_RUN flag that defaults
# to True. On a dry run it only reads and prints the changes it would make, each
# marked with a [DRY-RUN] prefix. Set DRY_RUN = False to actually apply them.
#
# Run locally with:
#   pip install -r requirements.txt
# and a populated .env (GENESYS_CLOUD_CLIENT_ID / GENESYS_CLOUD_CLIENT_SECRET).
# =============================================================================


# --- Imports -----------------------------------------------------------------
import os

import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from dotenv import load_dotenv


# --- Configuration -----------------------------------------------------------
# Enter the two user IDs by hand before running. "aml" is the person whose
# access is already correct and that we copy from. "target" is the person we
# make match the aml (a new hire or an internal transfer).
aml = '25e322b0-5a98-44a3-bc45-b45eb45c6d7e'
target = '39e0b085-95a0-4c45-ab72-eb5b10f57c2b'

# Safety switch. While this is True the script only reads and prints what it
# would do, and makes no change in Genesys. Set it to False to actually apply
# the changes. Leave it True until you have reviewed the dry-run output.
DRY_RUN = False

# The object type the division-assign API expects when we move a user into a
# division. The API accepts several object types; we only ever move users.
DIVISION_OBJECT_TYPE_USER = 'USER'


# --- Authentication ----------------------------------------------------------
def build_apis():
    """Sign in to Genesys Cloud and return the API clients this script needs.

    Reads GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET from the .env
    file next to this script. Stops the script with a helpful message if either
    value is missing. Returns the clients in this order: (AuthorizationApi,
    UsersApi, GroupsApi, RoutingApi).

    Queues and skills are handled through UsersApi, not RoutingApi. We still
    need RoutingApi for the utilization step, because the read, apply, and
    reset-to-default utilization calls all live on RoutingApi.
    """
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
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
    return (
        PureCloudPlatformClientV2.AuthorizationApi(apiclient),
        PureCloudPlatformClientV2.UsersApi(apiclient),
        PureCloudPlatformClientV2.GroupsApi(apiclient),
        PureCloudPlatformClientV2.RoutingApi(apiclient),
    )


# --- Helpers -----------------------------------------------------------------
def get_home_division_and_group_ids(users_api, user_id):
    """Return a person's home division ID and the IDs of their groups.

    Reads the person once with the "groups" expand. From that single read we
    pull two things: the home division (the division that owns the user as an
    object) and the groups the person belongs to. Returns a tuple of
    (home_division_id, list of group ID strings).

    We read both from one call on purpose. The home division is always on the
    user record, and the "groups" expand adds the groups to that same record, so
    one call covers both and saves a second round trip.

    home_division_id is None if the call fails or the user has no division set.
    The group list is empty if the call fails or the person is in no groups.

    Please note: the "groups" expand is best effort, so Genesys does not promise
    to return it. If the group list comes back empty, we cannot tell whether the
    person is really in no groups or the expand just did not load. The caller
    prints the count it found, so you can check it against what you expect in
    the dry-run output before you apply anything.
    """
    home_division_id = None
    group_ids = []

    try:
        user = users_api.get_user(user_id, expand=['groups'])
        division = getattr(user, 'division', None)
        if division is not None:
            home_division_id = getattr(division, 'id', None)
        for group in getattr(user, 'groups', None) or []:
            if getattr(group, 'id', None):
                group_ids.append(group.id)
    except ApiException as e:
        print("Exception when calling UsersApi->get_user: %s\n" % e)
    return (home_division_id, group_ids)


def get_role_division_pairs(authorization_api, user_id):
    """Return a person's direct role-and-division pairs.

    Reads the person's authorization grants from Genesys Cloud. Each grant
    pairs one role with one division, so a role the person has in two divisions
    shows up as two grants. We keep each pairing on its own and return a list of
    (role_id, division_id) tuples.

    This returns only direct roles, meaning roles given straight to the person.
    It leaves out roles the person gets from a group, because those are stored
    on the group, not on the person.

    Returns an empty list if the call fails, so the caller can decide what to do
    next. Skips any grant that is missing its role or division, so one bad entry
    does not stop the whole run.
    """
    pairs = []

    try:
        response = authorization_api.get_authorization_subject(user_id, include_duplicates=False)
        for grant in response.grants or []:
            if not grant.role or not grant.division:
                continue
            pairs.append((grant.role.id, grant.division.id))
    except ApiException as e:
        print("Exception when calling AuthorizationApi->get_authorization_subject: %s\n" % e)
    return pairs


def get_skill_pairs(users_api, user_id):
    """Return a person's ACD skills as (skill_id, proficiency) pairs.

    Reads the person's routing skills from Genesys Cloud. Each skill has a
    proficiency, which is a rating from 0.0 to 5.0 for how strong the person is
    at that skill. We keep the proficiency so the target matches the aml's skill
    level, not just the list of skills. Returns a list of (skill_id,
    proficiency) tuples.

    Returns an empty list if the call fails. Skips any skill missing its ID so
    one bad entry does not stop the whole run. Defaults a missing proficiency to
    0.0, because the apply API requires a proficiency on every skill.
    """
    pairs = []

    try:
        response = users_api.get_user_routingskills(user_id, page_size=100)
        for skill in response.entities or []:
            skill_id = getattr(skill, 'id', None)
            if not skill_id:
                continue
            proficiency = getattr(skill, 'proficiency', None)
            if proficiency is None:
                proficiency = 0.0
            pairs.append((skill_id, proficiency))
    except ApiException as e:
        print("Exception when calling UsersApi->get_user_routingskills: %s\n" % e)
    return pairs


def get_queue_ids(users_api, user_id):
    """Return the IDs of the queues a person is currently joined to.

    Reads the person's queues from Genesys Cloud, one page at a time, and
    returns a list of queue ID strings. Returns an empty list if the call fails
    or the person is in no queues.
    """
    queue_ids = []

    try:
        page_number = 1
        while True:
            response = users_api.get_user_queues(user_id, page_size=100, page_number=page_number)
            for queue in response.entities or []:
                if getattr(queue, 'id', None):
                    queue_ids.append(queue.id)
            # Stop once we have read the last page. page_count is the total
            # number of pages Genesys has for this person's queues.
            if page_number >= (getattr(response, 'page_count', 0) or 0):
                break
            page_number += 1
    except ApiException as e:
        print("Exception when calling UsersApi->get_user_queues: %s\n" % e)
    return queue_ids


def get_custom_utilization(routing_api, user_id):
    """Return a person's custom utilization settings, or None if they use the default.

    Utilization settings control how many interactions of each media type an
    agent can handle at once. An agent either has their own custom settings or
    they inherit the organization-wide default.

    The read always returns a value, even when the agent is on the default, so
    we check the "level" field to tell the two apart. A level of "Agent" means
    the agent has custom settings; anything else (such as "Organization") means
    they are on the org default. We only return settings when the level is
    "Agent".

    Returns the full utilization response when the person has custom settings.
    Returns None when they are on the org default, or when the read fails. The
    caller treats None as "match the default", not as an error.
    """
    try:
        response = routing_api.get_routing_user_utilization(user_id)
    except ApiException as e:
        print("Exception when calling RoutingApi->get_routing_user_utilization: %s\n" % e)
        return None

    level = getattr(response, 'level', None)
    if level == 'Agent':
        return response
    # Any other level means the person is on the org-wide default, so there are
    # no custom settings to copy.
    return None


# --- Steps -------------------------------------------------------------------
def set_home_division(authorization_api, user_id, division_id):
    """Move a person into the given home division (Step 2).

    Genesys does not let you set the home division through the user update API,
    so we use the division-assign API instead. It moves a list of objects into a
    division; here that list is just this one user. There is nothing to clear
    first, because a user always has exactly one home division, so this is a
    single move rather than a clear-then-set.

    Does nothing if division_id is empty, so a failed read of the aml's division
    never moves the target by mistake. Prints what it does. Makes no change and
    prints a note if DRY_RUN is True. Prints a message if the call fails.
    """
    if not division_id:
        print("No home division found on the aml, so the target's home division was left alone.")
        return

    if DRY_RUN:
        print("[DRY-RUN] Would move %s into home division %s" % (user_id, division_id))
        return

    try:
        authorization_api.post_authorization_division_object(
            division_id, DIVISION_OBJECT_TYPE_USER, [user_id]
        )
        print("Moved %s into home division %s" % (user_id, division_id))
    except ApiException as e:
        print("Exception when calling AuthorizationApi->post_authorization_division_object: %s\n" % e)


def remove_from_groups(groups_api, user_id, group_ids):
    """Remove a person from each of the given groups (Step 1, groups half).

    Genesys has no way to remove a person from many groups at once, so we remove
    them from one group at a time. The remove API takes a comma separated list
    of user IDs, and we pass just this one person each time. We catch errors per
    group and keep going, so one group that fails does not stop the rest.

    Prints what it does for each group. Makes no change and prints a note for
    each group if DRY_RUN is True.
    """
    for group_id in group_ids:
        if DRY_RUN:
            print("[DRY-RUN] Would remove %s from group %s" % (user_id, group_id))
            continue
        try:
            groups_api.delete_group_members(group_id, user_id)
            print("Removed %s from group %s" % (user_id, group_id))
        except ApiException as e:
            print("Exception removing %s from group %s: %s\n" % (user_id, group_id, e))


def unjoin_queues(users_api, user_id, queue_ids):
    """Unjoin a person from each of the given queues (Step 1, queues half).

    Builds one request that marks each queue as not joined, then sends it. The
    join API takes a list of UserQueue entries, each with a queue ID and a
    joined flag; we set joined to False for every queue the person is in now.

    Prints what it does. Makes no change and prints a note if DRY_RUN is True.
    Prints a message if the call fails. Does nothing if the list is empty.
    """
    if not queue_ids:
        return

    if DRY_RUN:
        print("[DRY-RUN] Would unjoin %s from %d queue(s)" % (user_id, len(queue_ids)))
        return

    body = []
    for queue_id in queue_ids:
        user_queue = PureCloudPlatformClientV2.UserQueue()
        user_queue.id = queue_id
        user_queue.joined = False
        body.append(user_queue)

    try:
        users_api.patch_user_queues(user_id, body)
        print("Unjoined %s from %d queue(s)" % (user_id, len(queue_ids)))
    except ApiException as e:
        print("Exception when calling UsersApi->patch_user_queues (unjoin): %s\n" % e)


def add_to_groups(groups_api, user_id, group_ids):
    """Add a person to each of the given groups (Step 3).

    Adding a member needs the group's current version. The version acts as a
    lock so two edits cannot overwrite each other. For each group we read the
    group to get its version, then add the person with that version. If the
    group changed between the read and the add, the call fails. This is rare for
    this script.

    We catch errors per group and keep going, so one group that fails does not
    stop the rest. Prints what it does for each group. Makes no change and
    prints a note for each group if DRY_RUN is True.
    """
    for group_id in group_ids:
        if DRY_RUN:
            print("[DRY-RUN] Would add %s to group %s" % (user_id, group_id))
            continue
        try:
            # Read the group first so we have its current version for the add.
            group = groups_api.get_group(group_id)
            body = PureCloudPlatformClientV2.GroupMembersUpdate()
            body.member_ids = [user_id]
            body.version = getattr(group, 'version', None)
            groups_api.post_group_members(group_id, body)
            print("Added %s to group %s" % (user_id, group_id))
        except ApiException as e:
            print("Exception adding %s to group %s: %s\n" % (user_id, group_id, e))


def apply_role_division_pairs(authorization_api, user_id, role_division_pairs):
    """Give a person exactly the given direct role-and-division pairs (Step 4).

    Builds the body the bulk-replace API wants: a RoleDivisionGrants object
    whose grants field is a list of RoleDivisionPair objects, one per pair.

    Bulk-replace swaps all of the person's direct roles for the pairs we pass.
    So this one call both clears the target's old direct roles and sets the new
    ones, and we do not need a separate clear step. An empty list would clear
    the person's direct roles.

    Prints what it does. Makes no change and prints a note if DRY_RUN is True.
    Prints a message and makes no change if the call fails.
    """
    if DRY_RUN:
        print("[DRY-RUN] Would set %d direct role grant(s) on %s:" % (len(role_division_pairs), user_id))
        for role_id, division_id in role_division_pairs:
            print("            role %s in division %s" % (role_id, division_id))
        return

    pairs = []
    for role_id, division_id in role_division_pairs:
        pair = PureCloudPlatformClientV2.RoleDivisionPair()
        pair.role_id = role_id
        pair.division_id = division_id
        pairs.append(pair)

    body = PureCloudPlatformClientV2.RoleDivisionGrants()
    body.grants = pairs

    try:
        authorization_api.post_authorization_subject_bulkreplace(user_id, body)
        print("Set %d direct role grant(s) on %s" % (len(pairs), user_id))
    except ApiException as e:
        print("Exception when calling AuthorizationApi->post_authorization_subject_bulkreplace: %s\n" % e)


def apply_skills(users_api, user_id, skill_pairs):
    """Give a person exactly the given ACD skills and proficiencies (Step 5).

    Builds a list of skill entries, each with a skill ID and a proficiency, then
    sends it to the bulk routing-skills API. That API replaces all of the
    person's current skills with the list we pass, so this one call both clears
    the target's old skills and sets the new ones. An empty list clears the
    person's skills.

    Prints what it does. Makes no change and prints a note if DRY_RUN is True.
    Prints a message and makes no change if the call fails.
    """
    if DRY_RUN:
        print("[DRY-RUN] Would set %d skill(s) on %s:" % (len(skill_pairs), user_id))
        for skill_id, proficiency in skill_pairs:
            print("            skill %s at proficiency %s" % (skill_id, proficiency))
        return

    body = []
    for skill_id, proficiency in skill_pairs:
        skill = PureCloudPlatformClientV2.UserRoutingSkillPost()
        skill.id = skill_id
        skill.proficiency = proficiency
        body.append(skill)

    try:
        users_api.put_user_routingskills_bulk(user_id, body)
        print("Set %d skill(s) on %s" % (len(body), user_id))
    except ApiException as e:
        print("Exception when calling UsersApi->put_user_routingskills_bulk: %s\n" % e)


def join_queues(users_api, user_id, queue_ids):
    """Join a person to each of the given queues (Step 6).

    Builds one request that marks each queue as joined, then sends it. The join
    API takes a list of UserQueue entries, each with a queue ID and a joined
    flag; we set joined to True for every queue we want the target in.

    Please note: Genesys only joins a person to a queue they already have access
    to, and it drops any queue in the request they cannot access. It can also
    take a moment to apply the roles and groups from earlier steps, so a join
    sent right after may be dropped if that access has not caught up. So after
    the call we read the target's queues back and warn about any requested queue
    that did not take, instead of assuming every join worked.

    Prints what it does. Makes no change and prints a note if DRY_RUN is True.
    Prints a message if the call fails. Does nothing if the list is empty.
    """
    if not queue_ids:
        print("The aml is in no queues, so no queues were joined for the target.")
        return

    if DRY_RUN:
        print("[DRY-RUN] Would join %s to %d queue(s)" % (user_id, len(queue_ids)))
        return

    body = []
    for queue_id in queue_ids:
        user_queue = PureCloudPlatformClientV2.UserQueue()
        user_queue.id = queue_id
        user_queue.joined = True
        body.append(user_queue)

    try:
        users_api.patch_user_queues(user_id, body)
        print("Requested join of %s to %d queue(s)" % (user_id, len(body)))
    except ApiException as e:
        print("Exception when calling UsersApi->patch_user_queues (join): %s\n" % e)
        return

    # Read the queues back and warn about any the join did not apply. We cannot
    # trust the join response alone, because Genesys applies the change in the
    # background and drops queues the target has no access to.
    joined_now = set(get_queue_ids(users_api, user_id))
    missing = []
    for queue_id in queue_ids:
        if queue_id not in joined_now:
            missing.append(queue_id)

    if missing:
        print(
            "Warning: %d queue(s) did not take. The target may not have access "
            "to them yet, or the change may still be applying. Re-run the queue "
            "step shortly or check these queues by hand:" % len(missing)
        )
        for queue_id in missing:
            print("            %s" % queue_id)
    else:
        print("All %d requested queue(s) are now joined." % len(queue_ids))


def apply_utilization(routing_api, user_id, aml_utilization):
    """Make the target's utilization match the aml's (Step 7).

    There are two cases, and the caller decides which by what it passes in:

    1. The aml has custom utilization (aml_utilization is a response object).
       We copy those settings onto the target with a utilization update.
    2. The aml is on the org-wide default (aml_utilization is None). We reset
       the target to the org default too, so the two still match. The reset
       deletes the target's custom settings, which makes Genesys fall back to
       the org default.

    We always act on the target so the two end up the same. Leaving the target's
    old custom settings in place when the aml is on the default would leave them
    out of sync, which is the opposite of what this script is for.

    Prints what it does. Makes no change and prints a note if DRY_RUN is True.
    Prints a message and makes no change if the call fails.
    """
    # Case 2: the aml is on the org default, so reset the target to the default.
    if aml_utilization is None:
        if DRY_RUN:
            print("[DRY-RUN] Would reset %s to the org default utilization" % user_id)
            return
        try:
            routing_api.delete_routing_user_utilization(user_id)
            print("Reset %s to the org default utilization" % user_id)
        except ApiException as e:
            print("Exception when calling RoutingApi->delete_routing_user_utilization: %s\n" % e)
        return

    # Case 1: the aml has custom utilization, so copy it onto the target.
    if DRY_RUN:
        print("[DRY-RUN] Would copy the aml's custom utilization onto %s" % user_id)
        return

    body = PureCloudPlatformClientV2.UtilizationRequest()
    body.utilization = getattr(aml_utilization, 'utilization', None)
    body.max_inbound_calls = getattr(aml_utilization, 'max_inbound_calls', None)

    # The read returns label settings as response objects, but the update wants
    # request objects. The two share the fields we need, so we copy those fields
    # into request objects one label at a time.
    label_utilizations = getattr(aml_utilization, 'label_utilizations', None)
    if label_utilizations:
        request_labels = {}
        for label_id, label_setting in label_utilizations.items():
            request_label = PureCloudPlatformClientV2.LabelUtilizationRequest()
            request_label.maximum_capacity = getattr(label_setting, 'maximum_capacity', None)
            request_label.interrupting_label_ids = getattr(label_setting, 'interrupting_label_ids', None)
            request_labels[label_id] = request_label
        body.label_utilizations = request_labels

    try:
        routing_api.put_routing_user_utilization(user_id, body)
        print("Copied the aml's custom utilization onto %s" % user_id)
    except ApiException as e:
        print("Exception when calling RoutingApi->put_routing_user_utilization: %s\n" % e)


# --- Main --------------------------------------------------------------------
def main(aml_id, target_id):
    """Make the target's access match the aml's access exactly.

    Step 0: Stop early if either user ID is blank, so we never call the API
            with an empty ID.
    Step A: Read everything from the aml first: home division, groups, direct
            role-and-division pairs, skills, queues, and utilization. We read
            before we wipe so a bad aml ID or a failed read never leaves the
            target with nothing. Stop if the aml has no access worth copying.
    Step 1: Clean slate. Remove the target's groups and unjoin their queues.
            Roles and skills do not need a separate clear, because the apply
            steps below replace them in one call each.
    Step 2: Move the target into the aml's home division.
    Step 3: Add the target to the aml's groups.
    Step 4: Give the target the aml's direct role-and-division pairs (this
            replaces any the target had).
    Step 5: Give the target the aml's skills and proficiencies (this replaces
            any the target had).
    Step 6: Join the target to the aml's queues. This runs last of the access
            steps because a queue join needs the roles and groups from Steps 3
            and 4 to be in place first.
    Step 7: Match the target's utilization to the aml's. If the aml has custom
            utilization we copy it; if the aml is on the org default we reset
            the target to the default too. This step is independent of the
            others.

    While DRY_RUN is True this only reads and prints the changes it would make.
    The reads in Step A still run, so the dry-run output shows exactly what
    would be applied.
    """
    # Stop early if either ID is blank. Without this, a blank ID would fail
    # later at the API call with a confusing error instead of a clear one.
    if not aml_id or not target_id:
        raise SystemExit(
            "Set both 'aml' (copy from) and 'target' (copy onto) user IDs near "
            "the top of the script before running."
        )

    authorization_api, users_api, groups_api, routing_api = build_apis()

    if DRY_RUN:
        print("DRY_RUN is True: reading only, no changes will be made in Genesys.\n")

    # Step A: read everything from the aml first (read-only). Doing this before
    # we wipe the target means a bad aml ID or a failed read never leaves the
    # target with nothing. The home division and groups come from one read.
    aml_home_division_id, aml_group_ids = get_home_division_and_group_ids(users_api, aml_id)
    aml_role_division_pairs = get_role_division_pairs(authorization_api, aml_id)
    aml_skill_pairs = get_skill_pairs(users_api, aml_id)
    aml_queue_ids = get_queue_ids(users_api, aml_id)
    # None here means the aml is on the org default utilization, so Step 7 will
    # reset the target to the default rather than copy custom settings.
    aml_utilization = get_custom_utilization(routing_api, aml_id)

    print(
        "Found on the aml (%s): home division %s, %d group(s), %d direct role "
        "grant(s), %d skill(s), %d queue(s), %s utilization." % (
            aml_id,
            aml_home_division_id or "none",
            len(aml_group_ids),
            len(aml_role_division_pairs),
            len(aml_skill_pairs),
            len(aml_queue_ids),
            "custom" if aml_utilization is not None else "org-default",
        )
    )

    # Stop if the aml has nothing worth copying. This usually means a read
    # failed or the aml ID is wrong, and wiping the target to grant nothing
    # would hide the real problem.
    if (not aml_home_division_id and not aml_group_ids and not aml_role_division_pairs
            and not aml_skill_pairs and not aml_queue_ids):
        raise SystemExit(
            "The aml has no home division, groups, roles, skills, or queues, so "
            "the target was left alone. Check the 'aml' user ID and that the "
            "reads above did not fail."
        )

    # Step 1: clean slate for the target. We only need to clear groups and
    # queues here. Roles and skills are cleared by their apply steps below,
    # which replace the whole set in one call, so a separate clear would just be
    # a wasted API call.
    target_home_division_id, target_group_ids = get_home_division_and_group_ids(users_api, target_id)
    target_queue_ids = get_queue_ids(users_api, target_id)
    print(
        "The target (%s) currently has: home division %s, %d group(s), %d "
        "queue(s)." % (
            target_id,
            target_home_division_id or "none",
            len(target_group_ids),
            len(target_queue_ids),
        )
    )
    remove_from_groups(groups_api, target_id, target_group_ids)
    unjoin_queues(users_api, target_id, target_queue_ids)

    # Step 2: move the target into the aml's home division.
    set_home_division(authorization_api, target_id, aml_home_division_id)

    # Step 3: put the target in the aml's groups, so the group roles follow.
    add_to_groups(groups_api, target_id, aml_group_ids)

    # Step 4: give the target the aml's direct role grants (replaces old ones).
    apply_role_division_pairs(authorization_api, target_id, aml_role_division_pairs)

    # Step 5: give the target the aml's skills and proficiencies (replaces old).
    apply_skills(users_api, target_id, aml_skill_pairs)

    # Step 6: join the target to the aml's queues. Last on purpose: a queue join
    # needs the role and group access from Steps 3 and 4 to already be in place.
    join_queues(users_api, target_id, aml_queue_ids)

    # Step 7: match the target's utilization to the aml's. If the aml has custom
    # settings we copy them; if the aml is on the org default we reset the
    # target to the default too. This step does not depend on the others, so its
    # order does not matter; it runs last to keep the flow tidy.
    apply_utilization(routing_api, target_id, aml_utilization)

    if DRY_RUN:
        print("\n[DRY-RUN] Done. No changes were made. Set DRY_RUN = False to apply.")
    else:
        print("\nAML Completed")


if __name__ == '__main__':
    main(aml, target)
