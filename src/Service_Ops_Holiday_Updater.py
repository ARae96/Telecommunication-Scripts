# =============================================================================
# Genesys Cloud - Update The Holiday Decision In Service Ops Flows
# =============================================================================
# Many of our call flows start with the same decision at the top: a check that
# asks whether "right now" falls inside one of our holiday closure windows. When
# it is a holiday, the flow sends the caller down a different, closed-for-the-
# holiday path. Today we edit that check by hand in the Genesys Cloud Architect
# user interface (UI), one flow at a time. This script does that same edit for
# you, across a list of flows, using the Architect API.
#
# Why this script exists: holidays move around the calendar from year to year,
# and the days we close can change. Instead of hand-typing a long expression in
# the UI each time, you keep a plain list of holidays near the top of this file
# (name, dates, and the hour offset for that date). The script turns that list
# into the same kind of expression we would write by hand and pushes it to every
# flow you list. When the holidays change, you edit the list, not the expression.
#
# What the script changes: only the holiday decision expression at the top of
# the flow. It finds that expression by its shape - date windows built from
# MakeDateTime(...) and joined by "Or" - which is unique to the holiday check.
#
# What the script leaves alone: the hours-of-operation checks deeper in the flow
# (the ones that use DayOfWeek to tell weekdays from weekends). Those are
# maintained by a separate script, Service_Ops_Flow_Updater.py, which flips the
# time offset twice a year. This script never touches them, because it only
# matches the holiday-style expression and refuses to touch a DayOfWeek one.
#
# What the script does for each flow you list:
#   Step 1: Check out the flow so we can edit it (same as opening it in the UI).
#   Step 2: Export the flow to YAML (the flow's full definition as text).
#   Step 3: Find the one holiday expression and swap it for a new expression
#           built from the holiday list below.
#   Step 4: Import the edited YAML back onto the same flow.
#   Step 5: Publish the flow so the change goes live.
#
# How the script finds the right expression to replace: it does NOT rely on the
# holiday decision being "the first one." It looks for the expression whose text
# is made only of MakeDateTime(...) date windows joined by And/Or, and never
# mentions DayOfWeek. That shape is unique to the holiday check. Before changing
# anything, the script confirms it found exactly one such expression. If it
# finds none, or more than one, it stops and changes nothing, because guessing
# could break the flow.
#
# Safety: this script changes live Genesys Cloud flows, so it honors a DRY_RUN
# flag that defaults to True. While DRY_RUN is True it only reads: it checks out
# and exports each flow, shows you the old expression and the new one it would
# write, and then stops without importing or publishing. Set DRY_RUN to False
# only once the preview looks right.
#
# Run locally with:
#   pip install -r requirements.txt
# and a populated .env (GENESYS_CLOUD_CLIENT_ID / GENESYS_CLOUD_CLIENT_SECRET).
# =============================================================================


# --- Imports -----------------------------------------------------------------
import os
import re
import time
import urllib.request

import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from dotenv import load_dotenv


# --- Configuration -----------------------------------------------------------
# The flows to update. Add as many flow IDs as you need, one per line. The same
# holiday expression is written to every flow in this list, so only list flows
# that share the same holiday schedule.
FLOW_IDS = [
    'REPLACE-WITH-FLOW-ID',
]

