# =============================================================================
# Genesys Cloud - Users Who Have Never Logged In
# =============================================================================
# Reads every user in Genesys Cloud and finds the ones who have never logged
# in. A user who has never logged in has no last login date, so Genesys returns
# that date as empty (None). The script counts those users, works out what
# share they are of the whole user list, and then breaks that count down by
# division and by license type.
#
# This is a read-only report. It does not change anything in Genesys Cloud.
#
# What it prints:
#   1. How many users have never logged in (last login is empty).
#   2. What percent that is of the total users the script read.
#   3. A per-division count of the never-logged-in users, so you can see which
#      divisions they fall under.
#   4. A per-license-type count of the never-logged-in users. A license type is
#      the Genesys product a user is licensed for (for example "communicate" or
#      "cloudCX3").
#
#      Three of the licenses (collaboratePro, communicate, cloudCX3) are tiers
#      of the same product, and a user is only billed for the highest tier they
#      hold. So a user who holds more than one of those three is counted once,
#      under the highest tier they hold. Any other license is counted on its
#      own on top of that. A user can still land under more than one license
#      (their highest tier plus other licenses), so the counts can add up to
#      more than the number of never-logged-in users.
#
# A note on which users are counted: by default this script reads users who are
# "active" and "inactive", because those are the real people in the org. It
# leaves out "deleted" users on purpose, since counting removed accounts would
# make the "never logged in" share look worse than it really is. You can change
# this with USER_STATES below.
#
# Run locally with:
#   pip install -r requirements.txt
# and a populated .env (GENESYS_CLOUD_CLIENT_ID / GENESYS_CLOUD_CLIENT_SECRET).
# =============================================================================


# --- Imports -----------------------------------------------------------------

from PureCloudPlatformClientV2.rest import ApiException

from genesys_common import build_apis, get_all_users, split_into_batches


# --- Configuration -----------------------------------------------------------
# Which user states to include in the report. Genesys can return users in three
# states: "active" (current employees who can sign in), "inactive" (accounts
# turned off but not removed), and "deleted" (removed accounts). We read active
# and inactive by default because they are the real people in the org. Add
# "deleted" here only if you truly want removed accounts in the counts.
USER_STATES = ['active']

# We ask Genesys to send two extra fields that are not part of the basic user
# record: the last login date and the division. We have to request these by
# name here or Genesys leaves them empty. This matters a lot for the last login
# date: without asking for it, every user comes back with an empty date and the
# report would wrongly say that 100% of users never logged in.
EXPAND_FIELDS = ['dateLastLogin', 'division']

# The label we use in the per-division breakdown when a user has no division on
# their record. This keeps those users visible in the report instead of being
# dropped.
NO_DIVISION_LABEL = '(no division)'

# How many user IDs to ask about in a single license lookup. The license
# lookup takes a list of user IDs and returns the licenses for each one. We ask
# in batches so we are not sending thousands of IDs in one request. This
# endpoint is documented to take at most 100 IDs per request, so do not set
# this above 100.
LICENSE_BATCH_SIZE = 100

# The label we use in the per-license-type breakdown when a user holds no
# license at all. This keeps those users visible in the report instead of being
# dropped.
NO_LICENSE_LABEL = '(no license)'

# These three licenses are tiers of the same product, so a user who holds more
# than one of them is only billed for the highest tier. We count them the same
# way: a user who holds several of these is counted once, under the highest
# tier they hold, and their lower tiers are not counted. This list is ordered
# from the cheapest (lowest) tier to the most expensive (highest) tier, so the
# last one a user holds in this list is the one we count.
#
# Any license not in this list is not a tier. Those are counted on their own,
# as normal, on top of whatever tier the user holds.
TIERED_LICENSES_LOW_TO_HIGH = ['collaboratePro', 'communicate', 'cloudCX3']


# --- Helpers -----------------------------------------------------------------
def has_never_logged_in(user):
    """Return True when a user has never logged in to Genesys Cloud.

    A user who has never signed in has no last login date, so Genesys leaves
    the dateLastLogin field empty (None). We read that field safely with
    getattr in case a record does not include it at all, and treat a missing or
    empty date as "never logged in".
    """
    return getattr(user, 'date_last_login', None) is None


def get_division_name(user):
    """Return the name of a user's division, or a clear fallback label.

    The division comes back as a small object with a name on it. Some users may
    have no division set, so we fall back to a plain "(no division)" label
    instead of dropping them. That way every never-logged-in user shows up
    somewhere in the per-division breakdown.
    """
    division = getattr(user, 'division', None)
    if division is None:
        return NO_DIVISION_LABEL

    return getattr(division, 'name', None) or NO_DIVISION_LABEL


