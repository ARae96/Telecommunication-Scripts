# =============================================================================
# Genesys Cloud - Business Unit (BU) Schedule Backup
# =============================================================================
# Backs up the published Workforce Management (WFM) week schedules for a set of
# business units (BUs) that are being retired. For each BU, the script finds
# every published week schedule the Platform API will give us, then saves all
# of the schedule data it can reach to CSV and JSON files on your computer.
#
# Why this exists: the WFM schedule screen in Genesys has export buttons
# (Activities, Agent Shifts, Scheduled and Required, Activity counts), but the
# Platform API has no matching endpoints for those exact files. So instead of
# copying those four exports, this script pulls the underlying schedule data
# from the API and writes our own CSV and JSON. The files hold the same
# information, but they will not look byte-for-byte like the screen exports.
#
# How far back we look: the API's "recent" listing only covers about 26 weeks
# before and after today. To reach older schedules, the script also asks for
# each past week by its date, one week at a time, going back LOOKBACK_WEEKS
# weeks (104 weeks is two years). A schedule that spans several weeks can show
# up more than once, so the script keeps only one copy of each schedule ID.
# The script prints what it finds for each BU so you can check that the
# schedules you need are included.
#
# Names: the schedule data only holds agent IDs and activity code IDs. So the
# script looks up each agent's name and each activity code's name and writes
# them next to the IDs in the CSV files. If an activity code has no name, the
# script writes the code's category instead (for example "Meal"). If the code
# has no category either, it writes "Retired". If an agent's name cannot be
# found at all, it writes
# "Attritted". The script checks active, inactive, and deleted users before it
# gives up, so former agents who are still on record keep their real names.
#
# This script only reads from Genesys. It never changes anything in Genesys.
#
# Output (written under the backup folder set in BACKUP_ROOT below):
#   <BU Name>/
#     user_names.json              Agent ID to name lookup used for this BU.
#     activity_code_names.json     Activity code ID to name lookup for this BU.
#     W23-2025 06-02 to 06-08 <schedule id>/
#       schedule_metadata.json     Full schedule metadata from the API.
#       agent_schedules.json       Full agent schedule data (every agent).
#       agent_shifts.csv           One row per shift, flattened for Excel.
#       agent_activities.csv       One row per activity inside each shift.
#   backup_summary.csv             One row per schedule we tried to back up.
#
# Please note - agent_schedules.json is the raw copy from Genesys, so it only
# holds IDs. The names live in the CSV files and in the two lookup files.
# =============================================================================

# --- Imports -----------------------------------------------------------------
import os
import time

import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException

# Shared helpers (sign in, name lookups, BU details, file writers) live in
# genesys_common.py, next to this script.
from genesys_common import (
    build_apis,
    get_business_unit_id_from_link,
    get_bu_name_and_start_day,
    get_past_week_dates,
    get_user_names,
    clean_folder_name,
    format_week_folder_name,
    to_plain_data,
    fetch_json_from_url,
    write_json_file,
    write_csv_file,
)


# --- Configuration -----------------------------------------------------------
# The business units to back up. These are the admin screen links for each BU.
# The script pulls the BU ID out of the end of each link, so you can paste the
# link straight from the browser without editing it.
BUSINESS_UNITS = [
    'https://apps.mypurecloud.com/directory/#/admin/wfm/businessUnits/eb58a009-389d-42af-bfae-b9971536545e',
    'https://apps.mypurecloud.com/directory/#/admin/wfm/businessUnits/21783ae3-aac5-4aec-aef7-6336b3d60fa1',
    'https://apps.mypurecloud.com/directory/#/admin/wfm/businessUnits/1fa4fa88-a84e-44a8-a092-098f8bc59f45',
    'https://apps.mypurecloud.com/directory/#/admin/wfm/businessUnits/688c60a8-7cd1-411b-872b-d05ec9a6809d',
]

# The top folder where all backups are written. The script makes this folder
# (and every folder under it) if it does not already exist.
BACKUP_ROOT = '/Users/alice.weaver/Documents/BU_Backups/Schedules'

