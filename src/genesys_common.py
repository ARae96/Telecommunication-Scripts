# =============================================================================
# Shared Genesys Cloud Helpers - Sign In, Name Lookups, Paging, and File Output
# =============================================================================
# A shared toolbox for the Genesys Cloud scripts in this folder. We built it by
# reviewing the scripts we already wrote and pulling out the API calls and
# helpers that kept showing up in several of them, written almost the same way
# each time. Instead of copying them into every new script, you import them.
#
# This module only reads from Genesys. It never changes anything in Genesys.
# Scripts that change things (grant roles, add group members, and so on) should
# keep that logic in the script itself, next to their confirm step.
#
# How to use it in a script (the scripts sit next to this file, so a plain
# import works, the same way confirm_prompt.py is imported):
#
#   from genesys_common import build_apis, get_management_unit_names
#   wfm_api, users_api = build_apis('WorkforceManagementApi', 'UsersApi')
#   mu_names = get_management_unit_names(wfm_api)
#
# What is inside (see each section below):
#   - Sign in:          sign_in, build_apis
#   - Safe calls:       call_api, split_into_batches
#   - Name lookups:     get_user_name, get_role_name, get_queue_name,
#                       get_group_name, get_division_name, get_flow_name,
#                       get_user_names, get_queue_names
#   - Lists of people:  get_all_users, get_role_user_ids, get_queue_user_ids
#   - Roles:            get_role_with_permissions, get_user_role_ids,
#                       get_user_grant_division_ids, policy_key,
#                       get_role_permission_strings, get_role_id_from_link
#   - BUs and MUs:      get_business_unit_id_from_link, get_business_units,
#                       get_business_unit_names, get_bu_name_and_start_day,
#                       get_management_units, get_management_unit_names
#   - Week dates:       get_past_week_dates, format_week_folder_name
#   - Files and data:   to_plain_data, convert_keys_to_snake_case,
#                       fetch_json_from_url, clean_folder_name,
#                       write_json_file, write_csv_file
#
# Please note: the sign in works on your Mac with the .env file. On Databricks,
# pass the client ID and secret into sign_in() from dbutils.secrets instead.
#
# Related script: confirm_prompt.py (the shared confirm dialog).
# =============================================================================

# --- Imports -----------------------------------------------------------------
import os
import re
import csv
import gzip
import json
import time
import datetime
import urllib.request

import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from dotenv import load_dotenv


# --- Configuration -----------------------------------------------------------
# The text we return when a name cannot be read. Scripts print this next to an
# ID so a missing name never stops a run.
NAME_UNAVAILABLE = "(name unavailable)"

# Genesys lets most list calls return at most 100 items per page or per batch.
PAGE_SIZE = 100

# If Genesys says we are sending calls too fast (error 429), call_api waits this
# many seconds and tries again, up to this many times, before it gives up.
RATE_LIMIT_MAX_RETRIES = 3
RATE_LIMIT_WAIT_SECONDS = 15

# The user states we search for names, in order. Active comes first. We only
# search the next state for the IDs we have not found yet.
USER_STATES_TO_SEARCH = ['active', 'inactive', 'deleted']

# Each BU picks its own first day of the week. Genesys wants a week date that is
# that first day. This maps the day name Genesys gives us to Python's weekday
# number (Monday is 0).
WEEKDAY_NUMBERS = {
    'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3,
    'Friday': 4, 'Saturday': 5, 'Sunday': 6,
}


# --- Sign in -----------------------------------------------------------------
def sign_in(client_id=None, client_secret=None):
    """Sign in to Genesys Cloud and return the signed-in API client.

    With no arguments, this reads GENESYS_CLOUD_CLIENT_ID and
    GENESYS_CLOUD_CLIENT_SECRET from the .env file at the workspace root (one
    folder up from this file). On Databricks, pass the two values in yourself
    from dbutils.secrets. Stops the script with a helpful message if either
    value is missing.
    """
    if not client_id or not client_secret:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        load_dotenv(env_path)
        client_id = os.environ.get('GENESYS_CLOUD_CLIENT_ID')
        client_secret = os.environ.get('GENESYS_CLOUD_CLIENT_SECRET')
    if not client_id or not client_secret:
        raise SystemExit(
            "Missing Genesys Cloud credentials. Copy .env.example to .env and set "
            "GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET."
        )

    # Genesys API call: ApiClient.get_client_credentials_token - signs in with
    # the client ID and secret and returns an authenticated client.
    return PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(
        client_id, client_secret
    )