# The holidays that should send callers down the closure path. Each holiday is
# one entry with four plain values:
#   name       - a label, only used in the printout so you can read the list.
#   start      - the first moment of the closure, as (year, month, day).
#   end        - the first moment AFTER the closure, as (year, month, day). The
#                window is "start up to, but not including, end", so a one-day
#                closure uses the next day as its end. A two-day closure (like a
#                holiday plus the day after) uses the day after the last day.
#   utc_offset - the hours to add to Coordinated Universal Time (UTC) to get our
#                local time on that date. We use -6 when the date is in daylight
#                saving time and -7 the rest of the year. If you are unsure which
#                one a date needs, copy the offset used for a nearby date in the
#                current expression.
#
# This list is the one place you edit when the holiday schedule changes. Add a
# new holiday, remove one we no longer close for, or move a date, then run the
# script to push the new expression out.
HOLIDAYS = [
    {'name': 'Martin Luther King Jr. Day', 'start': (2026, 1, 19),  'end': (2026, 1, 20),  'utc_offset': -7},
    {'name': "Presidents' Day",            'start': (2026, 2, 16),  'end': (2026, 2, 17),  'utc_offset': -7},
    {'name': 'Memorial Day',               'start': (2026, 5, 25),  'end': (2026, 5, 26),  'utc_offset': -6},
    {'name': 'Juneteenth',                 'start': (2026, 6, 19),  'end': (2026, 6, 20),  'utc_offset': -6},
    {'name': 'Independence Day',           'start': (2026, 7, 3),   'end': (2026, 7, 5),   'utc_offset': -6},
    {'name': 'Pioneer Day',                'start': (2026, 8, 26),  'end': (2026, 8, 27),  'utc_offset': -6},
    {'name': 'Labor Day',                  'start': (2026, 9, 7),   'end': (2026, 9, 8),   'utc_offset': -6},
    {'name': 'Thanksgiving',               'start': (2026, 11, 26), 'end': (2026, 11, 27), 'utc_offset': -7},
    {'name': 'Day After Thanksgiving',     'start': (2026, 11, 27), 'end': (2026, 11, 28), 'utc_offset': -7},
    {'name': 'Christmas',                  'start': (2026, 12, 24), 'end': (2026, 12, 26), 'utc_offset': -7},
]

# While DRY_RUN is True the script only reads. It checks out and exports each
# flow, prints the old and new expression, and stops before importing or
# publishing. No flow is changed. Set this to False to actually write the new
# expression and publish.
DRY_RUN = True

# A long-running Architect job (export or import) is not finished the instant
# we start it, so we ask for its status over and over until it reaches a final
# state. We wait POLL_SECONDS between checks and give up after POLL_MAX_TRIES
# checks so a stuck job cannot make the script wait forever.
POLL_SECONDS = 3
POLL_MAX_TRIES = 60


