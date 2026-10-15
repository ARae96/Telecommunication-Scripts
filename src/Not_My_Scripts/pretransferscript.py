import base64
import argparse
import pandas as pd
import pandas.io.sql as sqlio
from csv import reader
from io import StringIO
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
import datetime
import logging
import requests
import backoff
import csv


temp_file_aggregate = "phoneimport_error_log1.csv"

userslist = []
temp_file = 'webrtc_imports.csv'
#WEBRTC Imports CSV Location HERE, columns must be  name|base|site|email
file =  "/Users/meg.luong/Downloads/transfers1127.csv"


logger = logging.getLogger()

HTTP_SUCCESS = 200
HTTP_RATE_LIMIT_ERROR = 429
HTTP_NOT_FOUND = 404
API_RETRY_INTERVAL_SECONDS = 30
API_RETRY_COUNT = 5
BASE_PURECLOUD_AUTH_HOST = 'https://login.{domain}'
BASE_PURECLOUD_API_HOST = 'https://api.{domain}'

def get_access_token(config):
    "Returns an access_token for the client credentials, or raises if unauthorized"

    client_id = config['client_id']
    client_secret = config['client_secret']
    client_domain = config['domain']

    auth_host = BASE_PURECLOUD_AUTH_HOST.format(domain=client_domain)
    auth_endpoint = '{}/oauth/token'.format(auth_host)

    client_creds = "{}:{}".format(client_id, client_secret).encode('utf-8')
    raw_authorization = base64.b64encode(client_creds)
    authorization = raw_authorization.decode('ascii')

    body = {'grant_type': 'client_credentials'}

    headers = {
        'Authorization': 'Basic {}'.format(authorization),
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    response = requests.post(auth_endpoint, data=body, headers=headers)

    if response.status_code == HTTP_SUCCESS:
        response_json = response.json()
        return response_json['access_token']
    else:
        logger.fatal(response.json())
        raise RuntimeError("Unauthorized")

def giveup(error):
    logger.warning("Encountered an error while syncing")
    
    logger.error(error)
    
    is_api_error = hasattr(error, 'status')
    is_rate_limit_error = error.status == HTTP_RATE_LIMIT_ERROR
    
    logger.debug("Is API Error? {}. Is Rate Limit Error? {}.".format(is_api_error, is_rate_limit_error))

    #  return true if we should *not* retry
    
    should_retry = is_api_error and is_rate_limit_error
    return not should_retry

@backoff.on_exception(backoff.constant,
                      PureCloudPlatformClientV2.rest.ApiException,
                      jitter=backoff.random_jitter,
                      max_tries=API_RETRY_COUNT,
                      giveup=giveup,
                      interval=API_RETRY_INTERVAL_SECONDS)


###
### add functions here
###


#Role class object that stores role and division ID into object


def getUserID(email):
        # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.UsersApi()
    search_api = PureCloudPlatformClientV2.SearchApi()
        # create body
    query = PureCloudPlatformClientV2.UserSearchCriteria()
    query.type = 'EXACT'
    query.value = email
    query.fields = ['email']
    query.operator = 'AND'

    body = PureCloudPlatformClientV2.UserSearchRequest() 
    body.sort_order = 'DESC'
    body.types = ['USERS']
    body.query = [query]
    print(body)
    try:
            # Search users
            api_response = api_instance.post_users_search(body)
            print(api_response)
            id = api_response.results[0].id
            return id
    except ApiException as e:
        output = e.body
        error = str(email) + ',' + str(output)+ '\n'
        temp_file_aggregate = "phoneimport_error_log1.csv"
        with open(temp_file_aggregate, 'a') as f:
            f.write(error)
        print("Exception when calling UsersApi->user_search_request: %s\n" % e)
        return
def clearRoles(id):

    #Removes all of user's previous roles with the exception of Employee - Home
    api_instance = PureCloudPlatformClientV2.AuthorizationApi()
    subject_id = id# str | Subject ID (user or group)
    body = PureCloudPlatformClientV2.RoleDivisionGrants() # RoleDivisionGrants | Pairs of role and division IDs
    subject_type = "PC_USER" # str | what the type of the subject is (PC_GROUP, PC_USER or PC_OAUTH_CLIENT) (optional) (default to 'PC_USER')
    body.grants = [PureCloudPlatformClientV2.RoleDivisionPair()]
    body.grants[0].role_id = "4ab1c48a-5a6b-4962-a661-f5b4053cdbfe"
    body.grants[0].division_id = "df1b7ef4-744c-4b47-8aad-9dc6b2ecb9e0"


    try:
        # Replace subject's roles and divisions with the exact list supplied in the request.
        api_instance.post_authorization_subject_bulkreplace(subject_id, body, subject_type=subject_type)
    except ApiException as e:
        print("Exception when calling AuthorizationApi->post_authorization_subject_bulkreplace: %s\n" % e)

def removeQueues(id):

    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.UsersApi()
    user_id = id # str | User ID
    page_size = 100 # int | Page size (optional) (default to 25)
    page_number = 1 # int | Page number (optional) (default to 1)

    try:
        # Get queues for user
        api_response = api_instance.get_user_queues(user_id, page_size=page_size, page_number=page_number)
        api_instance = PureCloudPlatformClientV2.RoutingApi()
        queues = api_response.entities
        for i in queues:
            api_response = api_instance.delete_routing_queue_member(i.id, id)

    except ApiException as e:
        print("Exception when calling UsersApi->get_user_queues: %s\n" % e)

def do_sync(args):
    '''
    gets the token to be used
    
    '''
    logger.info("Starting Sync")
    config = {
    "domain": "mypurecloud.com",
    "client_id": ,
    "client_secret": 
    }
    
    logger.info("Getting access token")
    access_token = get_access_token(config)

    api_host = 'https://api.{domain}'.format(domain=config['domain'])

    PureCloudPlatformClientV2.configuration.host = api_host
    PureCloudPlatformClientV2.configuration.access_token = access_token
    pandas_handler()
    handler(config)
#main function 

def pandas_handler():
    df = pd.read_csv(file)
    df = df.drop(df.iloc[:, 4:], axis=1)
    df.to_csv(temp_file, index=False)
    print("Temp file agg",temp_file)
    print(df)

def handler(config):
    
    with open(file) as file_obj:
        csvreader_object=csv.reader(file_obj)
        # The line will skip the first row of the csv file (Header row)
        next(csvreader_object)  
        reader_obj = csv.reader(file_obj)
        for row in reader_obj:
            userslist.append(row[1])

    for i in userslist:
        print("Clearing roles, queues, and skilling for " + str(i))
        id = getUserID(i)
        print(id)
        clearRoles(id)
        removeQueues(id)
    

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