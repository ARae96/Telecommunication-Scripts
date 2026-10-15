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
import re
import os

os.environ['GENESYS_CLOUD_CLIENT_ID'] = '
os.environ['GENESYS_CLOUD_CLIENT_SECRET'] = 
os.environ['GENESYS_CLOUD_REGION'] = 'us_east_1'  # eg. us_east_1
CLIENT_ID = os.environ['GENESYS_CLOUD_CLIENT_ID']
CLIENT_SECRET = os.environ['GENESYS_CLOUD_CLIENT_SECRET']
ORG_REGION = os.environ['GENESYS_CLOUD_REGION']  # eg. us_east_1
apiclient = PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(CLIENT_ID, CLIENT_SECRET)


temp_file_aggregate = "validationerror.csv"

userslist = []
notmatch = []
file =  "/Users/meg.luong/Downloads/gc1127.csv"


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


class Person:
  def __init__(self, email, phone, ext):
    self.email = email
    self.phone = phone
    self.ext = ext
    self.version = "0"
    self.id = ""
    self.validation = False
  def reformatphone(self):

      newphone = re.sub("[^0-9]", "", self.phone)
      newphone = "+1" + str(newphone)
      self.phone =  newphone
      print(self.phone)
      
 
        
  def validateInfo(self):
        # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.UsersApi()
    search_api = PureCloudPlatformClientV2.SearchApi()
        # create body
    query = PureCloudPlatformClientV2.UserSearchCriteria()
    query.type = 'EXACT'
    query.value = self.email
    query.fields = ['email']
    query.operator = 'AND'

    body = PureCloudPlatformClientV2.UserSearchRequest() 
    body.sort_order = 'DESC'
    body.types = ['USERS']
    body.query = [query]

    try:
            # Search users
            api_response = api_instance.post_users_search(body)
            self.version = api_response.results[0].version
            self.id = api_response.results[0].id
            addresses = api_response.results[0].addresses
            if len(addresses) < 2: 
                print("missing number or extension")
                return
            elif addresses[0].address != self.phone:
                print("Phone does not match")
                return
            elif addresses[1].extension != self.ext or addresses[1].display != self.ext:
                print("ext does not match")
                return

            else : 
                print("Validation complete, users number successfully assigned")
                self.validation = True
    except ApiException as e:
        print("WAKAWAKA")
        output = e.body
        error = str(self.email) + ',' + str(output)+ '\n'
        temp_file_aggregate = "validationerror.csv"
        with open(temp_file_aggregate, 'a') as f:
            f.write(error)
        print("Exception when calling UsersApi->user_search_request: %s\n" % e)
        return
  def pushphone(self):

    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.UsersApi()
    user_id = self.id # str | User ID
    body = PureCloudPlatformClientV2.UpdateUser() # UpdateUser | User
    body.version = self.version
    body.addresses = [PureCloudPlatformClientV2.Contact()]
    body.addresses[0].address = self.phone
    body.addresses[0].media_type = "PHONE"
    body.addresses[0].type = "WORK"
    body.addresses[0].country_code = "US"
    extension = [PureCloudPlatformClientV2.Contact()]
    extension[0].extension = self.ext
    extension[0].media_type = "PHONE"
    extension[0].type = "WORK2"
    body.addresses.extend(extension)
    try:
        # Update user
        api_response = api_instance.patch_user(user_id, body)
        print('Successfully updated user, reevaluating changes for ' + str(self.email))
        self.validateInfo()
        while self.validation == False: 
            
            api_response = api_instance.patch_user(user_id, body)
            self.validateInfo()
    except ApiException as e:
        print("Exception when calling UsersApi->patch_user: %s\n" % e)

def do_sync(args):
    '''
    gets the token to be used
    
    '''
    logger.info("Starting Sync")
    config = {
    "domain": "mypurecloud.com",
    "client_id": "2a736644-4bcb-40db-ae97-321d78bdf8e8",
    "client_secret": "PDXaxz0GCWDJogk2Z6NQre_5T9b9DuFA5vVpICK9D9I"
    }
    
    logger.info("Getting access token")
    access_token = get_access_token(config)

    api_host = 'https://api.{domain}'.format(domain=config['domain'])

    PureCloudPlatformClientV2.configuration.host = api_host
    PureCloudPlatformClientV2.configuration.access_token = access_token
    handler(config)
#main function 


def handler(config):
    
    with open(file) as file_obj:
        csvreader_object=csv.reader(file_obj)
        # The line will skip the first row of the csv file (Header row)
        next(csvreader_object)  
        reader_obj = csv.reader(file_obj)
        for row in reader_obj:
            if row[2] == "":
                continue
            else:
                user = Person(row[1],row[2],row[3])
                userslist.append(user)
                if user.phone == "": 
                    continue
                else:
                    print(user.email)
                    user.reformatphone()
                    user.validateInfo()
       
        for user in userslist:
            if user.validation == False:
                print("Phone mismatch, pushing update to user")
                user.pushphone()
            else: 
                continue
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