def build_apis(*api_names):
    """Sign in once and return the API clients you ask for, by class name.

    Example: build_apis('WorkforceManagementApi', 'UsersApi') returns a tuple
    (wfm_api, users_api) in that order. If you ask for only one name, you get
    that one client back on its own (not in a tuple).

    We look each class up by name on the Genesys SDK. That is the one slightly
    advanced step here, and it saves every script from repeating the sign in.
    Stops the script with a clear message if a class name is misspelled.
    """
    api_client = sign_in()

    apis = []
    for api_name in api_names:
        api_class = getattr(PureCloudPlatformClientV2, api_name, None)
        if api_class is None:
            raise SystemExit("Unknown Genesys API class '%s'. Check the spelling." % api_name)
        apis.append(api_class(api_client))

    if len(apis) == 1:
        return apis[0]
    return tuple(apis)


# --- Safe calls --------------------------------------------------------------
def call_api(api_function, *args, **kwargs):
    """Call a Genesys API function and return its result.

    If Genesys answers 429 (too many calls too fast), this waits and tries
    again, up to RATE_LIMIT_MAX_RETRIES times. Any other error, or a 429 that
    keeps coming back, is raised so the caller can print it and move on.
    Example: call_api(wfm_api.get_workforcemanagement_businessunit, bu_id)
    """
    for attempt_number in range(RATE_LIMIT_MAX_RETRIES + 1):
        try:
            return api_function(*args, **kwargs)
        except ApiException as e:
            is_last_attempt = attempt_number >= RATE_LIMIT_MAX_RETRIES
            if e.status == 429 and not is_last_attempt:
                print("      Genesys asked us to slow down. Waiting %d seconds..." % RATE_LIMIT_WAIT_SECONDS)
                time.sleep(RATE_LIMIT_WAIT_SECONDS)
            else:
                raise


def split_into_batches(items, batch_size):
    """Return the items split into smaller lists of at most batch_size each.

    Many Genesys calls take only a limited number of IDs per request (often 50
    or 100), so we ask about people or queues in batches. Returns a list of
    lists.
    """
    batches = []
    for start in range(0, len(items), batch_size):
        batches.append(items[start:start + batch_size])
    return batches


# --- Name lookups (one ID at a time) -----------------------------------------
# Each of these returns a name, or NAME_UNAVAILABLE if the read fails. A missing
# name should never block a preview or a confirm dialog.
def get_user_name(users_api, user_id):
    """Return a user's display name, or NAME_UNAVAILABLE if we cannot read it."""
    try:
        user = users_api.get_user(user_id)
    except ApiException as e:
        print("Could not read user name for %s: %s" % (user_id, e))
        return NAME_UNAVAILABLE
    return getattr(user, 'name', None) or NAME_UNAVAILABLE


def get_role_name(authorization_api, role_id):
    """Return a role's name, or NAME_UNAVAILABLE if we cannot read it."""
    try:
        role = authorization_api.get_authorization_role(role_id)
    except ApiException as e:
        print("Could not read role name for %s: %s" % (role_id, e))
        return NAME_UNAVAILABLE
    return getattr(role, 'name', None) or NAME_UNAVAILABLE


def get_queue_name(routing_api, queue_id):
    """Return a queue's name, or NAME_UNAVAILABLE if we cannot read it."""
    try:
        queue = routing_api.get_routing_queue(queue_id)
    except ApiException as e:
        print("Could not read queue name for %s: %s" % (queue_id, e))
        return NAME_UNAVAILABLE
    return getattr(queue, 'name', None) or NAME_UNAVAILABLE


def get_group_name(groups_api, group_id):
    """Return a group's name, or NAME_UNAVAILABLE if we cannot read it."""
    try:
        group = groups_api.get_group(group_id)
    except ApiException as e:
        print("Could not read group name for %s: %s" % (group_id, e))
        return NAME_UNAVAILABLE
    return getattr(group, 'name', None) or NAME_UNAVAILABLE


def get_division_name(authorization_api, division_id):
    """Return a division's name, or NAME_UNAVAILABLE if we cannot read it.

    Returns "none" when there is no division ID to look up.
    """
    if not division_id:
        return "none"
    try:
        division = authorization_api.get_authorization_division(division_id)
    except ApiException as e:
        print("Could not read division name for %s: %s" % (division_id, e))
        return NAME_UNAVAILABLE
    return getattr(division, 'name', None) or NAME_UNAVAILABLE


