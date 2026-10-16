# =============================================================================
# Genesys Cloud - Architect Flow Tree Review List (OFFLINE / LOCAL)
# =============================================================================
# Starts from one or more Architect flows and walks each one's dependency tree,
# so you get the whole family of flows those starting flows lean on, not just
# the starting flows themselves. You enter the starting flow IDs near the top of
# the file. The script signs in to Genesys Cloud, reads each flow, and follows
# its dependencies.
#
# The script's job is to build a review list, not to download the flows. It
# finds every flow and operating schedule in the trees and writes them to one
# Excel file, with no duplicates even when two trees share an item. You then
# open that list and export the flows you need by hand from the Architect UI. We
# go this route because downloading a flow through the API needs a user sign-in
# that is not available here (see the sign-in note below).
#
# What the walk follows and what it stops at:
#   - It follows flows. A flow can call another flow, which can call more
#     flows, so the script keeps digging until it reaches the ends of the tree.
#   - It records operating schedules it runs into, but it does not dig into
#     them. A schedule does not call other flows, so it is an end point.
#   - It ignores every other kind of dependency (such as prompts and
#     recordings), because you only asked for flows and operating schedules.
#
# What the script writes (both land in the folder this file lives in, and both
# share one timestamp so you can tell which two came from the same run):
#   1. An Excel file listing every flow and operating schedule found, so you can
#      review them and open them by hand. Each row shows the item type, name,
#      ID, and a web link.
#        Architect_Export_Review_<timestamp>.xlsx
#   2. A JSON file listing the flows only (not schedules), in the shape the Dev
#      Center's export call wants. You paste its contents into the Dev Center to
#      get the YAML for every flow at once.
#        Architect_Export_Request_<timestamp>.json
#
# This script only reads from Genesys, so there is no DRY_RUN switch here.
#
# Why this builds a list instead of downloading the flows:
#   Downloading a flow's YAML through the API uses an "export job". That job
#   builds a download file that belongs to a real person, so Genesys only runs
#   it when the sign-in is tied to a user. The sign-in this script uses (a client
#   id and secret, the "client credentials" sign-in the other scripts in this
#   workspace use) has no user behind it, so the export job fails. Setting up a
#   user sign-in needs an OAuth app that is not available to us, so instead the
#   script lists the flows and you export the handful you need from the Architect
#   UI, where you are already signed in as yourself.
#
# How the flow-vs-schedule sorting works:
#   Genesys labels each dependency with a "type" string in all capitals, such
#   as "INBOUNDCALLFLOW" or "SCHEDULE". The Architect flow families and the
#   schedule types are a fixed, known list, so the script holds that list near
#   the top (FLOW_OBJECT_TYPES and SCHEDULE_OBJECT_TYPES). An item whose type is
#   in the flow list is a flow we follow and list; an item whose type is in the
#   schedule list is an operating schedule we list but do not dig into; anything
#   else is ignored.
#
# How the dependency lookup works (so nothing is guessed):
#   To read what a flow consumes, Genesys needs three things: the flow ID, the
#   flow's PUBLISHED version number, and the flow's type in all capitals (its
#   "object type"). So for each flow the script first reads the flow to get its
#   name, its type, and its published version, then asks for the resources that
#   published version consumes. A flow with no published version is recorded but
#   skipped for the dig, because without a published version there is nothing to
#   read dependencies from.
#
# Run locally with:
#   pip install -r requirements.txt
# and a populated .env (GENESYS_CLOUD_CLIENT_ID / GENESYS_CLOUD_CLIENT_SECRET).
# =============================================================================


# --- Imports -----------------------------------------------------------------
import os
import json
from datetime import datetime

import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from dotenv import load_dotenv
from openpyxl import Workbook


