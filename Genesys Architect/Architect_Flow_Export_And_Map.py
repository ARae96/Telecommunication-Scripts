# =============================================================================
# Genesys Cloud - Architect Flow Export and Caller Map (OFFLINE / LOCAL)
# =============================================================================
# Starts from one or more Architect flows and walks each one's dependency tree,
# so you get the whole family of flows those starting flows lean on, not just
# the starting flows themselves. You enter the starting flow IDs near the top of
# the file. The script signs in to Genesys Cloud, reads each flow, follows its
# dependencies, and then downloads the full configuration of every flow it
# found.
#
# What the walk follows and what it stops at:
#   - It follows flows. A flow can call another flow, which can call more
#     flows, so the script keeps digging until it reaches the ends of the tree.
#   - It records operating schedules it runs into, but it does not dig into
#     them. A schedule does not call other flows, so it is an end point.
#   - It ignores every other kind of dependency (such as prompts and
#     recordings), because you only asked for flows and operating schedules.
#
# What the script writes (all inside the folder this file lives in):
#   1. A new folder for this run, so each run's files stay together:
#        Architect_Flow_Export_<timestamp>/
#   2. Inside that folder, one JSON file per flow, holding the flow's full
#      published configuration:
#        <flow name>_<flow id>.json
#   3. An Excel file listing every flow and operating schedule found, so you
#      have a review list alongside the downloaded flows. Each row shows the
#      item type, name, ID, and a web link.
#        Architect_Export_Review_<timestamp>.xlsx
#   4. A Mermaid flowchart file showing how the flows route callers to each
#      other, with menu digits and transfer targets on the arrows. Open it in
#      any Mermaid viewer to see the caller journey as a picture.
#        Architect_Flowchart_<timestamp>.mmd
#
# About the file format (please read):
#   These files hold each flow's configuration as JSON, read straight from
#   Genesys. This is NOT the same as the Architect "YAML export" you get from the
#   Architect UI. The YAML export is built by a background "export job" that
#   belongs to a real person, so Genesys only runs it for a user sign-in; the
#   sign-in this script uses (a client id and secret, with no user behind it)
#   cannot run that job. The configuration JSON here holds the full flow
#   definition and is read with a plain call that works without a user, so it is
#   what we can pull automatically. Use it to review, compare, or archive flow
#   logic. If you need the re-importable YAML, export those flows by hand from
#   the Architect UI using the review list.
#
# This script only reads from Genesys, so there is no DRY_RUN switch here.
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
    'cfaad3f8-fd86-4506-8e61-9386b3b218d9',
    
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


def safe_flow_file_name(flow_name, flow_id):
    """Return a safe file name for a flow's config, like <flow name>_<flow id>.json.

    Flow names can hold characters that are not safe in a file name, such as a
    slash, a colon, or a space, so we replace anything that is not a letter,
    number, dash, or underscore with an underscore. We tack the flow ID on the
    end so two flows with the same name still get their own file, and so every
    name is unique. Falls back to just the ID if the flow has no name.
    """
    if not flow_name:
        return '%s.json' % flow_id

    cleaned_characters = []
    for character in flow_name:
        if character.isalnum() or character in ('-', '_'):
            cleaned_characters.append(character)
        else:
            cleaned_characters.append('_')
    cleaned_name = ''.join(cleaned_characters)
    return '%s_%s.json' % (cleaned_name, flow_id)


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


