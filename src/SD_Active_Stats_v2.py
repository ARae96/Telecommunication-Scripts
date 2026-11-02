# =============================================================================
# Genesys Cloud - Live Queue Dashboard (Service Desk)
# =============================================================================
# Reads live and same-day numbers for a set of Genesys Cloud queues and prints
# them as side-by-side cards in the terminal, one card per queue. It is built to
# mirror the Service Desk dashboard, which shows three queues next to each other
# (Student, Staff, and Academy), each with the same six numbers.
#
# For each queue it reads two kinds of data:
#
#   1. Right-now numbers (called "observations") that show what is happening in
#      the queue at this moment: how many calls are waiting, how many agents are
#      on a call, and how many agents are idle and ready to take a call.
#   2. Same-day totals (called "aggregates") that add up what has happened in
#      the queue since midnight today: how many calls were answered, the service
#      level (SLA) percent, and the abandon rate.
#
# A note on calls waiting: a waiting call can be a normal inbound call or a
# call back (a call the system places to a customer who asked to be called
# instead of waiting on hold). Genesys treats these as two different media
# types, "voice" and "callback". This script counts both and adds them together
# so "Calls Waiting" reflects everything a customer is waiting on.
#
# SLA stands for service level agreement. The SLA percent is the share of calls
# that were answered within the target wait time set on the queue in Genesys.
#
# A note on where these numbers come from: Genesys has no API that hands back
# the finished values shown on a saved dashboard. A dashboard is just a view
# that runs these same queries in the browser and draws the result. So this
# script reads the queues directly by their IDs and does the same math, which
# is why it needs the queue IDs below rather than a dashboard ID.
#
# This is a read-only report. It does not change anything in Genesys Cloud.
#
# What each queue card shows:
#   Calls Waiting (voice waiting now)     | Callbacks Waiting (callbacks now)
#   On Call (agents interacting)          | Idle (agents ready)
#   Calls (voice answered today)          | Callbacks (callbacks answered today)
#   SLA (service level percent, voice)    | Abandon (abandon rate percent, voice)
#
# There is no total-answered cell: add the Calls and Callbacks answered cells
# to get the day's total. The SLA and abandon rates cover normal inbound (voice)
# calls only, because we do not hold those targets for call backs.
#
# Run locally with:
#   pip install -r requirements.txt
# and a populated .env (GENESYS_CLOUD_CLIENT_ID / GENESYS_CLOUD_CLIENT_SECRET).
# =============================================================================


# --- Imports -----------------------------------------------------------------
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from dotenv import load_dotenv


# --- Configuration -----------------------------------------------------------
# The queues to show on the dashboard, in the left-to-right order you want the
# cards to appear. Each entry is a (card title, queue ID) pair. The card title
# is the short label printed at the top of the card; the queue ID is the long
# identifier Genesys gives every queue, such as
# "a1b2c3d4-5678-90ab-cdef-1234567890ab". We use the ID, not the name, because
# the ID always points at exactly one queue even when two queues share a name.
#
# To add, remove, or reorder cards, just change this list. You can find a
# queue's ID in Genesys under Admin > Contact Center > Queues (it is in the web
# address when you open the queue).
DASHBOARD_QUEUES = [
    ('Student', 'b75e16f3-4cf7-42f5-8dd0-dadb95638146'),
    ('Staff', 'b60d8687-1459-4806-a1c1-8996b94521ce'),
    ('Academy', 'd0816199-bb30-4e8b-9480-d5546a7d7cc5'),
]

# How wide each card is, in characters. The cards are printed side by side, so
# keep this small enough that a full row of cards fits in your terminal window.
# It also has to be wide enough for the longest cell label ("Callbacks
# Waiting"), so do not set it much lower than this.
CARD_WIDTH = 40

