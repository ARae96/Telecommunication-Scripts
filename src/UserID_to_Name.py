# =============================================================================
# Genesys Cloud - Look Up User Names From User IDs
# =============================================================================
# Signs in to Genesys Cloud and turns a list of user IDs into names. You paste
# the IDs you want into USER_IDS below, run the script, and it prints each ID
# next to the name Genesys has on file. Another report or export sometimes
# gives you only the long user ID. This turns that ID into the real person's
# name.
#
# The script only reads data. It never changes anything in Genesys.
#
# Local runs need `pip install -r requirements.txt` and a populated .env with
# GENESYS_CLOUD_CLIENT_ID and GENESYS_CLOUD_CLIENT_SECRET.
# =============================================================================

# --- Imports -----------------------------------------------------------------
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint

from genesys_common import build_apis


# --- Configuration -----------------------------------------------------------

# The user IDs you want names for. Add or replace the IDs in this list by hand.
USER_IDS = ['aee893dc-20c1-40b3-a6ec-e473c34b2c3e']



# --- Helpers -----------------------------------------------------------------

def get_name(user_api, user_id):
    """Return the name for one user ID, or None if the lookup fails.

    Calls the Genesys Cloud "get user" endpoint for a single ID. If that ID is
    bad or the call fails, it prints a message and returns None so one bad ID
    does not stop the whole run.
    """
    try:
        # get_user takes a single user ID and returns one user object.
        response = user_api.get_user(user_id)
        return response.name
    except ApiException as e:
        print("Exception when calling UsersApi->get_user for %s: %s" % (user_id, e))
        return None


# --- Main --------------------------------------------------------------------

def main():
    # Sign in and get the Users API client.
    user_api = build_apis('UsersApi')

    # Look up each ID one at a time and collect the ID/name pairs.
    results = []
    for user_id in USER_IDS:
        name = get_name(user_api, user_id)
        results.append((user_id, name))

    # Print the ID/name pairs so you can copy them into your report.
    pprint(results)


if __name__ == '__main__':
    main()
