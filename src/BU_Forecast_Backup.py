# =============================================================================
# Genesys Cloud - Business Unit (BU) Short-Term Forecast Backup
# =============================================================================
# Backs up the short-term forecasts for a set of business units (BUs) in
# Workforce Management (WFM) that are being retired. For each BU, the script
# finds every short-term forecast it can reach, then saves all of the forecast
# data to JSON and CSV files on your computer.
#
# This is the forecast partner to BU_Schedule_Backup.py. It uses the same BU
# list, the same two-year lookback, and the same folder naming.
#
# What gets saved for each forecast:
#   - The forecast details (dates, how it was made, any edits made to it).
#   - The planning groups used by the forecast, with their names and the names
#     of the queues that feed them.
#   - The generation results (which forecasting method each metric used).
#   - The forecast numbers: offered volume and average handle time for every
#     15 minute interval, for every planning group.
#   - The long-term numbers: offered volume and average handle time per day.
#   - The staffing requirements for every 15 minute interval.
#
# How far back we look: the "recent" list from Genesys only covers about 26
# weeks before and after today. To reach older forecasts, the script also asks
# for each past week by its date, going back LOOKBACK_WEEKS weeks (104 weeks is
# two years). One forecast can span several weeks and show up more than once,
# so the script keeps only one copy of each forecast ID. The script prints what
# it finds for each BU so you can check that the forecasts you need are there.
#
# Please note - how the CSV files line up with the raw data: Genesys sends the
# forecast numbers as long lists with one value per interval and no time stamp.
# The script works out each interval's start time by counting forward in 15
# minute steps from the forecast's start time. We checked this on a real
# forecast. The daily totals from the interval numbers matched the long-term
# daily numbers exactly. The raw JSON files keep the lists exactly as Genesys
# sent them. The CSV files are the flattened, easier to read copy.
#
# Please note - deleted queues: the forecast only holds queue IDs, so the script
# looks up each queue's name. If a queue has been deleted from Genesys, its name
# cannot be found, and the script writes the MISSING_QUEUE_NAME placeholder
# instead. The queue ID is always kept next to the name.
#
# Please note - blank staffing requirement cells are normal. Genesys sends no
# value for hours when the desk is closed, so you will see blanks outside the
# BU's open hours. A blank is not a failed save.
#
# Please note - the staffing requirements need the permission
# wfm:staffingRequirement:view on the role used by your OAuth client. Without
# it, Genesys answers "403 Forbidden", the script prints a message, and the
# rest of that forecast is still saved.
#
# This script only reads from Genesys. It never changes anything in Genesys.
#
# Output (written under the backup folder set in BACKUP_ROOT below):
#   <BU Name>/
#     W24-2025 06-09 to 07-06 <forecast id>/
#       forecast_list_item.json      The forecast's entry from the list.
#       forecast_detail.json         Full forecast details.
#       planning_groups.json         Raw planning groups used by the forecast.
#       planning_groups.csv          One row per planning group per queue route,
#                                    with the queue ID and queue name.
#       generation_results.json      Raw generation results.
#       generation_results.csv       One row per planning group per metric.
#       forecast_data.json           Raw interval numbers, one entry per week.
#       forecast_intervals.csv       One row per planning group per interval.
#       long_term_data.json          Raw long-term numbers.
#       long_term_daily.csv          One row per planning group per day.
#       staffing_requirements.json   Raw staffing requirements, per week.
#       staffing_requirements.csv    One row per planning group per interval.
#   queue_names.json                 Queue ID to queue name lookup used in this run.
#   backup_summary.csv               One row per forecast we tried to back up.
# =============================================================================

# --- Imports -----------------------------------------------------------------
import os
import json
import time
import datetime
from zoneinfo import ZoneInfo

from PureCloudPlatformClientV2.rest import ApiException

