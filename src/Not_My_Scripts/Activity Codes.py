import time
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
import os
import csv

# Configure OAuth2 access token for authorization: PureCloud OAuth

os.environ['GENESYS_CLOUD_CLIENT_ID'] = 
os.environ['GENESYS_CLOUD_CLIENT_SECRET'] = 
os.environ['GENESYS_CLOUD_REGION'] = 'us_east_1'  # eg. us_east_1
CLIENT_ID = os.environ['GENESYS_CLOUD_CLIENT_ID']
CLIENT_SECRET = os.environ['GENESYS_CLOUD_CLIENT_SECRET']
ORG_REGION = os.environ['GENESYS_CLOUD_REGION']  # eg. us_east_1
apiclient = PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(CLIENT_ID, CLIENT_SECRET)

# create an instance of the API class

api_instance = PureCloudPlatformClientV2.WorkforceManagementApi(apiclient)
businessunitlist = []
user_file_name="/Users/meg.luong/Documents/GenC_Python/ActivityCodes/"+'UniqueActivityCodes'+".csv"

with open(user_file_name, 'w', newline='') as f:
    columns = ['businessunit_name', 'businessunit_id', 'activitycode_name', 'activitycode_id', 'active', 'category', 'paid', 'selfuri']
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()

def BusinessUnitCodes(businessUnitID):
    api_response = api_instance.get_workforcemanagement_businessunit_activitycodes(businessUnitID)
    bu_api_response = api_instance.get_workforcemanagement_businessunit(businessUnitID)
    businessUnitName = bu_api_response.name
    print(businessUnitName)
    list = api_response.entities

    for i in list:
        if (i.name == ''):
                continue
        else:
            print(i.id)
            with open(user_file_name, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writerow({'businessunit_name' : businessUnitName, 'businessunit_id' : businessUnitID, 'activitycode_name' : str(i.name), 'activitycode_id' : str(i.id), 'active' : str(i.active), 'category' : str(i.category), 'paid' : str(i.counts_as_paid_time), 'selfuri' : str(i.self_uri)})
          

bu_api_response = api_instance.get_workforcemanagement_businessunits()
allbusinessunits = (bu_api_response.entities)

for i in allbusinessunits:
    businessunitlist.append(i.id)
for i in businessunitlist:
    BusinessUnitCodes(i)
