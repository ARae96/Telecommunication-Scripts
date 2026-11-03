# =============================================================================
# Genesys Cloud - Copy Queue Members Into A Group
# =============================================================================
# Reads every user assigned to a Genesys Cloud queue, then adds those same
# users as members of a group. The queue is left as-is; this only adds people
# to the group, it does not change the queue.
#
# You enter the IDs by hand near the top of the file: source_queues (one or
# more queues to read users from) and new_group (the group to add those users
# to). The script signs in to Genesys Cloud, lists the user members of every
# queue in the list, and adds their user IDs to the group.
#
# A user can be in more than one of the queues. The script collects everyone
# into one list with no repeats, so each person is added to the group only
# once even if they are in several of the queues.
#
# Safety: this script changes Genesys Cloud, so it always reads first and shows
# you a summary before it changes anything. It names the group that will receive
# the users, the number of unique users, and the queues they came from. Then it
# asks you to confirm in a pop-up dialog (with a typed fallback if the dialog
# cannot be shown). No members are added unless you confirm.
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

from confirm_prompt import ask_to_confirm


# --- Configuration -----------------------------------------------------------
# Enter the IDs by hand before running. source_queues is the list of queues we
# read users from; add as many queue IDs as you need, one per line. new_group
# is the group we add those users to.
source_queues = ['']
new_group = ''

# How many members to ask for on each page when reading the queue. The queue
# members API returns results one page at a time, so we loop through pages.
# The queue members API caps page size at 100, so do not set this above 100.
PAGE_SIZE = 100

# The add-members API accepts at most 50 user IDs in a single request, so we
# add people in batches of this size. This value must not go above 50.
ADD_BATCH_SIZE = 50


