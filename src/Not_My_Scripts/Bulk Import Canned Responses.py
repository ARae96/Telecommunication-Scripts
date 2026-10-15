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


#Reads CSV and creates a dictionary with key:value pair being title:canned response
def createDict():
    dict = {}
    df = pd.read_csv('/Users/meg.luong/Desktop/admissions.csv')
    for i in range(len(df)):
        title = df.values[i][0]
        response = df.values[i][1]
        dict[title] = response
    return dict



def createResponse(dictionary):
    for k, v in dictionary.items():
        key = k
        value  = v
        api_instance = PureCloudPlatformClientV2.ResponseManagementApi()
        body = PureCloudPlatformClientV2.Response() # Response | Respons
        body.name = key
        library = [PureCloudPlatformClientV2.DomainEntityRef()]
        library[0].id = "2551ec14-e712-4768-852b-b1b86789e6ae"
        text = [PureCloudPlatformClientV2.ResponseText()]
        text[0].content = value
        body.libraries = library
        body.texts = text


        try:
            # Create a response.
            api_response = api_instance.post_responsemanagement_responses(body)
            pprint(api_response)
        except ApiException as e:
            print("Exception when calling ResponseManagementApi->post_responsemanagement_responses: %s\n" % e)

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
    
    handler(config)
#main function 

def handler(config):
    dictionary = createDict()
    createResponse(dictionary)
    

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
