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
import time


temp_file_aggregate = "phoneimport_error_log1.csv"

userslist = []
temp_file = 'webrtc_imports.csv'
#WEBRTC Imports CSV Location HERE, columns must be  name|base|site|email
file =  "/Users/meg.luong/Downloads/webrtc11272.csv"


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
class WebRTCIMPORTS:
    def __init__(self, webRTCName,base, site, email):
       self.webRTCName= webRTCName
       self.base = base
       self.site = site
       self.email = email

    def getUserID(self):
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
                print(api_response)
                id = api_response.results[0].id
                
                return id
        except ApiException as e:
            output = e.body
            error = str(self.email) + ',' + str(output)+ '\n'
            temp_file_aggregate = "phoneimport_error_log1.csv"
            with open(temp_file_aggregate, 'a') as f:
                f.write(error)
            print("Exception when calling UsersApi->user_search_request: %s\n" % e)
            return

    def createPhone(self):
        # create an instance of the API class
        api_instance = PureCloudPlatformClientV2.TelephonyProvidersEdgeApi()
        body = PureCloudPlatformClientV2.Phone() # Phone | Phone
        body.name = self.webRTCName
        site = PureCloudPlatformClientV2.DomainEntityRef()
        site.id = "728d307e-87cb-4771-bf66-53f20e521c72"
        body.site = site
        phoneBaseSettings = PureCloudPlatformClientV2.DomainEntityRef()
        phoneBaseSettings.id = "3be35670-f833-47b0-980d-c7aeaa2bdd6e"
        body.phone_base_settings = phoneBaseSettings
        webrtcUser = PureCloudPlatformClientV2.DomainEntityRef()
        webrtcUser.id = self.getUserID()
        body.web_rtc_user = webrtcUser
        lines = PureCloudPlatformClientV2.Line()
        lineBaseSettings = PureCloudPlatformClientV2.DomainEntityRef()
        lineBaseSettings.id = "ae0a1ac2-dab9-47f2-8d06-2273fe91bf63"
        lines.line_base_settings =lineBaseSettings
        body.lines= [lines]
        try:
            api_response = api_instance.post_telephony_providers_edges_phones(body)
            print(self.webRTCName + " created for user")
            time.sleep(5)
            self.assignWebRTC(api_response.lines[0].id)
        except ApiException as e:
            output = e.body
            error = str(self.email) + ',' + str(output)+ '\n'
            temp_file_aggregate = "phoneimport_error_log1.csv"
            with open(temp_file_aggregate, 'a') as f:
                f.write(error)
            print("Exception when calling TelephonyProvidersEdgeApi->post_telephony_providers_edges_phones: %s\n" % e)
            return
            

    def assignWebRTC(self,stationID):
        api_instance = PureCloudPlatformClientV2.UsersApi()
        user_id = self.getUserID() # str | User ID
        station_id = stationID# str | stationId
        try:
            # Set default station
            api_instance.put_user_station_defaultstation_station_id(user_id, station_id)
            print(self.webRTCName + " assigned to " + self.email + " successfully") 
            return
        except ApiException as e:
            output = e.body
            error = str(self.email) + ',' + str(output)+ '\n'
            temp_file_aggregate = "phoneimport_error_log1.csv"
            with open(temp_file_aggregate, 'a') as f:
                f.write(error)
            print("Exception when calling UsersApi->put_user_station_defaultstation_station_id: %s\n" % e)
            return
        # Open file 

    def findStation(self):
        api_instance = PureCloudPlatformClientV2.StationsApi()
        page_size = 25 # int | Page size (optional) (default to 25)
        page_number = 1 # int | Page number (optional) (default to 1)
        name = self.webRTCName # str | Name (optional)

        try:
            print("Already assigned")
            # Get the list of available stations.
            #api_response = api_instance.get_stations(page_size=page_size, page_number=page_number, name=name)
            #self.assignWebRTC(api_response.entities[0].id)
        except ApiException as e:
            output = e.body
            error = str(self.email) + ',' + str(output)+ '\n'
            temp_file_aggregate = "phoneimport_error_log1.csv"
            with open(temp_file_aggregate, 'a') as f:
                f.write(error)
            print("Exception when calling StationsApi->get_stations: %s\n" % e)
            return

    def existingPhone(self):
        # create an instance of the API class
        api_instance = PureCloudPlatformClientV2.StationsApi()
        name = self.webRTCName # str | Name of the Phone to filter by (optional)
        print("Checking for existing phone")
        try:
            # Get a list of Phone Instances
            api_response = api_instance.get_stations(name=name)
            if len(api_response.entities) == 0:
                print("No Phone")
                self.createPhone()
            else:
                self.findStation()
        except ApiException as e:
            output = e.body
            error = str(self.email) + ',' + str(output)+ '\n'
            temp_file_aggregate = "phoneimport_error_log1.csv"
            with open(temp_file_aggregate, 'a') as f:
                f.write(error)
            print("Exception when calling TelephonyProvidersEdgeApi->get_telephony_providers_edges_phones: %s\n" % e)
            return



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
            userslist.append(WebRTCIMPORTS(row[0],row[1],row[2],row[3]))

    for i in userslist:
        print("Importing WebRTC for " + str(i.email))
        id = i.getUserID()
        i.existingPhone()


    

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