# The special word "recent" tells the API to return every week schedule within
# about 26 weeks before and after today. We use it to catch current and future
# schedules.
WEEK_LISTING_KEY = 'recent'

# How many weeks back from today to look for older schedules. 104 weeks is two
# years. The script asks for one past week at a time, so a larger number means
# more API calls per BU.
LOOKBACK_WEEKS = 104

# The name written when an activity code has no name and no category, or when
# the code ID is not in the BU's list at all (for example, the code was
# deleted from the BU).
MISSING_ACTIVITY_CODE_NAME = 'Retired'

# The name written when we cannot find a name for an agent ID in Genesys.
MISSING_USER_NAME = 'Attritted'

# Pulling a week of agent schedules can run as an async job. When it does, we
# check back on the job this many times, waiting this many seconds between
# checks, before we give up on that one schedule and move on.
ASYNC_MAX_CHECKS = 60
ASYNC_WAIT_SECONDS = 5


# --- Steps -------------------------------------------------------------------
def get_published_schedules(wfm_api, business_unit_id, start_day):
    """Return the published week schedules for one business unit (BU).

    Step 1: Ask the API for its "recent" list (about 26 weeks each way).
    Step 2: Ask for each past week by date, going back LOOKBACK_WEEKS weeks, to
            reach schedules older than the "recent" list.
    Step 3: Keep only schedules marked published, and keep one copy of each
            schedule ID, because one schedule can show up in several weeks.

    A failed lookup for one week is printed and skipped so it does not stop the
    rest. Returns a list of schedule objects, oldest first.
    """
    schedules_by_id = {}

    # Step 1: the "recent" list.
    try:
        # Genesys API call: get_workforcemanagement_businessunit_week_schedules
        # with the word "recent" - lists all week schedules in the window.
        listing = wfm_api.get_workforcemanagement_businessunit_week_schedules(
            business_unit_id, WEEK_LISTING_KEY
        )
        for schedule in (listing.entities or []):
            schedules_by_id[schedule.id] = schedule
    except ApiException as e:
        print("   Could not list the recent schedules for this BU: %s" % e)

    # Step 2: each past week, one at a time.
    print("   Checking %d past weeks for older schedules..." % LOOKBACK_WEEKS)
    for week_date in get_past_week_dates(start_day, LOOKBACK_WEEKS):
        try:
            # Same API call, but with a real week date instead of "recent". It
            # returns any schedule that spans that week.
            listing = wfm_api.get_workforcemanagement_businessunit_week_schedules(
                business_unit_id, week_date.isoformat()
            )
            for schedule in (listing.entities or []):
                schedules_by_id[schedule.id] = schedule
        except ApiException as e:
            print("      Could not list schedules for the week of %s: %s" % (week_date, e))

    # Step 3: keep published schedules only, oldest first.
    published = []
    for schedule in schedules_by_id.values():
        if getattr(schedule, 'published', False):
            published.append(schedule)
    published.sort(key=lambda item: item.week_date)
    return published


def get_activity_code_names(wfm_api, business_unit_id):
    """Return a dict that maps activity code ID to activity code name for one BU.

    Reads every activity code the BU has. A code with no name uses its category
    instead. A code with neither is left out, so a lookup of that ID later falls
    back to MISSING_ACTIVITY_CODE_NAME. Returns an empty dict if the lookup
    fails, which means every code shows as "Retired".

    Please note: Genesys usually sends the codes in a download file and leaves
    the "entities" list empty. So we read the download file when there is one,
    and only use "entities" when there is no download link.
    """
    names = {}
    try:
        # Genesys API call: get_workforcemanagement_businessunit_activitycodes
        # - lists all activity codes for the BU.
        listing = wfm_api.get_workforcemanagement_businessunit_activitycodes(business_unit_id)
    except ApiException as e:
        print("   Could not read the activity codes for this BU: %s" % e)
        return names

    codes = []
    if listing.download_url:
        downloaded = fetch_json_from_url(listing.download_url)
        if downloaded:
            codes = downloaded.get('entities') or []
    else:
        for code in (listing.entities or []):
            codes.append(to_plain_data(code))

    for code in codes:
        code_id = code.get('id')
        if not code_id:
            continue
        # Use the name first. Some built-in codes, like the default Meal code,
        # have an empty name, so we use the category (such as "Meal") instead.
        # A code with neither is left out and shows as "Retired" later.
        display_name = code.get('name') or code.get('category')
        if display_name:
            names[code_id] = display_name
    return names