def download_flow_configs(architect_api, found_flows, timestamp):
    """Download each flow's published configuration into a new per-run folder.

    Makes a folder named Architect_Flow_Export_<timestamp> inside the output
    folder, then saves one JSON file per flow into it. Each file holds the
    flow's full configuration at its published version, read straight from
    Genesys with get_flow_version_configuration.

    Only flows that have a published version are downloaded. A flow with no
    published version has nothing published to read, so we skip it and print a
    note naming it. We also catch a failed read per flow, print a message, and
    keep going, so one bad flow does not stop the rest.

    Returns a tuple of (folder path, number of files written, configs). The
    configs value is a dict of flow id to the flow's configuration, so the
    caller can build the flowchart without reading the files back from disk.
    """
    export_folder = os.path.join(OUTPUT_DIR, 'Architect_Flow_Export_%s' % timestamp)
    os.makedirs(export_folder, exist_ok=True)

    written_count = 0
    configs = {}
    for flow_id, flow_name, _object_type, _short_type, published_version in found_flows:
        if not published_version:
            # No published version means there is nothing published to download.
            print(
                "   Skipping %s because it has no published version."
                % (flow_name or flow_id)
            )
            continue

        try:
            config = architect_api.get_flow_version_configuration(flow_id, published_version)
        except ApiException as e:
            print("   Could not download config for %s: %s" % (flow_name or flow_id, e))
            continue

        file_path = os.path.join(export_folder, safe_flow_file_name(flow_name, flow_id))
        with open(file_path, 'w') as output_file:
            json.dump(config, output_file, indent=2, default=str)
        configs[flow_id] = config
        written_count += 1
        print("   Saved %s" % os.path.basename(file_path))

    return (export_folder, written_count, configs)


def action_kind(action):
    """Return an action's short kind name, such as "TransferFlowAction".

    Genesys stores the kind in an "__type" field with extra text after a comma.
    We keep just the part before the comma, which is the name we care about.
    Returns an empty string if the action has no kind.
    """
    return (action.get('__type') or '').split(',')[0]


def action_target(action):
    """Return a (kind, label) pair describing where an action sends the caller.

    Reads the one field that names the target for each kind of transfer:
      - a flow transfer uses the flow's name;
      - an external transfer uses the phone number in externalNumber.text;
      - a queue, group, or user transfer uses that object's name.
    Returns a tuple like ("flow", "0.1_MAIN_MENU") or ("ext", "+13855551234").
    Returns ("", "") when the action is not a transfer we chart (such as repeat
    menu, previous menu, or disconnect).
    """
    kind = action_kind(action)
    if kind in ('TransferFlowAction', 'TransferFlowSecureAction'):
        return ('flow', action.get('flowName') or action.get('flowId') or '(flow)')
    if kind == 'TransferExternalAction':
        number = action.get('externalNumber') or {}
        text = number.get('text') if isinstance(number, dict) else None
        return ('ext', text or '(external number)')
    for key in ('queue', 'group', 'user'):
        target = action.get(key)
        if isinstance(target, dict):
            return (key, target.get('name') or target.get('id') or ('(' + key + ')'))
    return ('', '')


def collect_menu_edges(config):
    """Return the caller-facing menu choices in one flow's configuration.

    Looks through the flow's menus and, for each choice that sends the caller
    somewhere, returns a simple record of it. We skip choices that just repeat
    or go back a menu, because they are not a move to a new place.

    Returns a list of dicts, each with:
      - digit:  the key the caller presses (may be None for a spoken choice)
      - label:  the choice name, such as "Financial Services"
      - kind:   the target kind ("flow", "ext", "queue", "group", "user")
      - target: the target label (a flow name or a phone number)
    """
    edges = []
    for item in config.get('flowSequenceItemList', []) or []:
        for choice in (item.get('menuChoiceList') or []):
            action = choice.get('action') or {}
            if action_kind(action) in ('RepeatMenuAction', 'PreviousMenuAction'):
                continue
            kind, target = action_target(action)
            if not kind:
                continue
            edges.append({
                'digit': choice.get('digit'),
                'label': choice.get('name') or '',
                'kind': kind,
                'target': target,
            })
    return edges


def collect_all_actions(obj, found):
    """Fill found with every action dict (one that has an "__type") under obj.

    Walks the whole structure, depth-first, into dicts and lists. We use this to
    find transfers that are not inside a menu, such as the ones a flow reaches
    after a decision (for example an identity check that passed or failed).
    """
    if isinstance(obj, dict):
        if '__type' in obj:
            found.append(obj)
        for value in obj.values():
            collect_all_actions(value, found)
    elif isinstance(obj, list):
        for value in obj:
            collect_all_actions(value, found)


