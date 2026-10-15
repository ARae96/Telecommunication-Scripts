import time
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
import os

os.environ['GENESYS_CLOUD_CLIENT_ID'] = 
os.environ['GENESYS_CLOUD_CLIENT_SECRET'] = 
os.environ['GENESYS_CLOUD_REGION'] = 'us_east_1'  # eg. us_east_1
CLIENT_ID = os.environ['GENESYS_CLOUD_CLIENT_ID']
CLIENT_SECRET = os.environ['GENESYS_CLOUD_CLIENT_SECRET']
ORG_REGION = os.environ['GENESYS_CLOUD_REGION']  # eg. us_east_1
apiclient = PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(CLIENT_ID, CLIENT_SECRET)

members = []

def getUserByEmail(): 
        # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.UsersApi(apiclient)
    search_api = PureCloudPlatformClientV2.SearchApi(apiclient)
        # create body
    query = PureCloudPlatformClientV2.UserSearchCriteria()
    query.type = 'EXACT'
    query.value = "Service Help Desk"
    query.fields = ['department']
    query.operator = 'AND'

    body = PureCloudPlatformClientV2.UserSearchRequest() 
    body.sort_order = 'DESC'
    body.types = ['USERS']
    body.query = [query]
    page = 1
    body.page_number = page
    try:
            # Search users
            api_response = api_instance.post_users_search(body)
            pages = api_response.page_count
            print(pages)
            while page <= pages: 
                api_response = api_instance.post_users_search(body)
                results = api_response.results
                for i in results:
                    print(i.email)
                    members.append(i.email)
                page += 1
                body.page_number = page
    except ApiException as e:
            print("Exception when calling UsersApi->post_users_search: %s\n" % e)

getUserByEmail()
print(len(members))