def get_user_ids_from_agent_data(agent_schedule_data):
    """Return the list of agent user IDs found in the agent schedule data."""
    user_ids = []
    agent_schedules = []
    if isinstance(agent_schedule_data, dict):
        agent_schedules = agent_schedule_data.get('agent_schedules') or []
    for agent in agent_schedules:
        user = agent.get('user') or {}
        if user.get('id'):
            user_ids.append(user.get('id'))
    return user_ids


def get_management_unit_ids(schedule_metadata):
    """Return the management unit (MU) IDs that are part of a schedule.

    Reads the "management_units" list on the schedule metadata and pulls the ID
    out of each one. We need these because the agent schedule pull below asks
    for one MU at a time. The API requires a management unit ID on that pull,
    so we cannot ask for every agent in a single call. Returns a list of ID
    strings, which may be empty if the schedule has no MUs.
    """
    management_unit_ids = []
    summaries = getattr(schedule_metadata, 'management_units', None) or []
    for summary in summaries:
        mu_reference = getattr(summary, 'management_unit', None)
        mu_id = getattr(mu_reference, 'id', None)
        if mu_id:
            management_unit_ids.append(mu_id)
    return management_unit_ids


def load_agent_schedules_for_mu(wfm_api, business_unit_id, week_date, schedule_id,
                                management_unit_id):
    """Return one management unit's (MU's) agent schedule data as plain data.

    This is the heavy pull for a single MU: it asks for every agent's shifts
    and activities in that MU for this week. The API requires the MU ID on this
    call, which is why we pull one MU at a time instead of the whole schedule
    at once. The API may answer in one of two ways, and we handle both:

      1. It sends the data back right away inside the response (small weeks).
      2. It runs the pull as a background job and gives us a download link to
         the finished JSON (larger weeks).

    When it is a background job, we check back on it until it is done, waiting a
    few seconds between checks. Returns the MU's agent schedule data as plain
    Python data (a dict), or None if the pull never finishes or fails.
    """
    # The MU ID is required by the API. Without it the call fails with a 400.
    body = PureCloudPlatformClientV2.BuQueryAgentSchedulesRequest()
    body.management_unit_id = management_unit_id

    try:
        # Genesys API call:
        # post_workforcemanagement_businessunit_week_schedule_agentschedules_query
        # - starts the pull of all agent schedules for this MU and week.
        response = wfm_api.post_workforcemanagement_businessunit_week_schedule_agentschedules_query(
            business_unit_id, week_date, schedule_id, body
        )
    except ApiException as e:
        print("      Could not start the agent schedule pull for MU %s: %s" % (management_unit_id, e))
        return None

    # The response may already be done, or it may still be processing. We check
    # back a limited number of times so a stuck job cannot loop forever.
    for check_number in range(ASYNC_MAX_CHECKS):
        status = getattr(response, 'status', None)
        download_url = getattr(response, 'download_url', None)
        result = getattr(response, 'result', None)

        # Path 1: the finished data is waiting at a download link.
        if download_url:
            return fetch_json_from_url(download_url)

        # Path 2: the finished data came back inside the response itself.
        if result is not None and status in (None, 'Complete', 'Fulfilled'):
            return to_plain_data(result)

        # If the job failed, stop trying for this one MU.
        if status in ('Error', 'Failed', 'Cancelled'):
            print("      The agent schedule job for MU %s ended with status '%s'." % (management_unit_id, status))
            return None

        # Still working. Wait, then ask the API for the latest job status.
        # The same query call returns the current state of the job.
        time.sleep(ASYNC_WAIT_SECONDS)
        try:
            response = wfm_api.post_workforcemanagement_businessunit_week_schedule_agentschedules_query(
                business_unit_id, week_date, schedule_id, body
            )
        except ApiException as e:
            print("      Lost contact with the agent schedule job for MU %s: %s" % (management_unit_id, e))
            return None

    print("      Gave up waiting for the agent schedule job for MU %s to finish." % management_unit_id)
    return None