def get_flow_name(architect_api, flow_id):
    """Return an Architect flow's name, or NAME_UNAVAILABLE if we cannot read it."""
    try:
        flow = architect_api.get_flow(flow_id)
    except ApiException as e:
        print("Could not read flow name for %s: %s" % (flow_id, e))
        return NAME_UNAVAILABLE
    return getattr(flow, 'name', None) or NAME_UNAVAILABLE


# --- Name lookups (many IDs at once) -----------------------------------------
def get_user_names(users_api, user_ids, known_names=None, missing_name='Deleted User'):
    """Return a dict that maps user ID to user name for the IDs you give.

    Only looks up IDs that are not already in known_names, so you can pass the
    same dict from call to call and each person is looked up once per run.
    Searches active users first, then inactive, then deleted, and only searches
    the next state for IDs still missing. An ID that no state returns is saved
    as missing_name. Changes known_names in place and also returns it.
    """
    if known_names is None:
        known_names = {}

    ids_to_find = []
    for user_id in user_ids:
        if user_id and user_id not in known_names and user_id not in ids_to_find:
            ids_to_find.append(user_id)

    for state in USER_STATES_TO_SEARCH:
        if not ids_to_find:
            break
        for batch in split_into_batches(ids_to_find, PAGE_SIZE):
            try:
                # Genesys API call: get_users with a list of IDs and a state -
                # returns the users in that state whose IDs we asked for.
                response = call_api(users_api.get_users, id=batch, state=state, page_size=PAGE_SIZE)
            except ApiException as e:
                print("      Could not look up %s users, so some names in this batch may be wrong: %s" % (state, e))
                continue
            for user in (response.entities or []):
                if user.id and user.name:
                    known_names[user.id] = user.name

        # Carry only the IDs we still have not found into the next state.
        still_missing = []
        for user_id in ids_to_find:
            if user_id not in known_names:
                still_missing.append(user_id)
        ids_to_find = still_missing

    for user_id in ids_to_find:
        known_names[user_id] = missing_name
    return known_names


def get_queue_names(routing_api, queue_ids, known_names=None, missing_name='Deleted Queue'):
    """Return a dict that maps queue ID to queue name for the IDs you give.

    Only looks up IDs that are not already in known_names. Any ID Genesys does
    not return is saved as missing_name, because a deleted queue no longer
    exists to look up. Changes known_names in place and also returns it.

    Please note: if a lookup call fails (not just "queue not found"), the IDs in
    that batch are left out instead of being marked deleted. That way a later
    call tries them again, and a temporary problem is not saved as a deletion.
    """
    if known_names is None:
        known_names = {}

    ids_to_find = []
    for queue_id in queue_ids:
        if queue_id and queue_id not in known_names and queue_id not in ids_to_find:
            ids_to_find.append(queue_id)

    for batch in split_into_batches(ids_to_find, PAGE_SIZE):
        try:
            # Genesys API call: get_routing_queues with a list of IDs - returns
            # the queues that still exist from the IDs we asked for.
            response = call_api(routing_api.get_routing_queues, id=batch, page_size=PAGE_SIZE)
        except ApiException as e:
            print("      Could not look up queue names, so these queues show no name this time: %s" % e)
            continue

        for queue in (response.entities or []):
            if queue.id and queue.name:
                known_names[queue.id] = queue.name

        # Any ID in this batch that did not come back no longer exists.
        for queue_id in batch:
            if queue_id not in known_names:
                known_names[queue_id] = missing_name
    return known_names


# --- Lists of people ---------------------------------------------------------
def get_all_users(users_api, states=('active',), expand=None):
    """Return a list of every user in the given states.

    Reads users one page at a time. The API lets us ask for one state at a time,
    so we read all pages for each state and add them together. Pass expand
    (for example ['dateLastLogin', 'division']) to include extra fields.
    If a page fails, we print the error, stop reading that state, and keep what
    we already gathered.
    """
    all_users = []
    for state in states:
        page_number = 1
        while True:
            try:
                response = users_api.get_users(
                    page_size=PAGE_SIZE, page_number=page_number, expand=expand, state=state
                )
            except ApiException as e:
                print("Exception when calling UsersApi->get_users: %s\n" % e)
                break
            all_users.extend(response.entities or [])
            if page_number >= (response.page_count or 0):
                break
            page_number += 1
    return all_users