def count_never_logged_in_by_division(users):
    """Return how many never-logged-in users fall under each division.

    Walks the users who have never logged in and tallies them up by division
    name. Returns a dict that maps each division name to its count. A user with
    no division is counted under the "(no division)" label so they are still
    shown.
    """
    counts = {}
    for user in users:
        division_name = get_division_name(user)
        # Start a division at 0 the first time we see it, then add one for this
        # user. This gives us a running count per division.
        counts[division_name] = counts.get(division_name, 0) + 1
    return counts


def get_licenses_by_user_id(license_api, user_ids):
    """Return a map from user ID to that user's list of license names.

    Asks Genesys which licenses each user holds. The lookup takes a list of
    user IDs and sends back a map from each user ID to a list of license-type
    names (for example ["cloudCX3"] or ["agentCopilotLicense", "cloudCX3"]). A
    user can hold more than one license, and some users hold none, so the list
    can be empty.

    We ask in batches of at most 100 IDs because that is the most this lookup
    takes in one request. If one batch fails we print the error and keep going
    with the next batch, so one bad batch does not throw away the whole run.
    Returns one combined map across all the batches.
    """
    licenses_by_user_id = {}
    batches = split_into_batches(user_ids, LICENSE_BATCH_SIZE)

    for batch_number, batch in enumerate(batches, start=1):
        try:
            # Genesys API call: LicenseApi.post_license_users - takes a list of
            # user IDs and returns a map from each user ID to its licenses.
            response = license_api.post_license_users(body=batch)
        except ApiException as e:
            print("Exception when calling LicenseApi->post_license_users: %s\n" % e)
            # Skip this batch's users on an error, but keep the batches we
            # already have so one bad batch does not lose everything.
            continue

        # The response is a plain map from user ID to a list of license names.
        # We merge each batch's map into the combined map we return.
        for user_id, license_names in (response or {}).items():
            licenses_by_user_id[user_id] = license_names or []

    return licenses_by_user_id


def get_highest_tier(license_names):
    """Return the highest tier a user holds, or None if they hold no tier.

    Three of the licenses (collaboratePro, communicate, cloudCX3) are tiers of
    the same product, and a user is only billed for the highest one they hold.
    This looks through the user's licenses and returns the most expensive tier
    they hold, based on the order in TIERED_LICENSES_LOW_TO_HIGH. Returns None
    when the user holds none of the three tiers, so the caller knows there is
    no tier to count.
    """
    highest_tier = None
    highest_rank = -1

    for license_name in license_names:
        # Skip any license that is not one of the three tiers. Its rank would
        # be -1 (not found), so this also guards against a false match.
        if license_name not in TIERED_LICENSES_LOW_TO_HIGH:
            continue

        # The tier's position in the low-to-high list is its rank. A bigger
        # position means a more expensive tier, so we keep the one with the
        # biggest position.
        rank = TIERED_LICENSES_LOW_TO_HIGH.index(license_name)
        if rank > highest_rank:
            highest_rank = rank
            highest_tier = license_name

    return highest_tier


def get_billable_licenses(license_names):
    """Return the licenses to count for a user, after collapsing the tiers.

    A user is billed for only the highest of the three tiers they hold, so we
    drop their lower tiers before counting. Every license that is not a tier is
    kept as-is, because those are billed on their own on top of the tier.

    Returns a list that holds the user's one highest tier (if they hold any
    tier) plus all of their non-tier licenses. For example a user with
    communicate, cloudCX3, and salesforceClient comes back as cloudCX3 (their
    highest tier) plus salesforceClient.
    """
    billable = []

    # Keep the single highest tier, if the user holds any of the three tiers.
    highest_tier = get_highest_tier(license_names)
    if highest_tier is not None:
        billable.append(highest_tier)

    # Keep every non-tier license as-is. These are separate charges, so they
    # are counted on their own and are not affected by the tier collapse.
    for license_name in license_names:
        if license_name not in TIERED_LICENSES_LOW_TO_HIGH:
            billable.append(license_name)

    return billable