# --- Configuration -----------------------------------------------------------
# Enter one or more starting Architect flow IDs by hand before running. The
# script walks the dependency tree of each one and gathers every flow and
# operating schedule across all of them into a single review file.
#
# You can list as many IDs as you like, one per line, each in quotes. If two
# starting flows share a sub-flow or schedule, it is listed only once, so there
# are no duplicates in the review file.
STARTING_FLOW_IDS = [
    '52a24409-5a60-435d-9430-959e5c8380b6',
    'a75df757-d52f-4c45-add0-5cb510867dce',
    'e0f7ae70-f673-4a94-9e63-dcd5433c4073',
    'dbfc1018-7b1f-4984-b64d-d28387205fb2',
]

# How many items to ask for per page when a Genesys call returns a list. 100 is
# the common page size the other scripts in this workspace use.
PAGE_SIZE = 100

# The Architect flow families, written the way the dependency system labels
# them: all capitals. These are the types we both export and dig into. This is
# the full set of flow types Genesys tracks, so the walk follows every kind of
# flow a flow can call.
FLOW_OBJECT_TYPES = {
    'BOTFLOW',
    'COMMONMODULEFLOW',
    'DIGITALBOTFLOW',
    'INBOUNDCALLFLOW',
    'INBOUNDCHATFLOW',
    'INBOUNDEMAILFLOW',
    'INBOUNDSHORTMESSAGEFLOW',
    'INQUEUECALLFLOW',
    'INQUEUEEMAILFLOW',
    'INQUEUESHORTMESSAGEFLOW',
    'OUTBOUNDCALLFLOW',
    'SECURECALLFLOW',
    'SURVEYINVITEFLOW',
    'VOICESURVEYFLOW',
    'VOICEMAILFLOW',
    'WORKITEMFLOW',
    'WORKFLOW',
}

# The operating schedule types, again as the dependency system labels them. We
# record these for the review file but do not dig into them, because a schedule
# does not call other flows. A schedule group is a bundle of schedules, so we
# record it the same way.
SCHEDULE_OBJECT_TYPES = {
    'SCHEDULE',
    'SCHEDULEGROUP',
}

# The web address pieces used to build the "Link" column in the review file. A
# flow link looks like:
#   https://apps.mypurecloud.com/architect/#/<segment>/flows/<flow id>/latest
# and a schedule link looks like:
#   https://apps.mypurecloud.com/directory/#/admin/routing/scheduling/schedules/<schedule id>
# The <segment> in a flow link changes with the flow's kind. Below is the full
# list of flow kinds that can show up in a dependency list, mapped to the
# segment Architect uses in its web address. Two of these segments are confirmed
# from real links ("inboundcall" and "commonmodule"); the rest follow the same
# naming pattern. If a link for one of the unconfirmed kinds does not open,
# check the address bar in Architect for that flow kind and fix its segment
# here. If a flow kind is somehow missing from this map, build_flow_link falls
# back to a best guess (the object type with the trailing "FLOW" dropped and
# lower-cased) so the review file still shows a link to try.
FLOW_URL_BASE = 'https://apps.mypurecloud.com/architect/#'
SCHEDULE_URL_BASE = 'https://apps.mypurecloud.com/directory/#/admin/routing/scheduling/schedules'
FLOW_URL_SEGMENTS = {
    'INBOUNDCALLFLOW': 'inboundcall',           # confirmed from a real link
    'COMMONMODULEFLOW': 'commonmodule',          # confirmed from a real link
    'INBOUNDSHORTMESSAGEFLOW': 'inboundshortmessage',
    'INBOUNDEMAILFLOW': 'inboundemail',
    'INBOUNDCHATFLOW': 'inboundchat',
    'OUTBOUNDCALLFLOW': 'outboundcall',
    'BOTFLOW': 'bot',
    'DIGITALBOTFLOW': 'digitalbot',
    'INQUEUECALLFLOW': 'inqueuecall',
    'INQUEUEEMAILFLOW': 'inqueueemail',
    'INQUEUESHORTMESSAGEFLOW': 'inqueueshortmessage',
    'SECURECALLFLOW': 'securecall',
    'VOICEMAILFLOW': 'voicemail',
    'WORKFLOW': 'workflow',
    'WORKITEMFLOW': 'workitem',
}

