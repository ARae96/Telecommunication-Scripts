# =============================================================================
# Genesys Cloud - Flip The Hours-Of-Operation Time Offset In Service Ops Flows
# =============================================================================
# Some of our call flows decide "are we open right now?" by comparing the
# current time to our open and close hours. To do that comparison in local
# time, the flow first shifts the current Coordinated Universal Time (UTC) by a
# fixed number of hours. That shift lives inside the flow as
# AddHours(GetCurrentDateTimeUtc(), N), where N is the offset. Twice a year,
# when daylight saving time starts or ends, that offset has to change (for us,
# between -6 and -7). Today we change it by hand in the Genesys Cloud Architect
# user interface (UI), one flow at a time. This script does that same change
# for you, across a list of flows, using the Architect API.
#
# What the script changes: the open/close "hours of operation" checks only.
# Those checks live in the Switch cases that use DayOfWeek(...) to tell weekdays
# from weekends. Every AddHours(GetCurrentDateTimeUtc(), OLD_UTC_OFFSET) inside
# those cases is rewritten to AddHours(GetCurrentDateTimeUtc(), NEW_UTC_OFFSET).
#
# What the script leaves alone: the holiday decision at the top of the flow.
# That holiday check also uses AddHours(GetCurrentDateTimeUtc(), ...), but it is
# maintained separately. This script never touches it. The hour numbers inside
# MakeDateTime(...) (like the "6" in 6 AM) are also left alone, because this
# script only rewrites the offset argument to AddHours, nowhere else.
#
# What the script does for each flow you list:
#   Step 1: Check out the flow so we can edit it (same as opening it in the UI).
#   Step 2: Export the flow to YAML (the flow's full definition as text).
#   Step 3: Find the hours-of-operation case expressions (the ones that use
#           DayOfWeek) and flip the offset inside them from OLD to NEW.
#   Step 4: Import the edited YAML back onto the same flow.
#   Step 5: Publish the flow so the change goes live.
#
# How the script finds the right expressions to change: it does NOT rely on the
# cases being in a fixed spot. It looks for expressions that contain
# DayOfWeek(AddHours(GetCurrentDateTimeUtc(), ...)). That shape belongs only to
# the hours-of-operation checks, so it is a safe thing to match on, and it never
# matches the holiday block.
#
# Reversing it later: the offset flips back the other way every six months. To
# reverse a change, swap the two values in OLD_UTC_OFFSET and NEW_UTC_OFFSET and
# run the script again.
#
# Safety: this script changes live Genesys Cloud flows, so it always reads first
# and shows you a summary before it changes anything. It checks out and exports
# each flow (both read-only), counts how many offsets it would change in each,
# and shows you that plan. Then it asks you to confirm in a pop-up dialog (with
# a typed fallback if the dialog cannot be shown). No flow is imported or
# published unless you confirm.
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

from confirm_prompt import ask_to_confirm


# --- Configuration -----------------------------------------------------------
# The flows to update. Add as many flow IDs as you need, one per line. The same
# offset flip is applied to every flow in this list.
FLOW_IDS = [
    'REPLACE-WITH-FLOW-ID',
]

# The time offset to change, in hours added to UTC. The flow holds this number
# inside AddHours(GetCurrentDateTimeUtc(), N). OLD_UTC_OFFSET is the value in
# the flow right now; NEW_UTC_OFFSET is what you want it to become. When
# daylight saving time flips, swap these two values and run the script again.
#
# For us the offset is -6 during daylight saving time and -7 the rest of the
# year, so a typical run sets one of these to -6 and the other to -7.
OLD_UTC_OFFSET = -6
NEW_UTC_OFFSET = -7

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


# --- Find and flip the offset in the exported YAML ---------------------------
# The hours-of-operation checks are the only expressions that ask what day of
# the week it is, using DayOfWeek(AddHours(GetCurrentDateTimeUtc(), N)). We use
# that shape to find those lines. The holiday block never uses DayOfWeek, so
# this match leaves the holiday block alone. We allow any offset inside so the
# same pattern works no matter which way the offset is set today. "re.escape"
# below just keeps punctuation literal, so the match is for the exact text.
_DAYOFWEEK_MARKER = re.compile(
    r"DayOfWeek\(\s*AddHours\(\s*GetCurrentDateTimeUtc\(\)\s*,\s*-?\d+\s*\)\s*\)"
)


def count_old_offset(text):
    """Return how many times the old offset appears in the given text.

    Counts the exact AddHours(GetCurrentDateTimeUtc(), OLD_UTC_OFFSET) text. We
    use this to show a before-count in the preview and to confirm the change
    landed. It does not change anything.
    """
    needle = "AddHours(GetCurrentDateTimeUtc(), %d)" % OLD_UTC_OFFSET
    return text.count(needle)