def count_users_by_license_type(users, licenses_by_user_id):
    """Return how many of the given users hold each billable license type.

    Walks the users and tallies them up by license-type name, using the
    user-ID-to-licenses map we read earlier. Before counting, we collapse the
    three tiers (collaboratePro, communicate, cloudCX3) down to the single
    highest tier each user holds, because a user is only billed for their
    highest tier. Non-tier licenses are counted on their own, on top of the
    tier.

    A user can still land under more than one license (their highest tier plus
    any non-tier licenses), so the counts can add up to more than the number of
    users. A user who holds no license (or whose licenses we could not read) is
    counted once under the "(no license)" label so they still show up. Returns
    a dict that maps each license type to its count.
    """
    counts = {}
    for user in users:
        user_id = getattr(user, 'id', None)
        held_licenses = licenses_by_user_id.get(user_id, [])

        # Collapse the three tiers down to the one highest tier the user holds,
        # and keep their non-tier licenses. This is the set we actually count.
        billable_licenses = get_billable_licenses(held_licenses)

        # A user with no license still matters, so count them under a clear
        # fallback label instead of dropping them from the report.
        if not billable_licenses:
            counts[NO_LICENSE_LABEL] = counts.get(NO_LICENSE_LABEL, 0) + 1
            continue

        # Count the user once under each billable license. After the tier
        # collapse this is at most one tier plus their non-tier licenses.
        for license_name in billable_licenses:
            counts[license_name] = counts.get(license_name, 0) + 1

    return counts


# --- Main --------------------------------------------------------------------
def main():
    """Read all users and report who has never logged in to Genesys Cloud.

    Step 1: Sign in to Genesys Cloud.
    Step 2: Read every user in the states we care about, with their division.
    Step 3: Stop if no users came back, so we do not divide by zero later.
    Step 4: Pick out the users whose last login date is empty (never logged in).
    Step 5: Look up which license each never-logged-in user holds.
    Step 6: Print the count, the percent of all users, a per-division breakdown,
            and a per-license-type breakdown of the never-logged-in users.
    """
    users_api, license_api = build_apis('UsersApi', 'LicenseApi')

    print("Reading users from Genesys Cloud (states: %s)..." % ", ".join(USER_STATES))
    all_users = get_all_users(users_api, USER_STATES, EXPAND_FIELDS)

    total_users = len(all_users)

    # Stop if we read no users at all. This usually means every page read
    # failed or the states returned nobody. Going further would divide by zero
    # when working out the percent, so we stop with a clear message instead.
    if total_users == 0:
        raise SystemExit(
            "No users were read from Genesys Cloud, so there is nothing to "
            "report. Check the reads above did not fail and that USER_STATES "
            "is set to states that have users."
        )

    # Keep only the users who have never logged in. We reuse this list for both
    # the overall count and the per-division breakdown.
    never_logged_in_users = []
    for user in all_users:
        if has_never_logged_in(user):
            never_logged_in_users.append(user)

    never_logged_in_count = len(never_logged_in_users)

    # Work out the share as a percent. We already made sure total_users is not
    # zero above, so this is safe to divide.
    never_logged_in_percent = (never_logged_in_count / total_users) * 100

    print()
    print("Total users read: %d" % total_users)
    print("Users who have never logged in: %d" % never_logged_in_count)
    print(
        "That is %.1f%% of all users read."
        % never_logged_in_percent
    )

    print()
    print("Never-logged-in users per division:")
    division_counts = count_never_logged_in_by_division(never_logged_in_users)

    # Show the divisions with the most never-logged-in users first, so the
    # biggest gaps are easy to spot at the top of the list.
    sorted_divisions = sorted(
        division_counts.items(), key=lambda pair: pair[1], reverse=True
    )
    for division_name, count in sorted_divisions:
        print("  %s: %d" % (division_name, count))

    # Look up the license each never-logged-in user holds, then break the count
    # down by license type. We only look up the never-logged-in users, not
    # everyone, so this stays quick.
    print()
    print("Reading licenses for the %d users..."
          % never_logged_in_count
        )
    never_logged_in_ids = []
    for user in never_logged_in_users:
        user_id = getattr(user, 'id', None)
        if user_id:
            never_logged_in_ids.append(user_id)

    licenses_by_user_id = get_licenses_by_user_id(license_api, never_logged_in_ids)
    license_counts = count_users_by_license_type(
        never_logged_in_users, licenses_by_user_id
    )

    print()
    print(
        "  (A user can still hold other licenses too, so these can add up to "
        "more than %d.)" % never_logged_in_count
    )

    # Show the license types with the most never-logged-in users first, so the
    # biggest groups are easy to spot at the top of the list.
    sorted_licenses = sorted(
        license_counts.items(), key=lambda pair: pair[1], reverse=True
    )
    for license_name, count in sorted_licenses:
        print("  %s: %d" % (license_name, count))

    print()
    print("Done.")


if __name__ == '__main__':
    main()