def load_agent_schedules(wfm_api, business_unit_id, week_date, schedule_id,
                         management_unit_ids):
    """Return the full agent schedule data for one week schedule as plain data.

    The API pulls agent schedules one management unit (MU) at a time, so this
    function asks for each MU in the schedule and then joins the results into
    one combined set. The combined shape matches a single MU response: a dict
    with an "agent_schedules" list holding every agent from every MU, plus the
    business unit time zone. Returns that dict, or None if no MU returned data.
    """
    if not management_unit_ids:
        print("      This schedule lists no management units, so there is nothing to pull.")
        return None

    combined_agent_schedules = []
    business_unit_time_zone = None
    any_data = False

    for management_unit_id in management_unit_ids:
        mu_data = load_agent_schedules_for_mu(
            wfm_api, business_unit_id, week_date, schedule_id, management_unit_id
        )
        if not mu_data:
            continue
        any_data = True

        # Each MU response holds its own list of agents. We add them all to one
        # combined list so the saved files cover the whole schedule.
        mu_agents = mu_data.get('agent_schedules') or []
        combined_agent_schedules.extend(mu_agents)

        # The time zone is the same across MUs in a BU, so we keep the first one
        # we see and reuse it for the combined result.
        if business_unit_time_zone is None:
            business_unit_time_zone = mu_data.get('business_unit_time_zone')

    if not any_data:
        return None

    return {
        'agent_schedules': combined_agent_schedules,
        'business_unit_time_zone': business_unit_time_zone,
    }


def write_shift_and_activity_csvs(folder_path, agent_schedule_data, user_names,
                                  activity_code_names):
    """Write the shift and activity CSV files for one schedule.

    Walks the agent schedule data and flattens it into two Excel-friendly
    files: one row per shift in agent_shifts.csv, and one row per activity
    inside each shift in agent_activities.csv. Each row keeps the ID and adds
    the name next to it. An agent ID with no name shows MISSING_USER_NAME. An
    activity code ID with no name shows MISSING_ACTIVITY_CODE_NAME. Returns a
    (shift count, activity count) tuple. Writes nothing and returns zeros if
    there is no data.
    """
    if not agent_schedule_data:
        return (0, 0)

    # The agent schedule data is a dict with an "agent_schedules" list. Each
    # entry is one agent, and each agent has a list of shifts.
    agent_schedules = []
    if isinstance(agent_schedule_data, dict):
        agent_schedules = agent_schedule_data.get('agent_schedules') or []

    shift_rows = []
    activity_rows = []

    for agent in agent_schedules:
        user = agent.get('user') or {}
        user_id = user.get('id')
        user_name = user_names.get(user_id, MISSING_USER_NAME)
        shifts = agent.get('shifts') or []

        for shift in shifts:
            shift_id = shift.get('id')
            shift_start = shift.get('start_date')
            shift_length = shift.get('length_minutes')
            shift_rows.append({
                'user_id': user_id,
                'user_name': user_name,
                'shift_id': shift_id,
                'start_date': shift_start,
                'length_minutes': shift_length,
            })

            activities = shift.get('activities') or []
            for activity in activities:
                activity_code_id = activity.get('activity_code_id')
                # An activity with no code ID at all gets a blank name. A code
                # ID we cannot find a name for gets the "Retired" placeholder.
                if activity_code_id:
                    activity_code_name = activity_code_names.get(
                        activity_code_id, MISSING_ACTIVITY_CODE_NAME
                    )
                else:
                    activity_code_name = ''
                activity_rows.append({
                    'user_id': user_id,
                    'user_name': user_name,
                    'shift_id': shift_id,
                    'activity_code_id': activity_code_id,
                    'activity_code_name': activity_code_name,
                    'description': activity.get('description'),
                    'start_date': activity.get('start_date'),
                    'length_minutes': activity.get('length_minutes'),
                    'paid': activity.get('paid'),
                })

    write_csv_file(folder_path, 'agent_shifts.csv',
                   ['user_id', 'user_name', 'shift_id', 'start_date', 'length_minutes'],
                   shift_rows)
    write_csv_file(folder_path, 'agent_activities.csv',
                   ['user_id', 'user_name', 'shift_id', 'activity_code_id',
                    'activity_code_name', 'description', 'start_date',
                    'length_minutes', 'paid'],
                   activity_rows)

    return (len(shift_rows), len(activity_rows))