def flip_offset_in_expression(expression_text):
    """Return the case expression with every old offset flipped to the new one.

    Replaces every AddHours(GetCurrentDateTimeUtc(), OLD_UTC_OFFSET) with
    AddHours(GetCurrentDateTimeUtc(), NEW_UTC_OFFSET) inside this one case
    expression. Nothing else in the text is touched, so the hour numbers inside
    MakeDateTime(...) and any other logic stay exactly as they were.
    """
    old_text = "AddHours(GetCurrentDateTimeUtc(), %d)" % OLD_UTC_OFFSET
    new_text = "AddHours(GetCurrentDateTimeUtc(), %d)" % NEW_UTC_OFFSET
    return expression_text.replace(old_text, new_text)


def find_hours_of_operation_expressions(flow_yaml):
    """Return the hours-of-operation expression lines found in the flow YAML.

    The flow exports each expression as a single line, so we scan the YAML line
    by line and keep every line that contains the DayOfWeek(AddHours(...)) shape
    unique to the hours-of-operation cases. Returns the list of whole matching
    lines so the caller can rewrite them.

    Stops the script if it finds no such lines, because that means the flow does
    not look the way we expect and changing it could break it. A clear stop is
    safer than a wrong edit.
    """
    matching_lines = []
    for line in flow_yaml.splitlines():
        if _DAYOFWEEK_MARKER.search(line):
            matching_lines.append(line)

    if not matching_lines:
        raise SystemExit(
            "Could not find any hours-of-operation expressions (the ones that "
            "use DayOfWeek) in the exported flow. Nothing was changed. The flow "
            "may not have these checks, or its format may have changed. Check "
            "the flow in the Architect UI."
        )

    return matching_lines


def flip_offset_in_yaml(flow_yaml):
    """Return the flow YAML with the offset flipped in the hours checks only.

    Step 1: Find the hours-of-operation expression lines (the DayOfWeek ones).
    Step 2: For each of those whole lines, flip every old offset to the new one
            and replace that exact line in the YAML.

    Returns a pair: the updated YAML text and the number of offsets changed. We
    rewrite whole matched lines, so no AddHours offset outside these expressions
    (such as the holiday block at the top) is ever touched.
    """
    expression_lines = find_hours_of_operation_expressions(flow_yaml)

    updated_yaml = flow_yaml
    total_changed = 0
    for old_line in expression_lines:
        changed_in_line = count_old_offset(old_line)
        new_line = flip_offset_in_expression(old_line)
        # Replace this exact line text wherever it appears. The line is a long,
        # unique expression, so this only touches the case we matched.
        updated_yaml = updated_yaml.replace(old_line, new_line)
        total_changed += changed_in_line

    return updated_yaml, total_changed


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
    RuntimeError if the job fails, or if it never finishes within our try
    limit, so a bad or stuck export is never treated as good data.
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


def get_flow_name(architect_api, flow_id):
    """Return a flow's name, or a fallback label if we cannot read it.

    We show this name in the preview and the confirm dialog so you can check you
    picked the right flows. If the read fails we return a short "(name
    unavailable)" label instead of stopping, because a missing name should not
    block the preview.
    """
    try:
        flow = architect_api.get_flow(flow_id)
    except ApiException as e:
        print("Could not read flow name for %s: %s" % (flow_id, e))
        return "(name unavailable)"
    return getattr(flow, 'name', None) or "(name unavailable)"


def prepare_flow_update(architect_api, flow_id):
    """Read one flow and work out the edit, without changing the live flow.

    Step 1: Read the flow's name so the preview can show it.
    Step 2: Check out the flow. This is the API version of opening the flow for
            editing in the UI, and it is what lets a later import land on this
            flow. Checkout does not change the live flow, so it is safe to do
            before you confirm.
    Step 3: Export the flow to YAML and flip the offset in the hours checks.

    Returns a dictionary describing the planned edit:
      {"flow_id", "flow_name", "changed_count", "updated_yaml"}
    changed_count is how many offsets would change; it is 0 when the flow is
    already on the new offset. Catches its own errors and returns None on
    failure, so one bad flow does not stop the script from reading the rest.
    """
    print("\n--- Flow %s ---" % flow_id)

    try:
        flow_name = get_flow_name(architect_api, flow_id)
        architect_api.post_flows_actions_checkout(flow_id)

        flow_yaml = export_flow_yaml(architect_api, flow_id)
        updated_yaml, changed_count = flip_offset_in_yaml(flow_yaml)

        print("Flow '%s': would change the offset from %d to %d in %d place(s)."
              % (flow_name, OLD_UTC_OFFSET, NEW_UTC_OFFSET, changed_count))

        return {
            "flow_id": flow_id,
            "flow_name": flow_name,
            "changed_count": changed_count,
            "updated_yaml": updated_yaml,
        }

    except (ApiException, RuntimeError) as e:
        # Report this flow's failure and keep going. Returning None leaves it
        # out of the plan so it is not shown in the confirm or published.
        print("Could not prepare flow %s: %s" % (flow_id, e))
        print("This flow was left as-is. Check it in the Architect UI.")
        return None