def get_role_user_ids(authorization_api, role_id):
    """Return every user ID assigned to a role, paging through all results."""
    user_ids = []
    page_number = 1
    while True:
        # Genesys API call: get_authorization_role_users - lists the users
        # assigned to one role, one page at a time.
        response = authorization_api.get_authorization_role_users(
            role_id, page_size=PAGE_SIZE, page_number=page_number
        )
        for entity in (response.entities or []):
            user_ids.append(entity.id)
        if page_number >= (response.page_count or 0):
            break
        page_number += 1
    return user_ids


def get_queue_user_ids(routing_api, queue_id):
    """Return the user IDs of every user who is a member of a queue.

    A queue can hold both users and groups, so we ask for users only. This list
    marks the end with an empty next_uri instead of a page count, so we follow
    that. Returns what we gathered so far (maybe an empty list) if a read fails.
    """
    user_ids = []
    page_number = 1
    while True:
        try:
            response = routing_api.get_routing_queue_members(
                queue_id, page_number=page_number, page_size=PAGE_SIZE, member_by='user'
            )
        except ApiException as e:
            print("Exception when calling RoutingApi->get_routing_queue_members: %s\n" % e)
            return user_ids

        entities = response.entities or []
        for member in entities:
            user_id = getattr(member, 'id', None)
            if user_id:
                user_ids.append(user_id)

        # Stop when next_uri is empty. Also stop on an empty page, so we never
        # loop forever.
        if not getattr(response, 'next_uri', None) or not entities:
            break
        page_number += 1
    return user_ids


# --- Roles -------------------------------------------------------------------
def get_role_with_permissions(authorization_api, role_id):
    """Return one role with its permission policies filled in.

    We pass expand=['permissionPolicies'] so Genesys includes the full
    permission list. Without it the policies come back empty. Stops the script
    if the read fails, because the callers cannot go on without the role.
    """
    try:
        return authorization_api.get_authorization_role(role_id, expand=['permissionPolicies'])
    except ApiException as e:
        raise SystemExit("Failed to read role %s: %s" % (role_id, e))


def get_user_role_ids(authorization_api, user_id):
    """Return the IDs of the roles granted to one person, with no repeats.

    Each grant pairs one role with one division, so a role held in two divisions
    shows up twice in Genesys. We return each role ID once. Returns an empty
    list if the call fails.
    """
    role_ids = []
    try:
        # Genesys API call: get_authorization_subject - lists every role and
        # division granted to one user.
        subject = authorization_api.get_authorization_subject(user_id)
    except ApiException as e:
        print("Exception when calling AuthorizationApi->get_authorization_subject: %s\n" % e)
        return role_ids

    for grant in (getattr(subject, 'grants', None) or []):
        role_id = getattr(getattr(grant, 'role', None), 'id', None)
        if role_id and role_id not in role_ids:
            role_ids.append(role_id)
    return role_ids


def get_user_grant_division_ids(authorization_api, user_id):
    """Return the set of division IDs a user holds roles in.

    Please note: Genesys can grant a role across all divisions at once. That
    shows up as the special division ID "*". We keep it as-is, so the caller can
    treat "all divisions" as more than one division.
    """
    subject = authorization_api.get_authorization_subject(user_id)

    division_ids = set()
    for grant in (getattr(subject, 'grants', None) or []):
        division = getattr(grant, 'division', None)
        if division is not None and division.id:
            division_ids.add(division.id)
    return division_ids


def policy_key(policy):
    """Return the (domain, entity name) pair that identifies a permission policy.

    Two policies describe the same permission when they share this pair, for
    example ("directory", "user"). We use it to spot when two roles set the same
    permission and need to be combined.
    """
    return (getattr(policy, 'domain', None), getattr(policy, 'entity_name', None))


def get_role_permission_strings(authorization_api, role_id):
    """Return the set of plain permission strings for one role.

    Each string looks like domain:entity:action, which is how Genesys writes a
    permission. Returns an empty set if the read fails, so one bad role does not
    stop the whole run.
    """
    try:
        role = authorization_api.get_authorization_role(role_id)
    except ApiException as e:
        print("Exception reading role %s: %s\n" % (role_id, e))
        return set()

    permission_strings = set()
    for policy in (getattr(role, 'permission_policies', None) or []):
        domain = getattr(policy, 'domain', None)
        entity_name = getattr(policy, 'entity_name', None)
        if not domain or not entity_name:
            continue
        for action in (getattr(policy, 'action_set', None) or []):
            permission_strings.add("%s:%s:%s" % (domain, entity_name, action))
    return permission_strings