# The time zone the "today" numbers are counted in. The same-day totals (total
# calls, SLA, abandon) cover from midnight to now in this time zone, so set it
# to your contact center's local time zone. If you leave it as UTC, "today"
# starts at midnight UTC, which may not line up with your business day. Use a
# name from the IANA time zone database, such as "America/Denver".
REPORT_TIME_ZONE = 'America/Denver'

# The two voice media types, named so we can label them in the output. A normal
# inbound call is "voice" and a scheduled call back is "callback" (a call the
# system places to a customer who asked to be called instead of holding). We
# keep these two apart everywhere: the cards show calls waiting and call backs
# waiting separately, and the SLA and abandon rates count voice calls only.
MEDIA_TYPE_VOICE = 'voice'
MEDIA_TYPE_CALLBACK = 'callback'

# An agent is counted as "on a call" when their routing status is INTERACTING,
# and as "idle" when their routing status is IDLE. These are the two on-queue
# statuses in Genesys: IDLE means ready and waiting for a call, INTERACTING
# means currently handling one. Other statuses (such as OFF_QUEUE or
# NOT_RESPONDING) are not counted as either.
ROUTING_STATUS_ON_CALL = 'INTERACTING'
ROUTING_STATUS_IDLE = 'IDLE'

# The right-now metrics we ask Genesys for. oWaiting is the count of
# interactions waiting in the queue. oUserRoutingStatuses is the count of
# agents broken down by routing status (IDLE, INTERACTING, and so on), which is
# how we get agents-on-calls and agents-idle.
OBSERVATION_METRICS = ['oWaiting', 'oUserRoutingStatuses']

# The same-day totals we ask Genesys for:
#   - nOffered: how many calls came in.
#   - tAnswered: how many were answered.
#   - tAbandon: how many were abandoned (used for the abandon rate).
#   - nOverSla: how many answered calls missed the service level target.
#   - tFlowOut: how many calls left the queue another way (for example routed
#     out) and still count toward the service level denominator.
#
# We read nOverSla and tFlowOut because the service level has to be worked out
# from these counts. Genesys does not return a ready-made service level on this
# endpoint (the oServiceLevel metric is silently left out of the response), so
# we compute it ourselves using the same formula Genesys uses:
#   service level = (tAnswered - nOverSla) / (tAnswered + tFlowOut)
AGGREGATE_METRICS = ['nOffered', 'tAnswered', 'tAbandon', 'nOverSla', 'tFlowOut']