def back_up_one_schedule(wfm_api, users_api, business_unit_id, bu_name, bu_folder,
                         schedule, activity_code_names, user_names):
    """Back up one week schedule to its own folder and return a summary row.

    Does the work for a single schedule: builds its folder, pulls the schedule
    metadata and the full agent schedule data, looks up any agent names we do
    not know yet, writes the JSON and CSV files, and returns a dict describing
    what happened for the run summary. The user_names dict is shared across all
    schedules in the BU and grows as new agents appear.
    """
    schedule_id = schedule.id
    week_date = schedule.week_date
    week_count = getattr(schedule, 'week_count', None)

    week_folder_name = format_week_folder_name(week_date, week_count, schedule_id)
    week_folder = os.path.join(bu_folder, week_folder_name)
    os.makedirs(week_folder, exist_ok=True)

    print("   Backing up schedule %s -> %s" % (schedule_id, week_folder_name))

    # Save the schedule's own list-item record first, so even if later steps
    # fail we still have the schedule's basic details on disk.
    write_json_file(week_folder, 'schedule_list_item.json', to_plain_data(schedule))

    # Pull and save the fuller schedule metadata. We need this for two reasons:
    # it records which management units (MUs) and agents are in the schedule,
    # and it gives us the MU IDs the agent schedule pull below requires. If this
    # read fails we have no MU IDs, so we cannot pull the agent schedules.
    management_unit_ids = []
    try:
        # Genesys API call: get_workforcemanagement_businessunit_week_schedule
        # - returns the schedule metadata.
        metadata = wfm_api.get_workforcemanagement_businessunit_week_schedule(
            business_unit_id, week_date, schedule_id
        )
        write_json_file(week_folder, 'schedule_metadata.json', to_plain_data(metadata))
        management_unit_ids = get_management_unit_ids(metadata)
    except ApiException as e:
        print("      Could not read the schedule metadata: %s" % e)

    # Pull and save the full agent schedule data: every agent's shifts and
    # activities. This is the main content of the backup. The API pulls one MU
    # at a time, so we pass in the MU IDs we found in the metadata.
    agent_schedule_data = load_agent_schedules(
        wfm_api, business_unit_id, week_date, schedule_id, management_unit_ids
    )
    if agent_schedule_data is not None:
        write_json_file(week_folder, 'agent_schedules.json', agent_schedule_data)

        # Find names for any agents in this schedule that we have not seen yet.
        get_user_names(
            users_api, get_user_ids_from_agent_data(agent_schedule_data),
            user_names, missing_name=MISSING_USER_NAME
        )

        shift_count, activity_count = write_shift_and_activity_csvs(
            week_folder, agent_schedule_data, user_names, activity_code_names
        )
        agents_saved = 'yes'
    else:
        shift_count, activity_count = (0, 0)
        agents_saved = 'no'

    return {
        'business_unit_name': bu_name,
        'business_unit_id': business_unit_id,
        'schedule_id': schedule_id,
        'week_folder': week_folder_name,
        'week_date': week_date,
        'agent_data_saved': agents_saved,
        'shift_rows': shift_count,
        'activity_rows': activity_count,
    }