# --- Authentication ----------------------------------------------------------
def build_apis():
    """Sign in to Genesys Cloud and return the Routing and Groups API clients.

    Reads GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET from the .env
    file next to this script. Stops the script with a helpful message if either
    value is missing. Returns the clients in this order: (RoutingApi,
    GroupsApi). RoutingApi reads the queue's members; GroupsApi adds them to
    the group.
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
        PureCloudPlatformClientV2.RoutingApi(apiclient),
        PureCloudPlatformClientV2.GroupsApi(apiclient),
    )


# --- Steps -------------------------------------------------------------------
def get_queue_name(routing_api, queue_id):
    """Return the name of a queue, or a fallback label if we cannot read it.

    We print this name during the dry run so you can confirm you entered the
    right queue before running for real. If the read fails we return a short
    "(name unavailable)" label instead of stopping, because a missing name
    should not block the rest of the run.
    """
    try:
        queue = routing_api.get_routing_queue(queue_id)
    except ApiException as e:
        print("Exception when calling RoutingApi->get_routing_queue: %s\n" % e)
        return "(name unavailable)"

    return getattr(queue, 'name', None) or "(name unavailable)"


def get_group_name(groups_api, group_id):
    """Return the name of a group, or a fallback label if we cannot read it.

    We print this name during the dry run so you can confirm you entered the
    right group before running for real. If the read fails we return a short
    "(name unavailable)" label instead of stopping, because a missing name
    should not block the rest of the run.
    """
    try:
        group = groups_api.get_group(group_id)
    except ApiException as e:
        print("Exception when calling GroupsApi->get_group: %s\n" % e)
        return "(name unavailable)"

    return getattr(group, 'name', None) or "(name unavailable)"


def get_queue_user_ids(routing_api, queue_id):
    """Return the user IDs of every user assigned to a queue.

    Reads the queue's members one page at a time and collects each member's
    user ID. A queue can hold both users and groups, so we ask for users only
    with member_by='user'. Returns a list of user ID strings. Returns an empty
    list if the read fails, so the caller can decide what to do next.

    Step 1: Ask for the first page of queue members, users only.
    Step 2: Collect the user ID from each member on the page.
    Step 3: Move to the next page until the listing says there are no more.
            This listing marks the end with an empty next_uri rather than a
            page count, so we follow that instead of counting pages.
    """
    user_ids = []
    page_number = 1

    while True:
        try:
            response = routing_api.get_routing_queue_members(
                queue_id,
                page_number=page_number,
                page_size=PAGE_SIZE,
                member_by='user',
            )
        except ApiException as e:
            print("Exception when calling RoutingApi->get_routing_queue_members: %s\n" % e)
            return user_ids

        entities = response.entities or []
        for member in entities:
            # For a user member, the member's own id is the user ID we need.
            # Guard it in case a record is missing it, so one odd record does
            # not stop the whole run.
            user_id = getattr(member, 'id', None)
            if user_id:
                user_ids.append(user_id)

        # This listing does not tell us a total page count. Instead it gives a
        # next_uri that points at the next page, and leaves next_uri empty once
        # there are no more pages. So we stop as soon as next_uri is empty.
        # We also stop if a page came back empty, as a safety net so we never
        # loop forever.
        if not getattr(response, 'next_uri', None) or not entities:
            break
        page_number += 1

    return user_ids


def get_unique_user_ids_across_queues(routing_api, queue_ids):
    """Return the unique user IDs across all the queues and the queue names.

    Reads each queue in turn and gathers everyone into one list. A user who is
    in more than one of the queues is kept only once, so the group add later
    does not try to add the same person twice. The list keeps first-seen order,
    so the person found first comes first, which makes the output easy to read.

    Returns a tuple of (unique_user_ids, queue_names). queue_names holds the
    name of each queue we actually read, in order, so the confirm dialog can
    list which queues the users came from.

    Skips a blank queue ID and prints a per-queue count so you can see where
    the users came from. If one queue read fails it is reported inside
    get_queue_user_ids and simply contributes no users, so one bad queue does
    not stop the others.
    """
    unique_user_ids = []
    seen_user_ids = set()
    queue_names = []

    for queue_id in queue_ids:
        # Skip a blank entry so an empty line in the list does not cause a call
        # with an empty queue ID.
        if not queue_id:
            continue

        # Read the queue's name so the output and the confirm dialog show which
        # queue these users came from, not just its ID. This makes it easy to
        # confirm you entered the right queue.
        queue_name = get_queue_name(routing_api, queue_id)
        queue_names.append(queue_name)
        queue_user_ids = get_queue_user_ids(routing_api, queue_id)
        print(
            "Queue '%s' (%s) has %d users."
            % (queue_name, queue_id, len(queue_user_ids))
        )

        for user_id in queue_user_ids:
            # Add each user only the first time we see them. The seen set is how
            # we skip repeats, which is what stops the same person being added
            # to the group more than once.
            if user_id not in seen_user_ids:
                seen_user_ids.add(user_id)
                unique_user_ids.append(user_id)

    return unique_user_ids, queue_names


def split_into_batches(items, batch_size):
    """Return the items split into smaller lists of at most batch_size each.

    The add-members API accepts at most 50 user IDs per request, so we send
    people in batches. Returns a list of lists, where each inner list has up to
    batch_size items.
    """
    batches = []
    for start in range(0, len(items), batch_size):
        batches.append(items[start:start + batch_size])
    return batches


def add_members_to_group(groups_api, group_id, group_name, user_ids):
    """Add the given user IDs as members of a group.

    Adds people in batches of at most 50 because that is the most the API will
    take in one request. Builds a GroupMembersUpdate body for each batch and
    sends it. Prints progress for each batch, including the group's name so you
    can confirm it is the group you meant.

    Call this only after the person has confirmed. If one batch fails it prints
    the error and keeps going with the next batch, so one bad batch does not
    stop the whole run.
    """
    batches = split_into_batches(user_ids, ADD_BATCH_SIZE)

    for batch_number, batch in enumerate(batches, start=1):
        body = PureCloudPlatformClientV2.GroupMembersUpdate()
        body.member_ids = batch

        try:
            groups_api.post_group_members(group_id, body)
            print(
                "Added batch %d of %d (%d members) to group '%s' (%s)"
                % (batch_number, len(batches), len(batch), group_name, group_id)
            )
        except ApiException as e:
            print("Exception when calling GroupsApi->post_group_members: %s\n" % e)


def format_add_for_confirm(group_name, user_count, queue_names):
    """Build the confirm message for adding queue users to a group.

    Names the group that will receive the users, the number of unique users,
    and the queues they came from. Returns one block of text with real new
    lines, shown in the confirm dialog and the typed fallback.
    """
    lines = []

    lines.append("The following group will receive users:")
    lines.append(group_name)

    lines.append("")
    lines.append(
        "A total of %d unique user(s) will be added, from these queue(s):"
        % user_count
    )
    for queue_name in queue_names:
        lines.append(queue_name)

    return '\n'.join(lines)


# --- Main --------------------------------------------------------------------
def main(source_queue_ids, new_group_id):
    """Copy the users from one or more queues onto a group.

    Step 1: Stop early if there are no queues or the group ID is blank, so we
            never call the API with an empty ID.
    Step 2: Sign in to Genesys Cloud.
    Step 3: Read the users of every queue and gather them into one list with no
            repeats, so a person in several queues is added only once.
    Step 4: Stop if no users came back, so we do not make a pointless add call.
    Step 5: Add those user IDs to the group (in batches of 50).
    """
    # Stop early if there is nothing to read from or nowhere to add to. Without
    # this, a blank ID would fail later at the API call with a confusing error
    # instead of a clear one. any(...) is True only when the list holds at
    # least one non-blank queue ID.
    if not any(source_queue_ids) or not new_group_id:
        raise SystemExit(
            "Set 'source_queues' (one or more queues to read users from) and "
            "'new_group' (the group to add users to) near the top of the "
            "script before running."
        )

    routing_api, groups_api = build_apis()

    user_ids, queue_names = get_unique_user_ids_across_queues(routing_api, source_queue_ids)

    # Stop if no users came back. This usually means every queue read failed or
    # the queues have no user members, and adding nothing would be a wasted
    # call that could hide the real problem.
    if not user_ids:
        raise SystemExit(
            "No users found on any of the queues, so nothing was added to the "
            "group. Check the 'source_queues' IDs and that the reads above did "
            "not fail."
        )

    print("Found %d unique users across all queues." % len(user_ids))

    # Read the group's name so the summary shows which group these users would
    # be added to, not just its ID.
    group_name = get_group_name(groups_api, new_group_id)

    # Show the plan and ask you to confirm before adding anyone. If you do not
    # confirm, no members are added.
    question = format_add_for_confirm(group_name, len(user_ids), queue_names)
    if not ask_to_confirm(question, "Copy Queue Members Into a Group"):
        raise SystemExit("Stopped at your request. No members were added.")

    add_members_to_group(groups_api, new_group_id, group_name, user_ids)
    print('Done.')


if __name__ == '__main__':
    main(source_queues, new_group)