# --- Authentication ----------------------------------------------------------
def build_apis():
    """Sign in to Genesys Cloud and return the Architect API client.

    Reads GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET from the .env
    file at the workspace root (one folder up from this script). Stops the
    script with a helpful message if either value is missing. Returns the
    ArchitectApi client, which is the only client this script needs.
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
    return PureCloudPlatformClientV2.ArchitectApi(apiclient)


# --- Build the new expression ------------------------------------------------
def build_holiday_window(holiday):
    """Return the expression text for one holiday's date window.

    Builds the same shape we write by hand in the UI for a single holiday:

        ((AddHours(GetCurrentDateTimeUtc(), OFFSET) >= MakeDateTime(START))
         And (AddHours(GetCurrentDateTimeUtc(), OFFSET) < MakeDateTime(END)))

    The check says "local time is at or after the start, and before the end",
    which is how a closure window is matched. The offset turns UTC into our
    local time for that date (see the note on utc_offset in HOLIDAYS).
    """
    offset = holiday['utc_offset']
    start_year, start_month, start_day = holiday['start']
    end_year, end_month, end_day = holiday['end']

    # "local now" is the same subexpression used on both sides of the window,
    # so build it once and reuse it to keep the text consistent.
    local_now = "AddHours(GetCurrentDateTimeUtc(), %d)" % offset
    start_moment = "MakeDateTime(%d, %d, %d, 0, 0, 0)" % (start_year, start_month, start_day)
    end_moment = "MakeDateTime(%d, %d, %d, 0, 0, 0)" % (end_year, end_month, end_day)

    return "((%s >= %s) And (%s < %s))" % (local_now, start_moment, local_now, end_moment)


def build_holiday_expression(holidays):
    """Return the full holiday expression built from the holiday list.

    Joins each holiday's window (from build_holiday_window) with "Or" so the
    whole expression is true when "now" falls inside any one of the windows.
    This is the exact text we would otherwise type into the decision by hand.

    Stops the script if the holiday list is empty, because an empty expression
    would be meaningless and could break the decision if it were ever written.
    """
    if not holidays:
        raise SystemExit(
            "The HOLIDAYS list is empty, so there is no expression to build. Add "
            "at least one holiday near the top of the script before running."
        )

    windows = []
    for holiday in holidays:
        windows.append(build_holiday_window(holiday))

    # Join the windows with " Or " on its own line so the result reads as one
    # long "window Or window Or window" expression, matching the hand-written
    # form the UI produces.
    return "\n\nOr ".join(windows)


# --- Find and replace the expression in the exported YAML --------------------
# An Architect holiday window looks like a pair of MakeDateTime(...) checks on
# AddHours(GetCurrentDateTimeUtc(), N), joined by And and wrapped in parentheses.
# This pattern matches one such window. We use it to find the holiday block and
# to confirm the block we are about to replace really is the holiday check and
# nothing else. The pattern is deliberately loose about spacing so small
# formatting differences in the exported YAML do not cause a miss.
_WINDOW_PATTERN = re.compile(
    r"\(\s*\(\s*AddHours\(\s*GetCurrentDateTimeUtc\(\)\s*,\s*-?\d+\s*\)\s*>=\s*"
    r"MakeDateTime\([^)]*\)\s*\)\s*And\s*\(\s*AddHours\(\s*GetCurrentDateTimeUtc\(\)\s*,\s*-?\d+\s*\)\s*<\s*"
    r"MakeDateTime\([^)]*\)\s*\)\s*\)"
)

# A whole holiday expression is one or more of those windows joined by "Or". We
# match the full run of windows-and-Ors as a single block so we can replace the
# entire old expression in one go. This is what we actually swap out.
#
# Between windows the exported YAML does not use real line breaks. The whole
# expression is stored as one quoted line, and the spots where the UI shows a
# blank line are written as the two-character escape "\n". So the separator we
# see between windows is backslash-n-backslash-n then "Or". The pattern below
# allows those literal "\n" escapes (and any plain spacing) on either side of
# the "Or" so the windows link into one block. "(?:\\\\n)*" matches zero or
# more literal backslash-n escapes; the four backslashes are how we write one
# literal backslash inside a Python regex string.
_SEPARATOR = r"[\s]*(?:\\n)*[\s]*"
_EXPRESSION_PATTERN = re.compile(
    _WINDOW_PATTERN.pattern
    + r"(?:" + _SEPARATOR + r"Or" + _SEPARATOR + _WINDOW_PATTERN.pattern + r")*"
)


def find_existing_expression(flow_yaml):
    """Return the one holiday expression found in the flow YAML, or stop.

    Searches the exported flow text for a block that is only MakeDateTime(...)
    date windows joined by And/Or. That shape is unique to the holiday check, so
    finding exactly one of them tells us where to make the change. We also skip
    any match that mentions DayOfWeek, so the hours-of-operation checks (which
    the separate flow updater owns) can never be picked by mistake.

    Returns the matched expression text so the caller can show it and replace
    it. Stops the script if it finds none or more than one, because changing the
    wrong block (or guessing which of several to change) could break the flow. A
    clear stop is safer than a wrong edit.
    """
    all_matches = _EXPRESSION_PATTERN.findall(flow_yaml)

    # Keep only the holiday-style matches. A real holiday expression never uses
    # DayOfWeek; the hours-of-operation cases always do, so dropping any match
    # that mentions DayOfWeek keeps us off those.
    matches = []
    for match in all_matches:
        if "DayOfWeek" not in match:
            matches.append(match)

    if len(matches) == 0:
        raise SystemExit(
            "Could not find the holiday expression in the exported flow. Nothing "
            "was changed. The flow may not have a MakeDateTime-based holiday "
            "decision, or its format may have changed. Check the flow in the "
            "Architect UI."
        )

    if len(matches) > 1:
        raise SystemExit(
            "Found %d holiday-style expressions in the exported flow, so it is "
            "not clear which one to change. Nothing was changed. Review the flow "
            "in the Architect UI before running again." % len(matches)
        )

    return matches[0]


def replace_expression_in_yaml(flow_yaml, old_expression, new_expression):
    """Return the flow YAML with the old holiday expression swapped for the new.

    Replaces only the one old expression block we found, nowhere else, so the
    rest of the flow text is left exactly as it was. Stops the script if the
    swap does not change the text, which would mean the replace did not take and
    we should not import an unchanged file as if it were updated.
    """
    updated_yaml = flow_yaml.replace(old_expression, new_expression, 1)

    if updated_yaml == flow_yaml:
        raise SystemExit(
            "The holiday expression replacement did not change the flow text, so "
            "nothing was imported. This should not happen after a match was "
            "found; check the flow in the Architect UI."
        )

    return updated_yaml


# --- Talk to the presigned URLs ----------------------------------------------
def download_text(url):
    """Return the text contents of a file at a presigned download URL.

    Architect hands back a one-time URL to download the exported flow. We read
    it with a plain GET and decode it as text (the export is a YAML document).
    Raises on a failed download so a bad export never looks like success.
    """
    with urllib.request.urlopen(url) as response:
        raw_bytes = response.read()
    return raw_bytes.decode('utf-8')


def upload_text(url, headers, text):
    """Upload text to a presigned URL with a PUT request. Returns nothing.

    Architect hands back a one-time URL plus the exact headers we must send to
    upload the edited flow. We send the text as the body of a PUT with those
    headers. Raises on a failed upload so a bad import never looks like success.
    """
    data = text.encode('utf-8')

    # The headers Architect gives us must be sent exactly as provided, or the
    # upload is rejected. We start from those headers and do not add our own.
    request = urllib.request.Request(url, data=data, method='PUT')
    for header_name, header_value in (headers or {}).items():
        request.add_header(header_name, header_value)

    # We only care that the upload succeeded; there is no useful body to read.
    with urllib.request.urlopen(request):
        pass


# --- Wait for Architect jobs to finish ---------------------------------------
def wait_for_export_job(architect_api, job_id):
    """Wait for an export job to finish and return the finished job.

    Checks the export job over and over until it reaches a final state. Returns
    the finished job so the caller can read its download URL. Raises a
    RuntimeError if the job fails, or if it never finishes within our try limit,
    so a bad or stuck export is never treated as good data.
    """
    for _ in range(POLL_MAX_TRIES):
        job = architect_api.get_flows_export_job(job_id)
        status = getattr(job, 'status', None)

        if status == 'Success':
            return job
        if status == 'Failure':
            raise RuntimeError(
                "Architect export job %s failed: %s" % (job_id, getattr(job, 'messages', None))
            )

        # Any other status means the job is still working, so wait and ask
        # again on the next loop.
        time.sleep(POLL_SECONDS)

    raise RuntimeError(
        "Architect export job %s did not finish after %d checks." % (job_id, POLL_MAX_TRIES)
    )


def wait_for_import_job(architect_api, job_id):
    """Wait for an import job to finish and return the finished job.

    Checks the import job over and over until it reaches a final state. Returns
    the finished job. Raises a RuntimeError if the job fails, or if it never
    finishes within our try limit, so a bad or stuck import is never treated as
    a successful update.
    """
    for _ in range(POLL_MAX_TRIES):
        job = architect_api.get_flows_job(job_id)
        status = getattr(job, 'status', None)

        if status == 'Success':
            return job
        if status == 'Failure':
            raise RuntimeError(
                "Architect import job %s failed: %s" % (job_id, getattr(job, 'messages', None))
            )

        time.sleep(POLL_SECONDS)

    raise RuntimeError(
        "Architect import job %s did not finish after %d checks." % (job_id, POLL_MAX_TRIES)
    )


# --- Steps -------------------------------------------------------------------
def export_flow_yaml(architect_api, flow_id):
    """Export one flow and return its definition as YAML text.

    Step 1: Start an export job for this flow, asking for YAML output.
    Step 2: Wait for the job to finish and read the download URL it produces.
    Step 3: Download the YAML text from that URL and return it.

    The download URL is a one-time link that Architect signs for us; we use it
    right away rather than saving it, because it is meant for immediate use.
    """
    export_detail = PureCloudPlatformClientV2.ExportDetails()
    export_detail.flow = PureCloudPlatformClientV2.ArchitectFlowReference()
    export_detail.flow.id = flow_id
    export_detail.export_type = 'Yaml'

    export_request = PureCloudPlatformClientV2.RegisterArchitectExportJob()
    export_request.flows = [export_detail]

    export_response = architect_api.post_flows_export_jobs(export_request)
    finished_job = wait_for_export_job(architect_api, export_response.id)

    download_url = getattr(finished_job, 'download_url', None)
    if not download_url:
        raise RuntimeError(
            "Export job for flow %s finished but gave no download URL." % flow_id
        )

    return download_text(download_url)


def import_flow_yaml(architect_api, flow_yaml):
    """Import edited flow YAML and return the finished import job.

    Step 1: Register an import job, which gives back a one-time upload URL and
            the exact headers we must send with the upload.
    Step 2: Upload the edited YAML to that URL with those headers.
    Step 3: Wait for the import job to finish and return it.

    The uploaded YAML already carries the flow's own ID, so the import updates
    that same flow rather than creating a new one. Importing does not publish;
    publishing is a separate step the caller does next.
    """
    import_response = architect_api.post_flows_jobs()

    upload_url = getattr(import_response, 'presigned_url', None)
    upload_headers = getattr(import_response, 'headers', None)
    if not upload_url:
        raise RuntimeError("Import job registration gave no upload URL.")

    upload_text(upload_url, upload_headers, flow_yaml)
    return wait_for_import_job(architect_api, import_response.id)


def update_one_flow(architect_api, flow_id, new_expression):
    """Update the holiday expression in one flow, then publish it.

    Step 1: Check out the flow so we are allowed to change it.
    Step 2: Export the flow to YAML and find its one holiday expression.
    Step 3: Show the old and new expression so you can see the change.
    Step 4: If DRY_RUN is True, stop here and change nothing.
    Step 5: Swap the old expression for the new one, import the edited YAML, and
            publish the flow so the change goes live.

    Catches its own errors and returns True on success or False on failure, so
    one bad flow does not stop the script from trying the rest of the list.
    """
    print("\n--- Flow %s ---" % flow_id)

    try:
        # Check out the flow first. This is the API version of opening the flow
        # for editing in the UI, and it is what lets the later import land on
        # this flow. We do this even in a dry run so the preview matches what a
        # real run would see.
        architect_api.post_flows_actions_checkout(flow_id)

        flow_yaml = export_flow_yaml(architect_api, flow_id)
        old_expression = find_existing_expression(flow_yaml)

        print("Old expression found in flow:")
        print(old_expression)
        print("\nNew expression that would be written:")
        print(new_expression)

        if DRY_RUN:
            print("\n[DRY-RUN] Not importing or publishing. Set DRY_RUN to False "
                  "to apply this change.")
            return True

        updated_yaml = replace_expression_in_yaml(flow_yaml, old_expression, new_expression)

        import_flow_yaml(architect_api, updated_yaml)
        print("Imported the edited flow.")

        # Publishing is what makes the change live for callers. Importing alone
        # only saves a new draft, so we publish right after a successful import.
        architect_api.post_flows_actions_publish(flow_id)
        print("Published the flow. The change is now live.")
        return True

    except (ApiException, RuntimeError) as e:
        # Report this flow's failure and keep going. We return False so the
        # summary at the end can tell you which flows did not update.
        print("Failed to update flow %s: %s" % (flow_id, e))
        print("This flow was left as-is. Check it in the Architect UI.")
        return False


# --- Main --------------------------------------------------------------------
def main(flow_ids, holidays):
    """Update the holiday decision expression across a list of flows.

    Step 1: Stop early if there are no flows to update, so we never start a run
            that has nothing to do.
    Step 2: Build the new holiday expression once from the holiday list, since
            every flow gets the same expression.
    Step 3: Sign in to Genesys Cloud.
    Step 4: Update each flow in turn, keeping count of which succeeded and which
            failed, so one bad flow does not stop the others.
    Step 5: Print a short summary so you can see the result at a glance.
    """
    # Keep only the flow IDs that are actually filled in, so a leftover blank or
    # the placeholder line does not cause a pointless call that would fail.
    real_flow_ids = []
    for flow_id in flow_ids:
        if flow_id and flow_id != 'REPLACE-WITH-FLOW-ID':
            real_flow_ids.append(flow_id)

    if not real_flow_ids:
        raise SystemExit(
            "No flow IDs to update. Set one or more real flow IDs in FLOW_IDS "
            "near the top of the script before running."
        )

    new_expression = build_holiday_expression(holidays)

    if DRY_RUN:
        print("DRY_RUN is True, so no flow will be changed. You will see the old "
              "and new expression for each flow, then the script will stop "
              "before importing or publishing.")

    architect_api = build_apis()

    succeeded = 0
    failed = 0
    for flow_id in real_flow_ids:
        if update_one_flow(architect_api, flow_id, new_expression):
            succeeded += 1
        else:
            failed += 1

    print("\nDone. %d flow(s) succeeded, %d flow(s) failed, out of %d."
          % (succeeded, failed, len(real_flow_ids)))


if __name__ == '__main__':
    main(FLOW_IDS, HOLIDAYS)