def build_action_index(config):
    """Return a dict of action id to action for every action in a flow config.

    We use this to follow the action chain from one action to the next by id,
    which is how we trace a decision branch to the flow it ends up transferring
    the caller to.
    """
    index = {}

    def walk(node):
        if isinstance(node, dict):
            if 'id' in node and '__type' in node:
                index[node['id']] = node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(config)
    return index


def decision_condition_text(decision):
    """Return the plain-text condition a DecisionAction checks, or '' if none.

    Genesys stores the condition as a small expression tree under
    expression.config. The tree carries a "text" field with the condition
    written out, such as 'Task.LexSSN == Task.SalesforceSSN', so we pull that.
    """
    expression = decision.get('expression') or {}
    config_part = expression.get('config') or {}
    for value in config_part.values():
        if isinstance(value, dict) and value.get('text'):
            return value['text']
    return ''


def first_transfer_from(start_id, index, visited):
    """Follow the action chain from start_id to the first flow transfer it hits.

    Walks action to action: a plain action points to the next with "nextAction",
    and an action with a single path follows that one path. We stop and return
    the target flow name as soon as we reach a flow transfer. We stop with None
    if the chain ends (a disconnect or a menu), or if it reaches another branch
    we cannot follow without more logic. A visited set guards against loops.
    """
    current_id = start_id
    while current_id and current_id not in visited:
        visited.add(current_id)
        action = index.get(current_id)
        if action is None:
            return None
        if action_kind(action) in ('TransferFlowAction', 'TransferFlowSecureAction'):
            return action.get('flowName') or action.get('flowId')
        if action.get('nextAction'):
            current_id = action['nextAction']
            continue
        paths = action.get('paths') or []
        if len(paths) == 1:
            current_id = paths[0].get('nextActionId')
            continue
        # A branch with more than one path, or a dead end. We cannot tell which
        # way to go from here without more logic, so we stop.
        return None
    return None


def collect_logic_flow_edges(config, menu_targets):
    """Return flow transfers that do not come from a menu, labeled where we can.

    Some flows send the caller onward based on logic, not a key press. Two kinds
    show up:
      - A decision (an "if" check such as an identity or schedule test) whose
        Yes or No branch leads to a flow transfer. We trace each branch to the
        flow it reaches and label the edge with the branch (Yes/No) and the
        condition text, so the chart shows why the caller is routed there.
      - A plain transfer with no decision in front of it. We label this
        "(auto)" because there is no condition to show.

    menu_targets is the set of target flow names the menu edges already cover,
    so we do not draw the same edge twice.

    Returns a list of (target_flow_name, label) tuples, with duplicate
    (target, label) pairs removed, kept in the order first seen.
    """
    index = build_action_index(config)

    edges = []
    seen = set()
    labeled_targets = set()

    # First pass: decision branches that lead to a transfer.
    for action in index.values():
        if action_kind(action) != 'DecisionAction':
            continue
        condition = decision_condition_text(action)
        for path in action.get('paths', []):
            branch = path.get('label') or ''
            target = first_transfer_from(path.get('nextActionId'), index, set())
            if not target or target in menu_targets:
                continue
            if condition:
                label = '%s: %s' % (branch, condition)
            else:
                label = branch
            key = (target, label)
            if key in seen:
                continue
            seen.add(key)
            labeled_targets.add(target)
            edges.append((target, label))

    # Second pass: transfers not already explained by a menu or a decision.
    all_actions = []
    collect_all_actions(config.get('flowSequenceItemList', []), all_actions)
    for action in all_actions:
        if action_kind(action) not in ('TransferFlowAction', 'TransferFlowSecureAction'):
            continue
        target = action.get('flowName') or action.get('flowId')
        if not target or target in menu_targets or target in labeled_targets:
            continue
        key = (target, '(auto)')
        if key in seen:
            continue
        seen.add(key)
        edges.append((target, '(auto)'))

    return edges