def get_role_id_from_link(role_link):
    """Return the role ID from a role page link, or from a bare role ID.

    When you open a role in Genesys Cloud, the ID is the last part of the page
    link, right after the final slash. We trim spaces and any trailing slash,
    then keep that last part. Stops the script if it does not look like a role
    ID (a GUID), so a bad paste is caught before we call Genesys.
    """
    last_part = role_link.strip().rstrip('/').split('/')[-1]
    guid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    if not re.match(guid_pattern, last_part):
        raise SystemExit(
            "Could not find a role ID in '%s'. Paste the full role page link "
            "from your browser (it ends in the role ID), or paste the bare role ID."
            % role_link
        )
    return last_part


# --- Business units (BUs) and management units (MUs) -------------------------
def get_business_unit_id_from_link(business_unit_link):
    """Return the BU ID at the end of an admin link.

    The links look like ".../businessUnits/<id>", so the ID is the last piece.
    A plain ID with no slashes is returned unchanged.
    """
    return business_unit_link.rstrip('/').split('/')[-1]


def get_business_units(wfm_api):
    """Return the list of business units (BUs) your OAuth client can see.

    Each item is a Genesys object with id, name, and division. Stops with the
    API error printed if the call fails.
    """
    try:
        # Genesys API call: get_workforcemanagement_businessunits - lists the
        # BUs the signed-in client is allowed to see.
        response = wfm_api.get_workforcemanagement_businessunits()
    except ApiException as e:
        print("Exception calling get_workforcemanagement_businessunits: %s\n" % e)
        raise
    return response.entities or []


def get_business_unit_names(wfm_api):
    """Return a dict that maps BU ID to BU name for every BU we can see."""
    names = {}
    for business_unit in get_business_units(wfm_api):
        names[business_unit.id] = business_unit.name
    return names


def get_bu_name_and_start_day(wfm_api, business_unit_id):
    """Return a (name, start day) tuple for one BU, such as ("Service Desk", "Sunday").

    If the lookup fails, the name is the BU ID itself so a backup still has a
    folder name, and the start day is "Monday". A missing start day also
    defaults to "Monday".
    """
    try:
        # Genesys API call: get_workforcemanagement_businessunit with the
        # "settings" expand - returns the BU name and the first day of its week.
        business_unit = call_api(
            wfm_api.get_workforcemanagement_businessunit, business_unit_id, expand=['settings']
        )
    except ApiException as e:
        print("   Could not read the BU details for %s, using the ID and Monday: %s" % (business_unit_id, e))
        return (business_unit_id, 'Monday')

    name = getattr(business_unit, 'name', None) or business_unit_id
    settings = getattr(business_unit, 'settings', None)
    start_day = getattr(settings, 'start_day_of_week', None) or 'Monday'
    return (name, start_day)


def get_management_units(wfm_api, business_unit_ids=None):
    """Return the management units (MUs) for the given BUs as a list of objects.

    Pass a list of BU IDs, or leave it out to read the MUs of every BU we can
    see. A failure on one BU is printed and skipped so one bad BU does not stop
    the rest. Each MU object has id, name, and division.
    """
    if business_unit_ids is None:
        business_unit_ids = list(get_business_unit_names(wfm_api).keys())

    management_units = []
    for business_unit_id in business_unit_ids:
        try:
            # Genesys API call: get_workforcemanagement_businessunit_managementunits
            # - lists the MUs inside one BU.
            response = wfm_api.get_workforcemanagement_businessunit_managementunits(business_unit_id)
        except ApiException as e:
            print("Could not read the MUs for BU %s: %s" % (business_unit_id, e))
            continue
        management_units.extend(response.entities or [])
    return management_units


def get_management_unit_names(wfm_api, business_unit_ids=None):
    """Return a dict that maps MU ID to MU name.

    Pass a list of BU IDs to limit the lookup, or leave it out to cover every BU
    we can see.
    """
    names = {}
    for management_unit in get_management_units(wfm_api, business_unit_ids):
        names[management_unit.id] = management_unit.name
    return names


