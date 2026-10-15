from __future__ import division
import base64
import argparse
from distutils.command.config import config
from http.client import HTTP_VERSION_NOT_SUPPORTED
import pandas as pd
import pandas.io.sql as sqlio

# import psycopg2
from csv import reader
from io import StringIO
import time
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
import os
import re
import datetime
from datetime import timedelta
from email.utils import formataddr
import logging
import requests
import backoff
from dotenv import load_dotenv


load_dotenv()

# CC DELETION

# intialize variables
logger = logging.getLogger()

convoids = []


HTTP_SUCCESS = 200
HTTP_RATE_LIMIT_ERROR = 429
HTTP_NOT_FOUND = 404
API_RETRY_INTERVAL_SECONDS = 30
API_RETRY_COUNT = 5
BASE_PURECLOUD_AUTH_HOST = "https://login.{domain}"
BASE_PURECLOUD_API_HOST = "https://api.{domain}"


def get_access_token(config):
    "Returns an access_token for the client credentials, or raises if unauthorized"

    client_id = config["client_id"]
    client_secret = config["client_secret"]
    client_domain = config["domain"]

    auth_host = BASE_PURECLOUD_AUTH_HOST.format(domain=client_domain)
    auth_endpoint = "{}/oauth/token".format(auth_host)

    client_creds = "{}:{}".format(client_id, client_secret).encode("utf-8")
    raw_authorization = base64.b64encode(client_creds)
    authorization = raw_authorization.decode("ascii")

    body = {"grant_type": "client_credentials"}

    headers = {
        "Authorization": "Basic {}".format(authorization),
        "Content-Type": "application/x-www-form-urlencoded",
    }

    response = requests.post(auth_endpoint, data=body, headers=headers)

    if response.status_code == HTTP_SUCCESS:
        response_json = response.json()
        return response_json["access_token"]
    else:
        logger.fatal(response.json())
        raise RuntimeError("Unauthorized")


def giveup(error):
    logger.warning("Encountered an error while syncing")

    logger.error(error)

    is_api_error = hasattr(error, "status")
    is_rate_limit_error = error.status == HTTP_RATE_LIMIT_ERROR

    logger.debug(
        "Is API Error? {}. Is Rate Limit Error? {}.".format(
            is_api_error, is_rate_limit_error
        )
    )

    #  return true if we should *not* retry

    should_retry = is_api_error and is_rate_limit_error
    return not should_retry


@backoff.on_exception(
    backoff.constant,
    PureCloudPlatformClientV2.rest.ApiException,
    jitter=backoff.random_jitter,
    max_tries=API_RETRY_COUNT,
    giveup=giveup,
    interval=API_RETRY_INTERVAL_SECONDS,
)

# function that connects to postgres and looks for divisions with 'PM' or 'CI' in their name. Grabs their IDs and puts them in a list, Returns divisionlist


# Function that checks if a recording exists for a specific conversation
def disconnect_interactions(conversationID):
    api_instance = PureCloudPlatformClientV2.ConversationsApi()
    conversation_id = conversationID  # str | Conversation ID

    try:
        # Get all of a Conversation's Recordings.
        api_response = api_instance.post_conversation_disconnect(conversation_id)
        for i in api_response:
            print("{} successfully disconnected {} ".format(conversation_id, i))
        return
    except ApiException as error:
        if error.reason:
            print(error.reason)
            return
        else:
            giveup(error)
            return


# function that querys conversation details, filters out the following : DivisionID, Outbound, and Voice media. Conversation IDs that match filter will be appended to the convoids list
result_waiting = []


def get_waiting_interactions(config):

    logger.info("Fetching waiting interactions")
    api_instance = PureCloudPlatformClientV2.AnalyticsApi()
    body = PureCloudPlatformClientV2.QueueObservationQuery()
    body = {
        "filter": {
            "type": "and",
            "predicates": [
                {
                    "type": "dimension",
                    "dimension": "mediaType",
                    "operator": "matches",
                    "value": "email",
                },
                {
                    "type": "dimension",
                    "dimension": "queueId",
                    "operator": "matches",
                    "value": "b75e16f3-4cf7-42f5-8dd0-dadb95638146",
                    # b60d8687-1459-4806-a1c1-8996b94521ce
                },
            ],
        },
        "metrics": ["oWaiting"],
        "detailMetrics": ["oWaiting"],
    }
    try:
        api_response = api_instance.post_analytics_queues_observations_query(body)
        print(api_response)
        result = api_response.results[0].data
        result_waiting = result[0].observations
        # print(result_waiting)
        count = 0
        if result_waiting == None:
            return
        else:

            for i in result_waiting:
                conv = result_waiting[count].conversation_id
                count += 1
                print(conv)
                if conv in convoids:
                    continue
                else:
                    convoids.append(conv)

    except ApiException as error:
        if error.reason == "Not Found":
            print("No conversations found")
            return
        else:
            giveup(error)
            return


def do_sync(args):
    logger.info("Starting Sync")
    config = {
        "domain": "mypurecloud.com",
        "client_id": f"{os.environ["CLIENTID"]}",
        "client_secret": f"{os.environ["CLIENTSECRET"]}",
    }

    logger.info("Getting access token")
    access_token = get_access_token(config)

    api_host = "https://api.{domain}".format(domain=config["domain"])

    PureCloudPlatformClientV2.configuration.host = api_host
    PureCloudPlatformClientV2.configuration.access_token = access_token

    handler(config)


# main function


def handler(config):

    get_waiting_interactions(config)
    print(convoids)

    # retrieve DNIS values from each conversation, converts them into (###) ###-#### format

    for c in convoids:
        index = int(convoids.index(c)) + 1
        print(
            "Disconnecting interaction " + str(index) + " out of " + str(len(convoids))
        )
        disconnect_interactions(c)


def main():
    parser = argparse.ArgumentParser()

    args = parser.parse_args()

    try:
        do_sync(args)
    except RuntimeError:
        logger.fatal("Run failed.")
        exit(1)


if __name__ == "__main__":
    main()