def import_and_publish_flow(architect_api, plan):
    """Import the edited YAML for one flow and publish it. Call this after confirm.

    plan is one of the dictionaries that prepare_flow_update returns. This
    imports the edited YAML onto the same flow, then publishes it so the change
    goes live. Catches its own errors and returns True on success or False on
    failure, so one bad flow does not stop the rest.
    """
    flow_id = plan["flow_id"]
    flow_name = plan["flow_name"]
    print("\n--- Flow '%s' (%s) ---" % (flow_name, flow_id))

    try:
        import_flow_yaml(architect_api, plan["updated_yaml"])
        print("Imported the edited flow.")

        # Publishing is what makes the change live for callers. Importing alone
        # only saves a new draft, so we publish right after a successful import.
        architect_api.post_flows_actions_publish(flow_id)
        print("Published the flow. The change is now live.")
        return True

    except (ApiException, RuntimeError) as e:
        print("Failed to update flow %s: %s" % (flow_id, e))
        print("This flow was left as-is. Check it in the Architect UI.")
        return False


def format_flows_for_confirm(plans_with_changes):
    """Build the confirm message that lists the flows and their offset counts.

    plans_with_changes is the list of flow plans that would actually change (the
    ones with a changed_count above zero). Names the offset direction and each
    flow with how many offsets it would gain. Returns one block of text with
    real new lines, shown in the confirm dialog and the typed fallback.
    """
    lines = []

    lines.append(
        "This will change the hours-of-operation time offset in %d flow(s) and "
        "publish them live." % len(plans_with_changes)
    )

    lines.append("")
    lines.append("Offset change: %d  ->  %d" % (OLD_UTC_OFFSET, NEW_UTC_OFFSET))

    lines.append("")
    lines.append("Flows to update:")
    for plan in plans_with_changes:
        lines.append("%s (%d offset(s))" % (plan["flow_name"], plan["changed_count"]))

    lines.append("")
    lines.append("Flows with no matching offsets are skipped and not published.")

    lines.append("")
    lines.append(
        "Note: Apply re-imports and publishes each flow above, so the change "
        "goes live in Genesys Cloud right away."
    )

    return '\n'.join(lines)


# --- Main --------------------------------------------------------------------
def main(flow_ids):
    """Flip the hours-of-operation time offset across a list of flows.

    Step 1: Stop early if the old and new offset are the same, so we never run a
            flip that would change nothing.
    Step 2: Stop early if there are no flows to update.
    Step 3: Sign in to Genesys Cloud.
    Step 4: Read and prepare every flow (check out, export, flip). This is all
            read-only; the live flows are not changed yet.
    Step 5: Show the plan and ask you to confirm. If you do not confirm, stop
            before importing or publishing anything.
    Step 6: Import and publish each flow that would change.
    Step 7: Print a short summary so you can see the result at a glance.
    """
    if OLD_UTC_OFFSET == NEW_UTC_OFFSET:
        raise SystemExit(
            "OLD_UTC_OFFSET and NEW_UTC_OFFSET are both %d, so there is nothing "
            "to change. Set them to the two different offsets you want to flip "
            "between (for us, -6 and -7)." % OLD_UTC_OFFSET
        )

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

    architect_api = build_apis()

    # Step 4: prepare every flow (read-only). A flow that fails to prepare
    # returns None and is left out of the plan.
    plans = []
    for flow_id in real_flow_ids:
        plan = prepare_flow_update(architect_api, flow_id)
        if plan is not None:
            plans.append(plan)

    # Keep only the flows that would actually change. A flow with a changed
    # count of zero is already on the new offset, so we skip it and never
    # re-import or publish it for no reason.
    plans_with_changes = []
    for plan in plans:
        if plan["changed_count"] > 0:
            plans_with_changes.append(plan)

    if not plans_with_changes:
        print("\nNo flow needs changing. Every flow is already on the new offset "
              "or had no hours-of-operation checks to change.")
        return

    # Step 5: show the plan and ask you to confirm. Everything above was
    # read-only, so stopping here leaves every flow exactly as it was.
    question = format_flows_for_confirm(plans_with_changes)
    if not ask_to_confirm(question, "Update Service Ops Flow Offsets"):
        raise SystemExit("Stopped at your request. No flow was imported or published.")

    # Step 6: import and publish each flow that would change.
    succeeded = 0
    failed = 0
    for plan in plans_with_changes:
        if import_and_publish_flow(architect_api, plan):
            succeeded += 1
        else:
            failed += 1

    print("\nDone. %d flow(s) succeeded, %d flow(s) failed, out of %d."
          % (succeeded, failed, len(plans_with_changes)))


if __name__ == '__main__':
    main(FLOW_IDS)