# The folder to write the Excel review file into. We use the folder this script
# lives in, which is the Genesys Architect folder.
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


# --- Authentication ----------------------------------------------------------
def build_apis():
    """Sign in to Genesys Cloud and return the one API client this script needs.

    Reads GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET from the .env
    file at the workspace root (one folder up from this script). Stops the
    script with a helpful message if either value is missing. Returns an
    ArchitectApi client, which covers reading flows, dependency tracking, and
    operating schedules.
    """
    # The .env sits at the workspace root, one level above this script's folder.
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
    return PureCloudPlatformClientV2.ArchitectApi(apiclient)


# --- Helpers -----------------------------------------------------------------
def flow_type_to_object_type(flow_type):
    """Return a flow's all-capitals object type, the form the dependency API wants.

    Genesys reports a flow's own type in a short form such as "INBOUNDCALL" or
    "WORKFLOW". The dependency system uses a longer all-capitals form such as
    "INBOUNDCALLFLOW". For every flow family except the plain workflow, the
    dependency form is just the short form with "FLOW" added on the end. The
    workflow family is already "WORKFLOW", so we leave it alone.

    Returns the object type string, or None if flow_type is missing. Returns a
    value even for a type not in our known list, so the caller can still try the
    lookup; the caller checks the result against FLOW_OBJECT_TYPES before
    trusting it.
    """
    if not flow_type:
        return None
    upper_type = flow_type.upper()
    if upper_type == 'WORKFLOW':
        return 'WORKFLOW'
    if upper_type.endswith('FLOW'):
        return upper_type
    return upper_type + 'FLOW'


def flow_url_segment(object_type):
    """Return the Architect web-address segment for a flow object type.

    The segment is the piece of the flow link that names the flow's kind, such
    as "inboundcall" in an inbound call flow link. We first look the object type
    up in FLOW_URL_SEGMENTS, which holds the segments we have confirmed from a
    real Genesys link. If it is not there, we fall back to a best guess: the
    object type with the trailing "FLOW" dropped and lower-cased.

    Returns the segment string, or None if object_type is missing.
    """
    if not object_type:
        return None
    if object_type in FLOW_URL_SEGMENTS:
        return FLOW_URL_SEGMENTS[object_type]
    # Best-guess fallback. "INBOUNDCALLFLOW" -> "inboundcall". "WORKFLOW" has no
    # trailing kind to drop, so it just lower-cases to "workflow".
    if object_type.endswith('FLOW') and object_type != 'WORKFLOW':
        return object_type[:-len('FLOW')].lower()
    return object_type.lower()


def build_flow_link(flow_id, object_type):
    """Return the Architect web link for a flow, or an empty string if we cannot.

    Builds a link of the form
    "https://apps.mypurecloud.com/architect/#/<segment>/flows/<flow id>/latest".
    The <segment> comes from the flow's object type. Returns an empty string if
    the flow ID or the segment is missing, so the review file simply shows no
    link rather than a broken one.
    """
    segment = flow_url_segment(object_type)
    if not flow_id or not segment:
        return ''
    return '%s/%s/flows/%s/latest' % (FLOW_URL_BASE, segment, flow_id)


def build_schedule_link(schedule_id):
    """Return the Architect web link for an operating schedule, or an empty string.

    Builds a link of the form
    "https://apps.mypurecloud.com/directory/#/admin/routing/scheduling/schedules/<schedule id>".
    Returns an empty string if the schedule ID is missing, so the review file
    shows no link rather than a broken one.
    """
    if not schedule_id:
        return ''
    return '%s/%s' % (SCHEDULE_URL_BASE, schedule_id)