# Shared helpers (sign in, name lookups, BU details, file writers) live in
# genesys_common.py, next to this script.
from genesys_common import (
    build_apis,
    call_api,
    get_business_unit_id_from_link,
    get_bu_name_and_start_day,
    get_past_week_dates,
    get_queue_names,
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

# The top folder where all forecast backups are written. The script makes this
# folder (and every folder under it) if it does not already exist.
BACKUP_ROOT = '/Users/alice.weaver/Documents/BU_Backups/Forecasts'

# The special word "recent" tells Genesys to return every forecast within about
# 26 weeks before and after today. We use it to catch current and upcoming
# forecasts.
WEEK_LISTING_KEY = 'recent'

# How many weeks back from today to look for older forecasts. 104 weeks is two
# years. The script asks for one past week at a time, so a larger number means
# more calls per BU.
LOOKBACK_WEEKS = 104

# Each interval in the forecast numbers is 15 minutes long. We checked this
# against the interval length that Genesys reports with the staffing
# requirements. The script prints a warning if Genesys ever reports a different
# length.
INTERVAL_MINUTES = 15

# Some pulls run as a background job. When one does, we check back on it this
# many times, waiting this many seconds between checks, before we give up on
# that one piece and move on.
ASYNC_MAX_CHECKS = 60
ASYNC_WAIT_SECONDS = 5

# The name written when a queue's name cannot be found, which happens when the
# queue has been deleted from Genesys. Change this text if you prefer another.
MISSING_QUEUE_NAME = 'Deleted Queue'


# --- Helpers -----------------------------------------------------------------
def parse_start_time(value):
    """Return a date and time with a time zone from a value Genesys sent.

    Handles the three forms we see: a datetime object (from the SDK), a plain
    date (the long-term numbers), and text like "2025-06-09T06:00:00Z" (from
    download files). Plain dates and times with no time zone are treated as
    Coordinated Universal Time, which is the time zone Genesys uses. Returns
    None if the value is missing.
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        start_time = value
    elif isinstance(value, datetime.date):
        start_time = datetime.datetime(value.year, value.month, value.day)
    else:
        start_time = datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=datetime.timezone.utc)
    return start_time


def get_time_zone(forecast_detail):
    """Return the forecast's time zone as a ZoneInfo, or None if unavailable.

    The forecast detail holds the time zone as a name like "America/Denver".
    We use it to write the local time next to each interval. Returns None if
    the name is missing or not one Python knows, and then the local time
    column is left blank.
    """
    time_zone_name = (forecast_detail or {}).get('time_zone')
    if not time_zone_name:
        return None
    try:
        return ZoneInfo(time_zone_name)
    except Exception:
        print("      Unknown time zone '%s'. The local time column will be blank." % time_zone_name)
        return None


def format_time(start_time, time_zone=None):
    """Return a date and time as text like "2025-06-09 06:00".

    If a time zone is given, the time is first changed to that zone. Without
    one, it stays in Coordinated Universal Time. Returns a blank string when
    there is no time or no zone to convert to.
    """
    if start_time is None:
        return ''
    if time_zone is not None:
        start_time = start_time.astimezone(time_zone)
    return start_time.strftime('%Y-%m-%d %H:%M')


def read_result_or_download(response):
    """Return the data from a forecast response as plain data, or None.

    Genesys answers in one of two ways: the data is inside "result", or "result"
    is empty and "download_url" points to a file. We handle both. Returns None
    if neither holds data.
    """
    result = getattr(response, 'result', None)
    if result is not None:
        return to_plain_data(result)

    download_url = getattr(response, 'download_url', None)
    if download_url:
        downloaded = fetch_json_from_url(download_url)
        if downloaded is None:
            return None
        # The downloaded file may wrap the data in a "result" entry.
        return downloaded.get('result') or downloaded
    return None


# --- Steps: find the forecasts -----------------------------------------------
def get_forecasts(wfm_api, business_unit_id, start_day):
    """Return the short-term forecasts for one business unit (BU).

    Step 1: Ask Genesys for its "recent" list (about 26 weeks each way).
    Step 2: Ask for each past week by date, going back LOOKBACK_WEEKS weeks, to
            reach forecasts older than the "recent" list.
    Step 3: Keep one copy of each forecast ID, because one forecast can show up
            in several weeks.

    A failed lookup for one week is printed and skipped so it does not stop the
    rest. Returns a list of forecast list items, oldest first.
    """
    forecasts_by_id = {}

    # Step 1: the "recent" list.
    try:
        # Genesys API call: get_workforcemanagement_businessunit_week_shorttermforecasts
        # with the word "recent" - lists all forecasts in the window.
        listing = call_api(
            wfm_api.get_workforcemanagement_businessunit_week_shorttermforecasts,
            business_unit_id, WEEK_LISTING_KEY
        )
        for forecast in (listing.entities or []):
            forecasts_by_id[forecast.id] = forecast
    except ApiException as e:
        print("   Could not list the recent forecasts for this BU: %s" % e)

    # Step 2: each past week, one at a time.
    print("   Checking %d past weeks for older forecasts..." % LOOKBACK_WEEKS)
    for week_date in get_past_week_dates(start_day, LOOKBACK_WEEKS):
        try:
            # Same call, but with a real week date instead of "recent". It
            # returns any forecast that spans that week.
            listing = call_api(
                wfm_api.get_workforcemanagement_businessunit_week_shorttermforecasts,
                business_unit_id, week_date.isoformat()
            )
            for forecast in (listing.entities or []):
                forecasts_by_id[forecast.id] = forecast
        except ApiException as e:
            print("      Could not list forecasts for the week of %s: %s" % (week_date, e))

    # Step 3: oldest first.
    forecasts = list(forecasts_by_id.values())
    forecasts.sort(key=lambda item: item.week_date)
    return forecasts


# --- Steps: pull the data for one forecast -----------------------------------
def pull_forecast_detail(wfm_api, business_unit_id, week_date, forecast_id):
    """Return the full details of one forecast as plain data, or None on failure."""
    try:
        # Genesys API call: get_workforcemanagement_businessunit_week_shorttermforecast
        # - returns the forecast details.
        detail = call_api(
            wfm_api.get_workforcemanagement_businessunit_week_shorttermforecast,
            business_unit_id, week_date, forecast_id
        )
        return to_plain_data(detail)
    except ApiException as e:
        print("      Could not read the forecast details: %s" % e)
        return None


def pull_planning_groups(wfm_api, business_unit_id, week_date, forecast_id):
    """Return the planning groups used by one forecast as plain data, or None.

    This is a snapshot of the planning groups as they were for this forecast.
    It holds each group's name and the queues that feed it. We need it because
    the forecast numbers only carry planning group IDs.
    """
    try:
        # Genesys API call: ..._shorttermforecast_planninggroups - returns the
        # planning group snapshot for the forecast.
        groups = call_api(
            wfm_api.get_workforcemanagement_businessunit_week_shorttermforecast_planninggroups,
            business_unit_id, week_date, forecast_id
        )
        return to_plain_data(groups)
    except ApiException as e:
        print("      Could not read the planning groups: %s" % e)
        return None


def pull_generation_results(wfm_api, business_unit_id, week_date, forecast_id):
    """Return the generation results for one forecast as plain data, or None."""
    try:
        # Genesys API call: ..._shorttermforecast_generationresults - returns
        # which forecasting method each planning group metric used.
        results = call_api(
            wfm_api.get_workforcemanagement_businessunit_week_shorttermforecast_generationresults,
            business_unit_id, week_date, forecast_id
        )
        return to_plain_data(results)
    except ApiException as e:
        print("      Could not read the generation results: %s" % e)
        return None


def pull_forecast_data(wfm_api, business_unit_id, week_date, forecast_id, week_count):
    """Return the interval numbers for every week of one forecast.

    A forecast with several weeks has to be pulled one week at a time. Returns
    a list of plain data results in week order. A week that fails is printed
    and left out, so the list may be shorter than week_count. The caller checks
    the length to report a partial save.
    """
    weeks = []
    for week_number in range(1, (week_count or 1) + 1):
        try:
            # Genesys API call: ..._shorttermforecast_data with a week number -
            # returns offered volume and average handle time for each interval.
            response = call_api(
                wfm_api.get_workforcemanagement_businessunit_week_shorttermforecast_data,
                business_unit_id, week_date, forecast_id, week_number=week_number
            )
        except ApiException as e:
            print("      Could not read the forecast data for week %d: %s" % (week_number, e))
            continue

        week_result = read_result_or_download(response)
        if week_result is None:
            print("      The forecast data for week %d came back empty." % week_number)
            continue
        week_result.setdefault('week_number', week_number)
        weeks.append(week_result)
    return weeks


def pull_long_term_data(wfm_api, business_unit_id, week_date, forecast_id):
    """Return the long-term (per day) numbers for one forecast, or None."""
    try:
        # Genesys API call: ..._shorttermforecast_longtermforecastdata - returns
        # offered volume and average handle time for each day.
        response = call_api(
            wfm_api.get_workforcemanagement_businessunit_week_shorttermforecast_longtermforecastdata,
            business_unit_id, week_date, forecast_id
        )
    except ApiException as e:
        print("      Could not read the long-term data: %s" % e)
        return None

    long_term = read_result_or_download(response)
    if long_term is None:
        print("      The long-term data came back empty.")
    return long_term


def pull_staffing_requirements(wfm_api, business_unit_id, week_date, forecast_id):
    """Return the staffing requirements for one forecast, week by week.

    Genesys builds these in the background. The first call can start the job
    and come back with no results, so we check back until the state is
    "Complete". Each week's numbers then sit in their own download file, which
    we read. Returns a (weeks, expected week count) tuple. weeks is a list of
    plain data, one per week we could read. Returns (None, 0) if the job never
    finishes or fails, including a 403 caused by a missing permission.
    """
    response = None
    is_complete = False
    for check_number in range(ASYNC_MAX_CHECKS):
        try:
            # Genesys API call: ..._shorttermforecast_staffingrequirement -
            # starts or reads the staffing requirements job.
            response = call_api(
                wfm_api.get_workforcemanagement_businessunit_week_shorttermforecast_staffingrequirement,
                business_unit_id, week_date, forecast_id
            )
        except ApiException as e:
            if e.status == 403:
                print("      No permission for staffing requirements. The role needs wfm:staffingRequirement:view.")
            else:
                print("      Could not read the staffing requirements: %s" % e)
            return (None, 0)

        state = getattr(response, 'state', None)
        if state == 'Complete':
            is_complete = True
            break
        if state in ('Error', 'Failed'):
            print("      The staffing requirements job ended with state '%s'." % state)
            return (None, 0)
        time.sleep(ASYNC_WAIT_SECONDS)

    if not is_complete:
        print("      Gave up waiting for the staffing requirements job to finish.")
        return (None, 0)

    # Warn if the interval length is not what we assumed, because every time
    # stamp we write depends on it.
    reported_length = getattr(response, 'interval_length_minutes', None)
    if reported_length and reported_length != INTERVAL_MINUTES:
        print("      WARNING: Genesys reports %s minute intervals, but INTERVAL_MINUTES is %d. "
              "Interval start times will be wrong." % (reported_length, INTERVAL_MINUTES))

    result_items = response.results or []
    weeks = []
    for item in result_items:
        week_data = to_plain_data(item)
        # The download link is temporary and useless in a backup, so we drop it
        # after using it.
        download_url = week_data.pop('download_url', None)
        week_data.pop('download_url_expiration_date', None)

        if download_url:
            downloaded = fetch_json_from_url(download_url)
            if downloaded is None:
                print("      Could not read the staffing file for week %s." % week_data.get('week_number'))
                continue
            week_data['planning_group_staffing_requirements'] = (
                downloaded.get('planning_group_staffing_requirements') or []
            )
        weeks.append(week_data)
    return (weeks, len(result_items))


# --- Steps: flatten the data into CSV rows -----------------------------------
def get_planning_group_names(planning_groups_data):
    """Return a dict that maps planning group ID to planning group name.

    Reads the planning group snapshot for the forecast. Returns an empty dict
    if there is no snapshot, and then the name columns are left blank.
    """
    names = {}
    entities = (planning_groups_data or {}).get('entities') or []
    for group in entities:
        if group.get('id'):
            names[group['id']] = group.get('name')
    return names


def get_queue_ids_from_planning_groups(planning_groups_data):
    """Return the list of queue IDs used by the planning groups, with no repeats."""
    queue_ids = []
    entities = (planning_groups_data or {}).get('entities') or []
    for group in entities:
        for route in (group.get('route_paths') or []):
            queue = route.get('queue') or {}
            queue_id = queue.get('id')
            if queue_id and queue_id not in queue_ids:
                queue_ids.append(queue_id)
    return queue_ids


def build_planning_group_rows(planning_groups_data, queue_names):
    """Return CSV rows for the planning groups, one row per queue route.

    A planning group can send work from several queues, so it gets one row for
    each route. A group with no routes still gets one row. Each queue ID gets
    its name next to it. The skills and service goal template are saved as JSON
    text so they fit in one cell.
    """
    rows = []
    entities = (planning_groups_data or {}).get('entities') or []
    for group in entities:
        route_paths = group.get('route_paths') or []
        goal_template_text = json.dumps(group.get('service_goal_template'), default=str)

        if not route_paths:
            rows.append({
                'planning_group_id': group.get('id'),
                'planning_group_name': group.get('name'),
                'queue_id': '',
                'queue_name': '',
                'media_type': '',
                'language_id': '',
                'skills': '',
                'service_goal_template': goal_template_text,
            })
            continue

        for route in route_paths:
            queue = route.get('queue') or {}
            # The language is a small record with an ID. We save just the ID so
            # the cell stays clean. A route with no language leaves it blank.
            language = route.get('language') or {}
            queue_id = queue.get('id')
            rows.append({
                'planning_group_id': group.get('id'),
                'planning_group_name': group.get('name'),
                'queue_id': queue_id,
                'queue_name': queue_names.get(queue_id, '') if queue_id else '',
                'media_type': route.get('media_type'),
                'language_id': language.get('id'),
                'skills': json.dumps(route.get('skills'), default=str),
                'service_goal_template': goal_template_text,
            })
    return rows


def build_generation_rows(generation_data, planning_group_names):
    """Return CSV rows for the generation results, one row per group per metric."""
    rows = []
    group_results = (generation_data or {}).get('planning_group_results') or []
    for group_result in group_results:
        group_id = group_result.get('planning_group_id')
        for metric_result in (group_result.get('metric_results') or []):
            rows.append({
                'planning_group_id': group_id,
                'planning_group_name': planning_group_names.get(group_id),
                'metric': metric_result.get('metric'),
                'forecasting_method': metric_result.get('forecasting_method'),
                'forecast_type': metric_result.get('forecast_type'),
            })
    return rows


def build_interval_rows(week_results, reference_start, time_zone, planning_group_names):
    """Return CSV rows for the forecast numbers, one row per group per interval.

    Genesys sends each planning group's numbers as lists with one value per
    interval. The weeks of a forecast follow each other, so for every planning
    group we keep a running count of the intervals already used. That count
    tells us how far past the forecast's start time each value belongs. The
    start time of an interval is the forecast start plus (count times
    INTERVAL_MINUTES). Returns a list of row dicts.
    """
    rows = []
    intervals_used = {}

    for week_result in week_results:
        week_number = week_result.get('week_number')
        for group in (week_result.get('planning_groups') or []):
            group_id = group.get('planning_group_id')
            offered_list = group.get('offered_per_interval') or []
            handle_time_list = group.get('average_handle_time_seconds_per_interval') or []
            first_index = intervals_used.get(group_id, 0)

            for position in range(len(offered_list)):
                interval_start = reference_start + datetime.timedelta(
                    minutes=INTERVAL_MINUTES * (first_index + position)
                )
                handle_time = None
                if position < len(handle_time_list):
                    handle_time = handle_time_list[position]
                rows.append({
                    'interval_start': format_time(interval_start),
                    'interval_start_local': format_time(interval_start, time_zone),
                    'week_number': week_number,
                    'planning_group_id': group_id,
                    'planning_group_name': planning_group_names.get(group_id),
                    'offered': offered_list[position],
                    'average_handle_time_seconds': handle_time,
                })
            intervals_used[group_id] = first_index + len(offered_list)
    return rows


def build_long_term_rows(long_term_data, planning_group_names):
    """Return CSV rows for the long-term numbers, one row per group per day."""
    rows = []
    start_time = parse_start_time((long_term_data or {}).get('reference_start_date'))
    if start_time is None:
        return rows

    for group in ((long_term_data or {}).get('planning_groups') or []):
        group_id = group.get('planning_group_id')
        offered_list = group.get('offered_per_day') or []
        handle_time_list = group.get('average_handle_time_seconds_per_day') or []

        for position in range(len(offered_list)):
            day = start_time + datetime.timedelta(days=position)
            handle_time = None
            if position < len(handle_time_list):
                handle_time = handle_time_list[position]
            rows.append({
                'date': day.strftime('%Y-%m-%d'),
                'planning_group_id': group_id,
                'planning_group_name': planning_group_names.get(group_id),
                'offered': offered_list[position],
                'average_handle_time_seconds': handle_time,
            })
    return rows


def build_staffing_rows(staffing_weeks, reference_start, time_zone, planning_group_names):
    """Return CSV rows for the staffing requirements, one row per group per interval.

    Works the same way as build_interval_rows: each week continues where the
    last one ended, so a running count of intervals tells us each start time.
    """
    rows = []
    intervals_used = {}

    for week_data in staffing_weeks:
        week_number = week_data.get('week_number')
        for group in (week_data.get('planning_group_staffing_requirements') or []):
            group_id = group.get('planning_group_id')
            requirement_list = group.get('staffing_requirements_per_interval') or []
            first_index = intervals_used.get(group_id, 0)

            for position in range(len(requirement_list)):
                interval_start = reference_start + datetime.timedelta(
                    minutes=INTERVAL_MINUTES * (first_index + position)
                )
                rows.append({
                    'interval_start': format_time(interval_start),
                    'interval_start_local': format_time(interval_start, time_zone),
                    'week_number': week_number,
                    'planning_group_id': group_id,
                    'planning_group_name': planning_group_names.get(group_id),
                    'staffing_requirement': requirement_list[position],
                })
            intervals_used[group_id] = first_index + len(requirement_list)
    return rows


# --- Steps: back up forecasts ------------------------------------------------
def back_up_one_forecast(wfm_api, routing_api, business_unit_id, bu_name, bu_folder,
                         forecast, queue_names):
    """Back up one forecast to its own folder and return a summary row.

    The queue_names dict is shared across the whole run and grows as new queues
    appear, so each queue is only looked up once.

    Step 1: Make the forecast's folder.
    Step 2: Pull each piece of data on its own, so one failure does not stop
            the others: details, planning groups, generation results, interval
            numbers, long-term numbers, and staffing requirements.
    Step 3: Write the raw JSON and the flattened CSV for each piece we got.
    Step 4: Return a dict that says which pieces were saved, for the summary.
    """
    forecast_id = forecast.id
    week_date = forecast.week_date
    week_count = getattr(forecast, 'week_count', None) or 1

    week_folder_name = format_week_folder_name(week_date, week_count, forecast_id)
    week_folder = os.path.join(bu_folder, week_folder_name)
    os.makedirs(week_folder, exist_ok=True)

    print("   Backing up forecast %s -> %s" % (forecast_id, week_folder_name))

    # Save the forecast's own list entry first, so even if later steps fail we
    # still have its basic details on disk.
    write_json_file(week_folder, 'forecast_list_item.json', to_plain_data(forecast))

    # Step 2: pull every piece.
    detail = pull_forecast_detail(wfm_api, business_unit_id, week_date, forecast_id)
    planning_groups = pull_planning_groups(wfm_api, business_unit_id, week_date, forecast_id)
    generation = pull_generation_results(wfm_api, business_unit_id, week_date, forecast_id)
    data_weeks = pull_forecast_data(wfm_api, business_unit_id, week_date, forecast_id, week_count)
    long_term = pull_long_term_data(wfm_api, business_unit_id, week_date, forecast_id)
    staffing_weeks, staffing_expected = pull_staffing_requirements(
        wfm_api, business_unit_id, week_date, forecast_id
    )

    planning_group_names = get_planning_group_names(planning_groups)
    time_zone = get_time_zone(detail)

    # Look up the names of any queues in this forecast we have not seen yet.
    get_queue_names(
        routing_api, get_queue_ids_from_planning_groups(planning_groups),
        queue_names, missing_name=MISSING_QUEUE_NAME
    )

    # The forecast start time anchors every interval time stamp. The details
    # hold it. If they are missing, we fall back to the first week of data.
    reference_start = None
    if detail:
        reference_start = parse_start_time(detail.get('reference_start_date'))
    if reference_start is None and data_weeks:
        reference_start = parse_start_time(data_weeks[0].get('reference_start_date'))

    # Step 3: write the files for each piece we got.
    interval_row_count = 0
    long_term_row_count = 0
    staffing_row_count = 0

    if detail is not None:
        write_json_file(week_folder, 'forecast_detail.json', detail)

    if planning_groups is not None:
        write_json_file(week_folder, 'planning_groups.json', planning_groups)
        write_csv_file(
            week_folder, 'planning_groups.csv',
            ['planning_group_id', 'planning_group_name', 'queue_id', 'queue_name',
             'media_type', 'language_id', 'skills', 'service_goal_template'],
            build_planning_group_rows(planning_groups, queue_names)
        )

    if generation is not None:
        write_json_file(week_folder, 'generation_results.json', generation)
        write_csv_file(
            week_folder, 'generation_results.csv',
            ['planning_group_id', 'planning_group_name', 'metric',
             'forecasting_method', 'forecast_type'],
            build_generation_rows(generation, planning_group_names)
        )

    if data_weeks:
        write_json_file(week_folder, 'forecast_data.json', data_weeks)
        if reference_start is not None:
            interval_rows = build_interval_rows(
                data_weeks, reference_start, time_zone, planning_group_names
            )
            write_csv_file(
                week_folder, 'forecast_intervals.csv',
                ['interval_start', 'interval_start_local', 'week_number',
                 'planning_group_id', 'planning_group_name', 'offered',
                 'average_handle_time_seconds'],
                interval_rows
            )
            interval_row_count = len(interval_rows)
        else:
            print("      No forecast start time was found, so forecast_intervals.csv was not written.")

    if long_term is not None:
        write_json_file(week_folder, 'long_term_data.json', long_term)
        long_term_rows = build_long_term_rows(long_term, planning_group_names)
        write_csv_file(
            week_folder, 'long_term_daily.csv',
            ['date', 'planning_group_id', 'planning_group_name', 'offered',
             'average_handle_time_seconds'],
            long_term_rows
        )
        long_term_row_count = len(long_term_rows)

    if staffing_weeks:
        write_json_file(week_folder, 'staffing_requirements.json', staffing_weeks)
        if reference_start is not None:
            staffing_rows = build_staffing_rows(
                staffing_weeks, reference_start, time_zone, planning_group_names
            )
            write_csv_file(
                week_folder, 'staffing_requirements.csv',
                ['interval_start', 'interval_start_local', 'week_number',
                 'planning_group_id', 'planning_group_name', 'staffing_requirement'],
                staffing_rows
            )
            staffing_row_count = len(staffing_rows)
        else:
            print("      No forecast start time was found, so staffing_requirements.csv was not written.")

    # Step 4: describe what we saved. "all_saved" is the quick column to filter
    # on in the summary file to find forecasts with gaps.
    data_ok = len(data_weeks) == week_count
    staffing_ok = staffing_weeks is not None and len(staffing_weeks) == staffing_expected
    all_saved = (
        detail is not None and planning_groups is not None and generation is not None
        and data_ok and long_term is not None and staffing_ok
    )

    return {
        'business_unit_name': bu_name,
        'business_unit_id': business_unit_id,
        'forecast_id': forecast_id,
        'week_folder': week_folder_name,
        'week_date': week_date,
        'week_count': week_count,
        'all_saved': 'yes' if all_saved else 'NO - check messages above',
        'detail_saved': 'yes' if detail is not None else 'no',
        'planning_groups_saved': 'yes' if planning_groups is not None else 'no',
        'generation_saved': 'yes' if generation is not None else 'no',
        'data_weeks_saved': "%d of %d" % (len(data_weeks), week_count),
        'long_term_saved': 'yes' if long_term is not None else 'no',
        'staffing_weeks_saved': "%d of %d" % (len(staffing_weeks or []), staffing_expected),
        'interval_rows': interval_row_count,
        'long_term_rows': long_term_row_count,
        'staffing_rows': staffing_row_count,
    }


def back_up_business_unit(wfm_api, routing_api, business_unit_link, queue_names):
    """Back up every short-term forecast for one business unit (BU).

    Looks up the BU name and week start day, makes its folder, finds all
    forecasts, and backs each one up. Prints a short list of what it found so
    you can confirm the forecasts you need are present. Returns a list of
    summary rows, one per forecast.
    """
    business_unit_id = get_business_unit_id_from_link(business_unit_link)
    bu_name, start_day = get_bu_name_and_start_day(wfm_api, business_unit_id)
    bu_folder = os.path.join(BACKUP_ROOT, clean_folder_name(bu_name))
    os.makedirs(bu_folder, exist_ok=True)

    print("\nBusiness unit: %s (%s), week starts on %s" % (bu_name, business_unit_id, start_day))

    forecasts = get_forecasts(wfm_api, business_unit_id, start_day)
    print("   Found %d forecast(s) Genesys will give us:" % len(forecasts))
    for forecast in forecasts:
        print("      - %s  %s weeks  %s  (%s)" % (
            forecast.week_date,
            getattr(forecast, 'week_count', '?'),
            getattr(forecast, 'description', '') or '',
            forecast.id,
        ))

    summary_rows = []
    for forecast in forecasts:
        try:
            summary_rows.append(
                back_up_one_forecast(
                    wfm_api, routing_api, business_unit_id, bu_name, bu_folder,
                    forecast, queue_names
                )
            )
        except Exception as e:
            # Catch per-forecast problems so one bad forecast does not stop the
            # backup of the rest.
            print("      Skipped forecast %s because of an error: %s" % (forecast.id, e))
    return summary_rows


def write_run_summary(all_summary_rows):
    """Write one CSV that lists every forecast the run tried to back up.

    Saves backup_summary.csv at the top of the backup folder. Each row shows
    the BU, the forecast, its folder, and which pieces were saved. The
    "all_saved" column is the quick place to spot a forecast with a gap.
    """
    field_names = [
        'business_unit_name', 'business_unit_id', 'forecast_id', 'week_folder',
        'week_date', 'week_count', 'all_saved', 'detail_saved',
        'planning_groups_saved', 'generation_saved', 'data_weeks_saved',
        'long_term_saved', 'staffing_weeks_saved', 'interval_rows',
        'long_term_rows', 'staffing_rows',
    ]
    write_csv_file(BACKUP_ROOT, 'backup_summary.csv', field_names, all_summary_rows)
    print("\nWrote run summary: %s" % os.path.join(BACKUP_ROOT, 'backup_summary.csv'))


# --- Main --------------------------------------------------------------------
def main():
    """Run the full forecast backup for every business unit in BUSINESS_UNITS.

    Step 1: Sign in to Genesys Cloud.
    Step 2: Make the top backup folder if it is missing.
    Step 3: Back up every forecast for each BU. The summary file and the queue
            name lookup are rewritten after each BU, so a stop partway through
            still leaves both.
    Step 4: Print how many forecasts were backed up and how many have gaps.
    """
    (wfm_api, routing_api) = build_apis('WorkforceManagementApi', 'RoutingApi')

    os.makedirs(BACKUP_ROOT, exist_ok=True)
    print("Writing forecast backups under: %s" % BACKUP_ROOT)

    # Queue names are the same across BUs, so this one dict is shared by the
    # whole run. It starts empty and fills in as we meet queues.
    queue_names = {}

    all_summary_rows = []
    for business_unit_link in BUSINESS_UNITS:
        all_summary_rows.extend(
            back_up_business_unit(wfm_api, routing_api, business_unit_link, queue_names)
        )
        write_run_summary(all_summary_rows)
        write_json_file(BACKUP_ROOT, 'queue_names.json', queue_names)

    forecasts_with_gaps = 0
    for row in all_summary_rows:
        if row['all_saved'] != 'yes':
            forecasts_with_gaps += 1

    print("\nDone. Backed up %d forecast(s) in total." % len(all_summary_rows))
    if forecasts_with_gaps:
        print("%d forecast(s) are missing something. See the all_saved column in backup_summary.csv."
              % forecasts_with_gaps)


if __name__ == '__main__':
    main()