# --- Week dates --------------------------------------------------------------
def get_past_week_dates(start_day, lookback_weeks):
    """Return a list of past week start dates, newest first.

    Each date is the first day of a BU week (for example every Sunday), going
    back lookback_weeks weeks from today. The newest date is the start of the
    current week. Returns a list of date objects.
    """
    start_weekday = WEEKDAY_NUMBERS.get(start_day, 0)
    today = datetime.date.today()
    days_since_start = (today.weekday() - start_weekday) % 7
    this_week_start = today - datetime.timedelta(days=days_since_start)

    week_dates = []
    for weeks_back in range(lookback_weeks + 1):
        week_dates.append(this_week_start - datetime.timedelta(days=7 * weeks_back))
    return week_dates


def format_week_folder_name(week_date, week_count, item_id):
    """Return a folder name like "W23-2025 06-02 to 06-08 <item_id>".

    That is the ISO week and year, the start and end month-day, then the ID of
    the schedule or forecast. The end day is the start day plus (week_count
    times 7) minus 1, and week_count defaults to one week.

    Please note: some BUs start their week on Sunday, but ISO weeks start on
    Monday. Reading the ISO week from a Sunday would give the week before, so we
    read it from three days after the start date, the middle of the week.
    """
    iso_year, iso_week, _ = (week_date + datetime.timedelta(days=3)).isocalendar()
    weeks = week_count or 1
    end_date = week_date + datetime.timedelta(days=(weeks * 7) - 1)

    week_label = "W%02d-%d" % (iso_week, iso_year)
    return "%s %s to %s %s" % (week_label, week_date.strftime('%m-%d'), end_date.strftime('%m-%d'), item_id)


# --- Files and data ----------------------------------------------------------
def to_plain_data(api_object):
    """Return a plain dict or list copy of a Genesys SDK object.

    SDK objects turn themselves into nested dicts and lists with to_dict(). We
    call that so the data can be saved as JSON. Plain values are returned as-is.
    """
    if api_object is None:
        return None
    if hasattr(api_object, 'to_dict'):
        return api_object.to_dict()
    if isinstance(api_object, list):
        return [to_plain_data(item) for item in api_object]
    return api_object


def convert_keys_to_snake_case(data):
    """Return a copy of the data with every dict key changed to snake_case.

    Genesys download files use camelCase keys like "planningGroupId", while the
    SDK objects use snake_case like "planning_group_id". Converting makes both
    look the same. Walks through nested dicts and lists.
    """
    if isinstance(data, dict):
        converted = {}
        for key, value in data.items():
            snake_key = re.sub(r'(?<!^)(?=[A-Z])', '_', key).lower()
            converted[snake_key] = convert_keys_to_snake_case(value)
        return converted
    if isinstance(data, list):
        return [convert_keys_to_snake_case(item) for item in data]
    return data


def fetch_json_from_url(download_url):
    """Return the JSON found at a Genesys download link as plain data.

    For larger results Genesys hands back a short-lived link instead of the
    data. The file is usually gzip compressed, so we unpack it first. Keys are
    converted to snake_case. Returns None if the link cannot be read, so one bad
    download does not stop the run.
    """
    try:
        with urllib.request.urlopen(download_url) as response:
            raw_bytes = response.read()
        # Gzip files always begin with the two bytes 1f 8b.
        if raw_bytes[:2] == b'\x1f\x8b':
            raw_bytes = gzip.decompress(raw_bytes)
        data = json.loads(raw_bytes.decode('utf-8'))
        return convert_keys_to_snake_case(data)
    except Exception as e:
        print("      Could not read the download link: %s" % e)
        return None


def clean_folder_name(name):
    """Return a version of a name that is safe to use as a folder name.

    Any character that is not a letter, number, space, dash, dot, or underscore
    becomes a dash, then the ends are trimmed.
    """
    return re.sub(r'[^A-Za-z0-9 ._-]', '-', name).strip()


def write_json_file(folder_path, file_name, data):
    """Write data to an indented JSON file inside a folder and return the path.

    Dates and times are saved as text. The folder must already exist.
    """
    file_path = os.path.join(folder_path, file_name)
    with open(file_path, 'w') as out_file:
        json.dump(data, out_file, indent=2, default=str)
    return file_path


def write_csv_file(folder_path, file_name, field_names, rows):
    """Write a list of row dicts to a CSV file inside a folder and return the path.

    Always writes a header row so the file opens cleanly in Excel even when
    there are no data rows. The folder must already exist.
    """
    file_path = os.path.join(folder_path, file_name)
    with open(file_path, 'w', newline='') as out_file:
        writer = csv.DictWriter(out_file, fieldnames=field_names)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return file_path