def safe_export_file_name(flow_name, flow_id):
    """Return a safe "fileName" value for the export request, like Yaml_Export_<name>.

    The export request will not accept a file name with anything but letters,
    numbers, underscores, and hyphens, so we replace every other character in
    the flow name with an underscore. We build "Yaml_Export_<cleaned name>".
    If the flow has no name, we fall back to the flow ID so the file name is
    still unique and valid.
    """
    base = flow_name if flow_name else flow_id

    cleaned_characters = []
    for character in base:
        if character.isalnum() or character in ('-', '_'):
            cleaned_characters.append(character)
        else:
            cleaned_characters.append('_')
    cleaned = ''.join(cleaned_characters)
    return 'Yaml_Export_%s' % cleaned


def get_flow_details(architect_api, flow_id):
    """Return a flow's name, both type forms, and published version number.

    Reads one flow from Genesys so we know four things about it:
      - its name, for the review file and the export file;
      - its short type, the all-capitals form such as "INBOUNDCALL" that the
        export request wants;
      - its object type, the longer all-capitals form such as "INBOUNDCALLFLOW"
        that the dependency lookup needs;
      - its published version number, so the dependency lookup reads the
        published version you asked for, not a draft, and so the export file
        asks for that same published version.

    Returns a tuple of (name, short_type, object_type, published_version). Any
    of the four is None if it is missing or the read fails. A published_version
    of None means the flow has never been published, so the caller records it
    but does not try to read its dependencies.

    We keep two type forms on purpose, because Genesys wants different forms in
    two places: the short form in the export request and the longer form in the
    dependency lookup.
    """
    try:
        flow = architect_api.get_flow(flow_id)
    except ApiException as e:
        print("Could not read flow %s: %s" % (flow_id, e))
        return (None, None, None, None)

    name = getattr(flow, 'name', None)

    # The flow's own type is the short form the export request wants. We
    # upper-case it so it matches the form the export API expects.
    raw_type = getattr(flow, 'type', None)
    short_type = raw_type.upper() if raw_type else None
    object_type = flow_type_to_object_type(raw_type)

    published_version = None
    published = getattr(flow, 'published_version', None)
    if published is not None:
        published_version = getattr(published, 'id', None)

    return (name, short_type, object_type, published_version)


def get_consumed_dependencies(architect_api, flow_id, object_type, published_version):
    """Return the list of resources a flow's published version consumes.

    Reads what one flow leans on, using the dedicated consumed-resources call.
    That call needs the flow ID, the flow's published version number, and the
    flow's all-capitals object type. We read it a page at a time and gather
    every page. Returns a list of Dependency objects, each with an id, a name,
    and an all-capitals type.

    Returns an empty list if the flow has no published version or the read
    fails, so one bad flow does not stop the whole walk. The caller sorts these
    into flows to follow and schedules to record.
    """
    if not object_type or not published_version:
        return []

    dependencies = []
    try:
        page_number = 1
        while True:
            response = architect_api.get_architect_dependencytracking_consumedresources(
                flow_id,
                published_version,
                object_type,
                page_number=page_number,
                page_size=PAGE_SIZE,
            )
            for dependency in getattr(response, 'entities', None) or []:
                dependencies.append(dependency)
            # Stop once we have read the last page. page_count is the total
            # number of pages Genesys has for this flow's consumed resources.
            if page_number >= (getattr(response, 'page_count', 0) or 0):
                break
            page_number += 1
    except ApiException as e:
        print("Could not read dependencies for flow %s: %s" % (flow_id, e))
    return dependencies