def mermaid_node_id(flow_id):
    """Return a short, Mermaid-safe node id built from a flow id.

    Mermaid node ids cannot contain dashes, so we keep the letters and numbers
    from the flow id and add an "f" in front so the id never starts with a
    number. The result is stable for a given flow id.
    """
    cleaned = ''.join(c for c in (flow_id or '') if c.isalnum())
    return 'f' + cleaned


def mermaid_escape(text):
    """Return text safe to drop inside a Mermaid label.

    Replaces the characters that break Mermaid labels (quotes and the pipe and
    bracket characters) with spaces, and trims the length so a long name does
    not blow out the chart.
    """
    cleaned = text or ''
    for bad in ['"', '|', '[', ']', '{', '}', '(', ')']:
        cleaned = cleaned.replace(bad, ' ')
    cleaned = ' '.join(cleaned.split())
    return cleaned[:48]


def is_starting_flow(flow_id, starting_flow_ids):
    """Return True if this flow is one the caller can land on first."""
    return flow_id in starting_flow_ids


def write_flowchart_mermaid(found_flows, configs, timestamp, starting_flow_ids):
    """Write a styled Mermaid flowchart of how the flows route callers.

    Draws one box per flow and one arrow per routing step:
      - a menu choice, labeled with the digit and the choice name;
      - a decision branch, labeled with Yes or No and the condition it checks;
      - a plain automatic transfer, labeled "(auto)".
    A choice that dials an outside phone number gets its own box with the number,
    so you can see where a caller leaves the flows. A transfer to a flow outside
    the walked set gets its own box, marked so.

    The boxes are colored by role so the picture is easy to read: entry flows
    (where a call lands), regular flows, phone numbers, and outside-the-set
    targets each get their own color. The colors use plain "style" lines, which
    import cleanly into tools such as Lucidchart.

    Writes one file named Architect_Flowchart_<timestamp>.mmd in the output
    folder and returns the full path it wrote.
    """
    # Map flow name -> node id so a choice's target flow name finds its box.
    name_to_id = {}
    for flow_id, flow_name, _ot, _st, _pv in found_flows:
        if flow_name:
            name_to_id[flow_name] = mermaid_node_id(flow_id)

    lines = ['flowchart TD']

    entry_nodes = []
    flow_nodes = []
    # One box per flow we found. Entry flows get a rounded "stadium" shape so
    # the places a call can start stand out from the rest.
    for flow_id, flow_name, _ot, _st, _pv in found_flows:
        node = mermaid_node_id(flow_id)
        label = mermaid_escape(flow_name or flow_id)
        if is_starting_flow(flow_id, starting_flow_ids):
            lines.append('    %s(["%s"])' % (node, label))
            entry_nodes.append(node)
        else:
            lines.append('    %s["%s"]' % (node, label))
            flow_nodes.append(node)

    external_nodes = {}    # phone number -> node id, one box per number
    extra_flow_nodes = {}  # outside-the-set target -> node id
    edge_lines = []

    for flow_id, flow_name, _ot, _st, _pv in found_flows:
        config = configs.get(flow_id)
        if not config:
            continue
        source = mermaid_node_id(flow_id)

        # Menu edges: a key press that sends the caller to a flow or a number.
        menu_targets = set()
        for edge in collect_menu_edges(config):
            digit = edge['digit']
            prefix = ('%s: ' % digit) if digit not in (None, '') else ''
            label = mermaid_escape(prefix + edge['label'])

            if edge['kind'] == 'ext':
                number = edge['target']
                if number not in external_nodes:
                    external_nodes[number] = 'ext%d' % len(external_nodes)
                target_node = external_nodes[number]
            elif edge['kind'] == 'flow':
                menu_targets.add(edge['target'])
                target_node = name_to_id.get(edge['target'])
                if not target_node:
                    if edge['target'] not in extra_flow_nodes:
                        extra_flow_nodes[edge['target']] = 'x%d' % len(extra_flow_nodes)
                    target_node = extra_flow_nodes[edge['target']]
            else:
                key = edge['kind'] + ':' + edge['target']
                if key not in extra_flow_nodes:
                    extra_flow_nodes[key] = 'x%d' % len(extra_flow_nodes)
                target_node = extra_flow_nodes[key]

            edge_lines.append('    %s -- "%s" --> %s' % (source, label, target_node))

        # Logic edges: decision branches and automatic transfers, now labeled
        # with the branch and the condition where we can read it.
        for target, label in collect_logic_flow_edges(config, menu_targets):
            target_node = name_to_id.get(target)
            if not target_node:
                if target not in extra_flow_nodes:
                    extra_flow_nodes[target] = 'x%d' % len(extra_flow_nodes)
                target_node = extra_flow_nodes[target]
            edge_lines.append('    %s -. "%s" .-> %s' % (source, mermaid_escape(label), target_node))

    # Boxes for the external phone numbers we linked to.
    ext_node_ids = []
    for number, node in external_nodes.items():
        lines.append('    %s["Phone %s"]' % (node, mermaid_escape(number)))
        ext_node_ids.append(node)
    # Boxes for targets outside the walked set.
    outside_node_ids = []
    for name, node in extra_flow_nodes.items():
        # name may be "queue:...", "group:...", or a flow name; show it plainly.
        shown = name.split(':', 1)[-1] if ':' in name else name
        lines.append('    %s["%s (outside set)"]' % (node, mermaid_escape(shown)))
        outside_node_ids.append(node)

    lines.append('')
    lines.extend(edge_lines)

    # Styling: one color per role. These are plain style lines so they import
    # cleanly into Lucidchart and still render in any Mermaid viewer.
    lines.append('')
    for node in entry_nodes:
        lines.append('    style %s fill:#1f6feb,stroke:#0b3b8c,color:#ffffff' % node)
    for node in flow_nodes:
        lines.append('    style %s fill:#e8f0fe,stroke:#1f6feb,color:#13294b' % node)
    for node in ext_node_ids:
        lines.append('    style %s fill:#fde8e8,stroke:#d1242f,color:#5c0a0f' % node)
    for node in outside_node_ids:
        lines.append('    style %s fill:#fff4e5,stroke:#d98c00,color:#5c3b00' % node)

    file_path = os.path.join(OUTPUT_DIR, 'Architect_Flowchart_%s.mmd' % timestamp)
    with open(file_path, 'w') as output_file:
        output_file.write('\n'.join(lines) + '\n')
    return file_path