# --- Authentication ----------------------------------------------------------
def build_apis():
    """Sign in to Genesys Cloud and return the API clients this report needs.

    Reads GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET from the .env
    file at the workspace root (one folder up from this script). Stops the
    script with a helpful message if either value is missing. Returns the
    clients in this order: (RoutingApi, AnalyticsApi). RoutingApi confirms each
    queue ID is real; AnalyticsApi reads the live and same-day numbers.
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
    return (
        PureCloudPlatformClientV2.RoutingApi(apiclient),
        PureCloudPlatformClientV2.AnalyticsApi(apiclient),
    )


# --- Helpers: reading one queue ----------------------------------------------
def confirm_queue_exists(routing_api, title, queue_id):
    """Check that a queue ID is real, and stop with a clear message if not.

    Looks the queue up by its ID in Genesys Cloud so a mistyped ID is caught
    early with a helpful message, instead of showing up later as empty numbers.
    Returns nothing; it either passes quietly or stops the script.

    The title is the card label from the configuration (for example "Student"),
    and it is only used to make the error message easy to act on.
    """
    try:
        # Genesys API call: RoutingApi.get_routing_queue - reads one queue by
        # its ID. We only use it here to confirm the ID points at a real queue.
        routing_api.get_routing_queue(queue_id)
    except ApiException as e:
        raise SystemExit(
            "Could not find the '%s' queue (ID '%s') in Genesys Cloud. Check the "
            "ID in DASHBOARD_QUEUES and try again. (%s)" % (title, queue_id, e)
        )


def build_observation_query(queue_id):
    """Return the query object that asks for one queue's right-now numbers.

    Builds the filter so Genesys only looks at the queue we care about, and asks
    for the observation metrics in OBSERVATION_METRICS (waiting interactions and
    agent routing statuses). Returns a QueueObservationQuery ready to send.
    """
    predicate = PureCloudPlatformClientV2.QueueObservationQueryPredicate()
    predicate.dimension = 'queueId'
    predicate.value = queue_id

    query_filter = PureCloudPlatformClientV2.QueueObservationQueryFilter()
    query_filter.type = 'and'
    query_filter.predicates = [predicate]

    query = PureCloudPlatformClientV2.QueueObservationQuery()
    query.filter = query_filter
    query.metrics = OBSERVATION_METRICS
    return query


def get_group_dimensions(data_group):
    """Return the dimensions map for a group of observation results.

    The observation results come back in groups, and each group is tagged with
    the dimensions it covers (for example {"mediaType": "voice"}) in its group
    field. We read that map so we can tell which media type a group of waiting
    interactions is about. Returns an empty dict when the group has no
    dimensions.

    Note the routing status (IDLE, INTERACTING) is not here. It lives on each
    metric row's "qualifier" instead, so read_live_numbers reads it from the
    row, not from this map.
    """
    return getattr(data_group, 'group', None) or {}


def read_live_numbers(analytics_api, queue_id):
    """Return the queue's right-now numbers as a small dict.

    Asks Genesys for the live observation numbers for the queue and pulls out
    four counts: how many normal calls are waiting, how many call backs are
    waiting, how many agents are on a call, and how many agents are idle.
    Returns a dict with the keys "calls_waiting", "callbacks_waiting",
    "agents_on_calls", and "agents_idle".

    How the counts are read:
      - Calls waiting and call backs waiting: the oWaiting metric, kept apart by
        media type so normal calls (voice) and call backs (callback) each get
        their own count instead of being added together.
      - Agents on calls and agents idle: the oUserRoutingStatuses metric, which
        reports a count per routing status. We read the INTERACTING count as
        agents on calls and the IDLE count as agents idle.
    """
    query = build_observation_query(queue_id)

    try:
        # Genesys API call: AnalyticsApi.post_analytics_queues_observations_query
        # - returns the live numbers for the queue, grouped by media type.
        response = analytics_api.post_analytics_queues_observations_query(query)
    except ApiException as e:
        raise SystemExit("Could not read live queue numbers from Genesys Cloud: %s" % e)

    calls_waiting = 0
    callbacks_waiting = 0
    agents_on_calls = 0
    agents_idle = 0

    results = getattr(response, 'results', None) or []
    for data_group in results:
        # The media type lives on the group (for example {"mediaType": "voice"})
        # and tells us which waiting interactions to count. The routing status,
        # on the other hand, lives on each metric row's "qualifier", not on the
        # group, so we read that below per row.
        dimensions = get_group_dimensions(data_group)
        media_type = dimensions.get('mediaType')
        data_rows = getattr(data_group, 'data', None) or []

        for row in data_rows:
            metric_name = getattr(row, 'metric', None)
            stats = getattr(row, 'stats', None)
            # Every observation value arrives as a "count" on the stats object.
            # If it is missing we treat it as zero so one empty row does not
            # break the totals.
            count = getattr(stats, 'count', None) or 0

            if metric_name == 'oWaiting':
                # Keep normal calls and call backs apart so the card can show
                # each on its own. Any other media type is left out.
                if media_type == MEDIA_TYPE_VOICE:
                    calls_waiting += count
                elif media_type == MEDIA_TYPE_CALLBACK:
                    callbacks_waiting += count
            elif metric_name == 'oUserRoutingStatuses':
                # The routing status comes back on the row's "qualifier", such
                # as "INTERACTING" for agents on a call or "IDLE" for agents
                # ready and waiting. Reading it from the group instead (as an
                # earlier version did) always found nothing, which is why the
                # on-call count was stuck at zero. Genesys leaves out any status
                # with no agents, so a status we never see just stays at zero.
                routing_status = getattr(row, 'qualifier', None)
                if routing_status == ROUTING_STATUS_ON_CALL:
                    agents_on_calls += count
                elif routing_status == ROUTING_STATUS_IDLE:
                    agents_idle += count

    return {
        'calls_waiting': calls_waiting,
        'callbacks_waiting': callbacks_waiting,
        'agents_on_calls': agents_on_calls,
        'agents_idle': agents_idle,
    }


def get_start_of_today_interval():
    """Return the time range string for midnight today up to right now.

    The same-day totals need a time range. We use the start of today through the
    current moment, counted in the REPORT_TIME_ZONE so "today" lines up with the
    contact center's business day rather than midnight UTC. The range is written
    in the ISO-8601 format Genesys expects, with a time zone offset on each end,
    such as "2026-11-02T00:00:00-06:00/2026-11-02T14:30:00-06:00".

    We pair this with a one-day granularity on the query (see
    build_aggregate_query), so Genesys returns the whole day as a single bucket
    instead of splitting it into 30-minute slices.
    """
    zone = ZoneInfo(REPORT_TIME_ZONE)
    now = datetime.now(zone)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Genesys wants the range as "start/end". We write each end with its time
    # zone offset (for example -06:00) so there is no ambiguity about when the
    # day starts.
    start_text = start_of_today.strftime('%Y-%m-%dT%H:%M:%S%z')
    end_text = now.strftime('%Y-%m-%dT%H:%M:%S%z')
    # strftime writes the offset as "-0600"; Genesys wants "-06:00", so add the
    # colon. The offset is always the last five characters.
    start_text = start_text[:-2] + ':' + start_text[-2:]
    end_text = end_text[:-2] + ':' + end_text[-2:]
    return "%s/%s" % (start_text, end_text)


def build_aggregate_query(queue_id):
    """Return the query object that asks for one queue's same-day totals.

    Builds the filter so Genesys only adds up the queue we care about, sets the
    time range to the start of today through now, and asks for the aggregate
    metrics in AGGREGATE_METRICS (offered, answered, abandoned, service level).
    Returns a ConversationAggregationQuery ready to send.

    Two settings make the totals cover the whole day and split by call type:
      - granularity "P1D" tells Genesys to return the whole day as one bucket
        instead of many 30-minute slices. Without it, Genesys can split the day
        up, and the service level would be the rate for just one slice rather
        than the day so far.
      - group_by "mediaType" splits the totals by call type, so normal calls
        (voice) and call backs (callback) come back as separate groups. This is
        what lets us show the total calls answered split by type.
    """
    predicate = PureCloudPlatformClientV2.ConversationAggregateQueryPredicate()
    predicate.dimension = 'queueId'
    predicate.value = queue_id

    query_filter = PureCloudPlatformClientV2.ConversationAggregateQueryFilter()
    query_filter.type = 'and'
    query_filter.predicates = [predicate]

    query = PureCloudPlatformClientV2.ConversationAggregationQuery()
    query.interval = get_start_of_today_interval()
    # "P1D" is the ISO-8601 way of saying "one day", so the whole day comes back
    # as a single bucket.
    query.granularity = 'P1D'
    query.time_zone = REPORT_TIME_ZONE
    query.group_by = ['mediaType']
    query.filter = query_filter
    query.metrics = AGGREGATE_METRICS
    return query


def get_group_media_type(data_group):
    """Return the media type a result group is for, or None.

    Because we group the aggregate query by media type, each result group is
    tagged with its media type (for example {"mediaType": "voice"}) in its group
    field. This reads that value so the caller can tell normal calls from call
    backs. Returns None when the group has no media type.
    """
    group = getattr(data_group, 'group', None) or {}
    return group.get('mediaType')


def sum_metric_counts(data_group):
    """Return a map from metric name to its summed count for one result group.

    The same-day totals have an extra layer we have to step through. Each result
    group holds a "data" list, one entry per time bucket, and each of those
    entries holds the list of metrics with their stats. We ask for the whole day
    as one bucket, so there is normally just one entry, but we still add the
    counts across entries so an unexpected split does not drop any calls.

    Returns a plain dict from metric name to the total count for that metric
    (for example {"tAnswered": 39, "nOffered": 110, "tAbandon": 71}). Only the
    count is summed here; the service level is handled on its own because it is
    a ratio, not a count (see read_today_totals).
    """
    counts_by_metric = {}

    data_entries = getattr(data_group, 'data', None) or []
    for data_entry in data_entries:
        metrics = getattr(data_entry, 'metrics', None) or []
        for metric in metrics:
            metric_name = getattr(metric, 'metric', None)
            stats = getattr(metric, 'stats', None)
            if not metric_name or stats is None:
                continue
            count = getattr(stats, 'count', None) or 0
            counts_by_metric[metric_name] = counts_by_metric.get(metric_name, 0) + count

    return counts_by_metric


def compute_service_level_percent(counts):
    """Return the service level percent from a group's metric counts, or None.

    The service level is the share of calls answered within the target wait time
    set on the queue. Genesys does not hand back a ready-made service level on
    the conversation aggregate endpoint (the oServiceLevel metric is left out of
    the response entirely), so we work it out from the counts using the same
    formula Genesys uses in its performance views:

        service level = (tAnswered - nOverSla) / (tAnswered + tFlowOut)

    In plain terms: of the calls that were answered or routed out of the queue,
    what share were answered without missing the target time. nOverSla is the
    count of answered calls that missed the target, so subtracting it from the
    answered count leaves the ones that met the target.

    Takes the counts dict for one media-type group (as built by
    sum_metric_counts). Returns the percent as a number (for example 31.2), or
    None when there were no answered or routed-out calls, so the caller can tell
    "no data yet" apart from a real zero.
    """
    answered = counts.get('tAnswered', 0)
    over_sla = counts.get('nOverSla', 0)
    flow_out = counts.get('tFlowOut', 0)

    # The denominator is the calls that count toward service level: the ones
    # answered plus the ones that flowed out of the queue. If there are none
    # yet, there is no service level to report.
    denominator = answered + flow_out
    if denominator <= 0:
        return None

    within_target = answered - over_sla
    return (within_target / denominator) * 100


def read_today_totals(analytics_api, queue_id):
    """Return the queue's same-day totals as a small dict.

    Asks Genesys for the same-day aggregate numbers for the queue, split by
    media type, and works out the answered count (split into normal calls and
    call backs), the SLA percent, and the abandon rate. Returns a dict with
    these keys: "answered_voice", "answered_callback", "answered_total",
    "sla_percent", and "abandon_rate_percent".

    How the numbers are read, now that the query groups by media type and
    returns the whole day as one bucket:
      - Answered: the tAnswered count, kept per media type so we can show normal
        calls (voice) and call backs (callback) separately, and also added up
        for the total.
      - Abandon rate: abandoned calls (tAbandon) divided by offered calls
        (nOffered), counting normal inbound calls (voice) only. Call backs are
        left out because we do not hold service-level or abandon targets for
        them, so including them would skew the rate. When no voice calls were
        offered we report 0 so we never divide by zero.
      - SLA percent: worked out from the voice group's counts using Genesys's
        own formula (see compute_service_level_percent), because this endpoint
        does not return a ready-made service level. Call backs are left out for
        the same reason as above.
    """
    query = build_aggregate_query(queue_id)

    try:
        # Genesys API call:
        # AnalyticsApi.post_analytics_conversations_aggregates_query - returns
        # the same-day totals for the queue, grouped by media type.
        response = analytics_api.post_analytics_conversations_aggregates_query(query)
    except ApiException as e:
        raise SystemExit("Could not read same-day queue totals from Genesys Cloud: %s" % e)

    answered_voice = 0
    answered_callback = 0
    offered = 0
    abandoned = 0
    # Start the SLA at 0 and replace it with the real voice value when we find
    # it. We keep it separate from a "found it" flag so a queue with no voice
    # service level still shows 0.0% rather than nothing.
    sla_percent = 0.0

    results = getattr(response, 'results', None) or []
    for data_group in results:
        media_type = get_group_media_type(data_group)
        counts = sum_metric_counts(data_group)

        # Keep the answered count split by call type so the card can show normal
        # calls and call backs on their own. Both types count toward Total
        # Calls, which is why we keep each one here.
        answered_here = counts.get('tAnswered', 0)
        if media_type == MEDIA_TYPE_VOICE:
            answered_voice += answered_here
        elif media_type == MEDIA_TYPE_CALLBACK:
            answered_callback += answered_here

        # The abandon rate and SLA are for normal inbound calls only, so we only
        # read these from the voice group and skip call backs. We do not hold
        # service-level or abandon targets for call backs, so counting them
        # would make both rates misleading.
        if media_type == MEDIA_TYPE_VOICE:
            offered += counts.get('nOffered', 0)
            abandoned += counts.get('tAbandon', 0)

            # Work out the voice service level from the counts. If there is a
            # value, use it; otherwise leave the SLA at 0.0%.
            voice_sla = compute_service_level_percent(counts)
            if voice_sla is not None:
                sla_percent = voice_sla

    answered_total = answered_voice + answered_callback

    # Abandon rate is the share of offered voice calls that were abandoned (call
    # backs are not counted). Guard against no offered calls so we never divide
    # by zero on a quiet morning.
    if offered > 0:
        abandon_rate_percent = (abandoned / offered) * 100
    else:
        abandon_rate_percent = 0.0

    return {
        'answered_voice': answered_voice,
        'answered_callback': answered_callback,
        'answered_total': answered_total,
        'sla_percent': sla_percent,
        'abandon_rate_percent': abandon_rate_percent,
    }


def read_queue_card(analytics_api, title, queue_id):
    """Return all the dashboard numbers for one queue as a single dict.

    Pulls the live numbers and the same-day totals for the queue and gathers
    them, along with the card title, into one flat dict the card drawing uses.
    Returns a dict with these keys: "title", "calls_waiting",
    "callbacks_waiting", "agents_on_calls", "agents_idle", "answered_voice",
    "answered_callback", "answered_total", "sla_percent", and
    "abandon_rate_percent".
    """
    live_numbers = read_live_numbers(analytics_api, queue_id)
    today_totals = read_today_totals(analytics_api, queue_id)

    card = {'title': title}
    card.update(live_numbers)
    card.update(today_totals)
    return card


# --- Helpers: drawing the cards ----------------------------------------------
# These build the side-by-side cards out of plain text so the output looks like
# the dashboard: a title bar, then three rows of two labelled cells each. Each
# cell is half the card wide, so two cells sit next to each other on a line.
CELL_WIDTH = CARD_WIDTH // 2


def center_in(text, width):
    """Return the text centered inside a field of the given width.

    Pads the text with spaces on both sides so it sits in the middle of a field
    that is exactly width characters wide. Used to center the labels and values
    inside each card cell. Long text that does not fit is cut to the width so a
    cell never grows wider than planned and pushes the cards out of line.
    """
    text = str(text)
    if len(text) > width:
        return text[:width]
    return text.center(width)


def build_card_lines(card):
    """Return one queue's card as a list of text lines, all the same width.

    Draws the card the same way the dashboard lays it out: a title bar at the
    top, then three rows, each row holding two cells side by side. Every cell
    has a small label (such as "Calls Waiting") above its value (such as "6").
    Returns the lines as a list so the caller can print several cards next to
    each other, line by line.

    The cells, in the order they appear, are:
      Row 1: Calls Waiting | Callbacks Waiting   (waiting now, split by type)
      Row 2: On Call       | Idle                (agents)
      Row 3: Calls         | Callbacks           (answered today, split by type)
      Row 4: SLA           | Abandon             (voice calls only)

    There is no separate "total answered" cell; add the Calls and Callbacks
    answered cells in row 3 to get the day's total.
    """
    # The percent values get one decimal place and a "%" sign; the counts are
    # whole numbers. We format them into text first so the drawing below only
    # has to place ready-made strings.
    sla_text = "%.1f%%" % card['sla_percent']
    abandon_text = "%.1f%%" % card['abandon_rate_percent']

    # Each row is a pair of (label, value) cells, left cell then right cell. The
    # first row shows what is waiting right now, split into normal calls and
    # call backs; the third row shows what was answered today, split the same
    # way.
    rows = [
        (('Calls Waiting', card['calls_waiting']), ('Callbacks Waiting', card['callbacks_waiting'])),
        (('On Call', card['agents_on_calls']), ('Idle', card['agents_idle'])),
        (('Calls', card['answered_voice']), ('Callbacks', card['answered_callback'])),
        (('SLA', sla_text), ('Abandon', abandon_text)),
    ]

    # The horizontal border lines. The top and bottom use the full card width;
    # the middle divider between rows does too.
    full_border = '+' + ('-' * (CARD_WIDTH - 2)) + '+'

    lines = []
    lines.append(full_border)
    lines.append('|' + center_in(card['title'], CARD_WIDTH - 2) + '|')
    lines.append(full_border)

    for left_cell, right_cell in rows:
        left_label, left_value = left_cell
        right_label, right_value = right_cell

        # A row is three printed lines: the two labels, the two values, then a
        # divider. Each cell is centered in its half of the card.
        label_line = (
            '|' + center_in(left_label, CELL_WIDTH - 2) + '|'
            + center_in(right_label, CELL_WIDTH - 2) + '|'
        )
        value_line = (
            '|' + center_in(left_value, CELL_WIDTH - 2) + '|'
            + center_in(right_value, CELL_WIDTH - 2) + '|'
        )
        lines.append(label_line)
        lines.append(value_line)
        lines.append(full_border)

    return lines


def print_cards_side_by_side(cards):
    """Print the given cards next to each other, like the dashboard rows.

    Builds each card as a block of text lines, then prints them line by line
    with a gap between cards so they sit side by side across the terminal. All
    cards are the same height because every card has the same six cells, so the
    lines stay lined up. Prints to the screen and returns nothing.
    """
    # Build every card's lines first, then print them row by row. Because all
    # cards are the same height, we can walk the line numbers together.
    card_line_blocks = []
    for card in cards:
        card_line_blocks.append(build_card_lines(card))

    gap_between_cards = '   '
    number_of_lines = len(card_line_blocks[0])
    for line_index in range(number_of_lines):
        line_parts = []
        for card_lines in card_line_blocks:
            line_parts.append(card_lines[line_index])
        print(gap_between_cards.join(line_parts))


# --- Main --------------------------------------------------------------------
def main():
    """Read the configured queues and print them as side-by-side cards.

    Step 1: Sign in to Genesys Cloud.
    Step 2: Confirm each configured queue ID is real, so a typo is caught early.
    Step 3: Read the six numbers for each queue (live numbers and same-day
            totals).
    Step 4: Print the queues as side-by-side cards, laid out like the dashboard.
    """
    routing_api, analytics_api = build_apis()

    print("Checking the configured queues...")
    for title, queue_id in DASHBOARD_QUEUES:
        confirm_queue_exists(routing_api, title, queue_id)

    print("Reading live and same-day stats...")
    cards = []
    for title, queue_id in DASHBOARD_QUEUES:
        cards.append(read_queue_card(analytics_api, title, queue_id))

    # Show the time the numbers were read, in the local time zone, so anyone
    # looking at the output knows how fresh it is.
    read_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print()
    print("Service Desk Live Queue Dashboard  (as of %s local time)" % read_at)
    print()
    print_cards_side_by_side(cards)
    print()
    print("Done.")


if __name__ == '__main__':
    main()