# --- Steps -------------------------------------------------------------------
def walk_flow_tree(architect_api, starting_flow_ids):
    """Walk the dependency tree from each starting flow and sort what it finds.

    Takes a list of starting flow IDs and walks all of them in one pass, so the
    result is the combined set of flows and schedules across every tree. A flow
    or schedule that shows up in more than one tree is listed only once.

    Step 1: Start a to-do list holding the starting flow IDs.
    Step 2: Take one flow off the list, read its name, object type, and
            published version, and remember it as a flow we found. Reading the
            flow also proves it exists.
    Step 3: Read what that flow's published version consumes. For each consumed
            item:
              - If its type is a flow type and we have not seen it yet, add it to
                the to-do list so we dig into it later.
              - If its type is a schedule type, remember it as a schedule we
                found. We do not dig into schedules.
              - Anything else (prompts, recordings, and so on) is ignored.
    Step 4: Repeat until the to-do list is empty, which means we have reached
            the ends of every branch.

    We keep a "seen" set of flow IDs so a flow that shows up more than once, or a
    loop where two flows call each other, is handled only once and never spins
    forever.

    Returns a tuple of two lists:
      - found_flows:     list of
                         (flow_id, flow_name, object_type, short_type, published_version)
                         tuples. The object type lets the review file build the
                         right web link for each flow kind; the short type and
                         published version feed the export request file.
      - found_schedules: list of (schedule_id, schedule_name) tuples
    Both lists keep the order in which items were first found.
    """
    # Copy the starting list so we never change the caller's list as we work.
    flows_to_visit = list(starting_flow_ids)
    seen_flow_ids = set()
    seen_schedule_ids = set()
    found_flows = []
    found_schedules = []

    while flows_to_visit:
        flow_id = flows_to_visit.pop(0)

        # Skip a flow we have already handled. This is what stops loops in the
        # tree from making us go around forever.
        if flow_id in seen_flow_ids:
            continue
        seen_flow_ids.add(flow_id)

        flow_name, short_type, object_type, published_version = get_flow_details(architect_api, flow_id)
        if flow_name is None and short_type is None and object_type is None and published_version is None:
            # The read failed, so we cannot label this flow. We skip it and keep
            # going so one bad flow does not end the whole run.
            print("Skipping flow %s because it could not be read." % flow_id)
            continue

        found_flows.append((flow_id, flow_name, object_type, short_type, published_version))
        print("Found flow: %s (%s)" % (flow_name or "unnamed", flow_id))

        if not published_version:
            # With no published version there is nothing published to read
            # dependencies from, so we record the flow but do not dig into it.
            print(
                "   Flow %s has no published version, so its dependencies were "
                "not followed." % flow_id
            )
            continue

        for dependency in get_consumed_dependencies(architect_api, flow_id, object_type, published_version):
            dependency_id = getattr(dependency, 'id', None)
            dependency_name = getattr(dependency, 'name', None)
            dependency_type = getattr(dependency, 'type', None)
            if not dependency_id or not dependency_type:
                continue

            if dependency_type in SCHEDULE_OBJECT_TYPES:
                # Record the schedule once. We do not add it to the to-do list,
                # because a schedule does not call other flows.
                if dependency_id not in seen_schedule_ids:
                    seen_schedule_ids.add(dependency_id)
                    found_schedules.append((dependency_id, dependency_name))
                    print("Found operating schedule: %s (%s)" % (dependency_name or "unnamed", dependency_id))
            elif dependency_type in FLOW_OBJECT_TYPES:
                # A flow we have not handled yet goes on the to-do list so we
                # dig into its own dependencies later.
                if dependency_id not in seen_flow_ids:
                    flows_to_visit.append(dependency_id)
            # Every other dependency type is ignored on purpose.

    return (found_flows, found_schedules)