# --- Main --------------------------------------------------------------------
def main():
    """Walk the flow trees of one or more starting flows and write a review list.

    Step 0: Stop early if the starting flow list is empty, so we never call the
            API with nothing to do.
    Step 1: Sign in to Genesys Cloud.
    Step 2: Walk the dependency tree of each starting flow. Collect every flow
            and every operating schedule the trees touch, with no duplicates.
    Step 3: Write the output, all stamped with the same run time so it pairs up:
              - an Excel file listing every flow and operating schedule, as a
                review list;
              - a per-run folder holding one JSON file per flow, each with the
                flow's full published configuration; and
              - a Mermaid flowchart file showing how the flows route callers to
                each other, labeled with menu digits and transfer targets.
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

    # Step 3: write the review file and download the flow configs. Both share
    # one timestamp so the review file and the export folder from the same run
    # are easy to pair up.
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    review_path = write_review_excel(found_flows, found_schedules, timestamp)
    print("\nWrote the review file to %s" % review_path)

    print("\nDownloading %d flow configuration(s) ...\n" % len(found_flows))
    export_folder, written_count, configs = download_flow_configs(architect_api, found_flows, timestamp)
    print(
        "\nSaved %d of %d flow configuration(s) to %s"
        % (written_count, len(found_flows), export_folder)
    )

    # Step 4: build the caller routing flowchart from the configs we just read.
    flowchart_path = write_flowchart_mermaid(found_flows, configs, timestamp, set(starting_flow_ids))
    print("Wrote the caller routing flowchart to %s" % flowchart_path)


if __name__ == '__main__':
    main()