def back_up_business_unit(wfm_api, users_api, business_unit_link):
    """Back up every published schedule for one business unit (BU).

    Looks up the BU name and week start day, makes its folder, reads the
    activity code names, finds all published schedules, and backs each one up.
    Prints a short list of what it found so you can confirm the schedules you
    need are present. When it finishes, it saves the agent and activity code
    name lookups next to the schedule folders. Returns a list of summary rows,
    one per schedule.
    """
    business_unit_id = get_business_unit_id_from_link(business_unit_link)
    bu_name, start_day = get_bu_name_and_start_day(wfm_api, business_unit_id)
    bu_folder = os.path.join(BACKUP_ROOT, clean_folder_name(bu_name))
    os.makedirs(bu_folder, exist_ok=True)

    print("\nBusiness unit: %s (%s), week starts on %s" % (bu_name, business_unit_id, start_day))

    activity_code_names = get_activity_code_names(wfm_api, business_unit_id)
    print("   Read %d activity code name(s)." % len(activity_code_names))
    # This dict starts empty and fills in as we meet agents in each schedule.
    user_names = {}

    schedules = get_published_schedules(wfm_api, business_unit_id, start_day)
    print("   Found %d published schedule(s) the API will give us:" % len(schedules))
    for schedule in schedules:
        print("      - %s  %s  (%s)" % (
            schedule.week_date,
            getattr(schedule, 'description', '') or '',
            schedule.id,
        ))

    summary_rows = []
    for schedule in schedules:
        try:
            summary_rows.append(
                back_up_one_schedule(
                    wfm_api, users_api, business_unit_id, bu_name, bu_folder,
                    schedule, activity_code_names, user_names
                )
            )
        except Exception as e:
            # Catch per-schedule problems so one bad schedule does not stop the
            # backup of the rest.
            print("      Skipped schedule %s because of an error: %s" % (schedule.id, e))

    # Save the lookups so the raw JSON files can be matched to names later.
    write_json_file(bu_folder, 'user_names.json', user_names)
    write_json_file(bu_folder, 'activity_code_names.json', activity_code_names)
    return summary_rows


def write_run_summary(all_summary_rows):
    """Write one CSV that lists every schedule the run tried to back up.

    Saves backup_summary.csv at the top of the backup folder. Each row shows
    the BU, the schedule, its folder, and whether the agent data was saved.
    This is the quick place to confirm the four schedules you need are present.
    """
    field_names = [
        'business_unit_name', 'business_unit_id', 'schedule_id', 'week_folder', 'week_date',
        'agent_data_saved', 'shift_rows', 'activity_rows',
    ]
    write_csv_file(BACKUP_ROOT, 'backup_summary.csv', field_names, all_summary_rows)
    print("\nWrote run summary: %s" % os.path.join(BACKUP_ROOT, 'backup_summary.csv'))


# --- Main --------------------------------------------------------------------
def main():
    """Run the full backup for every business unit in BUSINESS_UNITS.

    Step 1: Sign in to Genesys Cloud.
    Step 2: Make the top backup folder if it is missing.
    Step 3: Back up every published schedule for each BU.
    Step 4: Write a single summary CSV listing everything we backed up.
    """
    (wfm_api, users_api) = build_apis('WorkforceManagementApi', 'UsersApi')

    os.makedirs(BACKUP_ROOT, exist_ok=True)
    print("Writing backups under: %s" % BACKUP_ROOT)

    all_summary_rows = []
    for business_unit_link in BUSINESS_UNITS:
        all_summary_rows.extend(back_up_business_unit(wfm_api, users_api, business_unit_link))

    write_run_summary(all_summary_rows)
    print("\nDone. Backed up %d schedule(s) in total." % len(all_summary_rows))


if __name__ == '__main__':
    main()