def write_review_excel(found_flows, found_schedules, timestamp):
    """Write an Excel file listing every flow and operating schedule we found.

    Builds a single sheet with a header row and one row per item. Each row shows
    the item type ("Flow" or "Operating Schedule"), the item name, the item ID,
    and a Link that opens the item in the Genesys web app. The ID and link are
    enough for you to find and open the item by hand in Genesys.

    The timestamp is passed in so this file and the export request file from the
    same run share one stamp. Writes one file named
    Architect_Export_Review_<timestamp>.xlsx in the output folder and returns
    the full path it wrote. The flows are listed first, then the schedules.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Architect Review'

    sheet.append(['Type', 'Name', 'ID', 'Link'])

    for flow_id, flow_name, object_type, _short_type, _published_version in found_flows:
        sheet.append(['Flow', flow_name or '', flow_id, build_flow_link(flow_id, object_type)])

    for schedule_id, schedule_name in found_schedules:
        sheet.append(['Operating Schedule', schedule_name or '', schedule_id, build_schedule_link(schedule_id)])

    file_path = os.path.join(OUTPUT_DIR, 'Architect_Export_Review_%s.xlsx' % timestamp)
    workbook.save(file_path)
    return file_path


def write_export_request_json(found_flows, timestamp):
    """Write the JSON file you paste into the Dev Center to export the flows' YAML.

    Builds the request body the Dev Center's "register export job" call expects:
    a "flows" list with one entry per flow. Each entry names the flow by id,
    name, short type (such as "INBOUNDCALL"), and published version, asks for a
    file name of "Yaml_Export_<flow name>", and sets the export type to "Yaml".

    This file lists flows only, not operating schedules, because a schedule is
    not a flow and has no YAML export.

    Only flows that have a published version are included. A flow with no
    published version has nothing published to export, so we leave it out and
    print a note naming it, rather than write an entry the export would reject.

    Writes one file named Architect_Export_Request_<timestamp>.json in the
    output folder and returns the full path it wrote.
    """
    flow_entries = []
    for flow_id, flow_name, _object_type, short_type, published_version in found_flows:
        if not published_version:
            # No published version means there is nothing published to export.
            print(
                "   Leaving %s out of the export file because it has no "
                "published version." % (flow_name or flow_id)
            )
            continue

        flow_entries.append({
            'flow': {
                'id': flow_id,
                'name': flow_name or '',
                'type': short_type or '',
                'version': published_version,
            },
            'fileName': safe_export_file_name(flow_name, flow_id),
            'exportType': 'Yaml',
        })

    body = {'flows': flow_entries}

    file_path = os.path.join(OUTPUT_DIR, 'Architect_Export_Request_%s.json' % timestamp)
    with open(file_path, 'w') as output_file:
        json.dump(body, output_file, indent=2)
    return file_path


# --- Main --------------------------------------------------------------------
def main():
    """Walk the flow trees of one or more starting flows and write a review list.

    Step 0: Stop early if the starting flow list is empty, so we never call the
            API with nothing to do.
    Step 1: Sign in to Genesys Cloud.
    Step 2: Walk the dependency tree of each starting flow. Collect every flow
            and every operating schedule the trees touch, with no duplicates.
    Step 3: Write two files, both stamped with the same run time so they pair up:
              - an Excel file listing every flow and operating schedule, so you
                can review them and open them by hand; and
              - a JSON file listing the flows only, ready to paste into the Dev
                Center to export their YAML.
    """
    # Step 0: stop early if no starting IDs were given. We drop any blank lines
    # first, so a stray empty quote in the list does not reach the API as an
    # empty ID.
    starting_flow_ids = [flow_id for flow_id in STARTING_FLOW_IDS if flow_id]
    if not starting_flow_ids:
        raise SystemExit(
            "Set at least one flow ID in STARTING_FLOW_IDS near the top of the "
            "script before running."
        )

    # Step 1: sign in.
    architect_api = build_apis()

    # Step 2: walk the tree of each starting flow.
    print("Walking the flow tree(s) from %d starting flow(s) ...\n" % len(starting_flow_ids))
    found_flows, found_schedules = walk_flow_tree(architect_api, starting_flow_ids)
    print(
        "\nFinished the walk. Found %d flow(s) and %d operating schedule(s)."
        % (len(found_flows), len(found_schedules))
    )
    if not found_flows:
        raise SystemExit(
            "No flows were found from the starting IDs, so there is nothing to "
            "list. Check that the IDs in STARTING_FLOW_IDS are real flows the "
            "credentials can read."
        )

    # Step 3: write both output files. They share one timestamp so the review
    # file and the export request file from the same run are easy to pair up.
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    review_path = write_review_excel(found_flows, found_schedules, timestamp)
    print("\nWrote the review file to %s" % review_path)
    request_path = write_export_request_json(found_flows, timestamp)
    print("Wrote the export request file to %s" % request_path)


if __name__ == '__main__':
    main()
