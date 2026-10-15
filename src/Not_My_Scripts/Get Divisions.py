from os import name
import time
import csv
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
import os

# Configure OAuth2 access token for authorization: PureCloud OAuth
os.environ['GENESYS_CLOUD_CLIENT_ID'] =
os.environ['GENESYS_CLOUD_CLIENT_SECRET'] = 
os.environ['GENESYS_CLOUD_REGION'] = 'us_east_1'  # eg. us_east_1
CLIENT_ID = os.environ['GENESYS_CLOUD_CLIENT_ID']
CLIENT_SECRET = os.environ['GENESYS_CLOUD_CLIENT_SECRET']
ORG_REGION = os.environ['GENESYS_CLOUD_REGION']  # eg. us_east_1
apiclient = PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(CLIENT_ID, CLIENT_SECRET)




api_instance = PureCloudPlatformClientV2.RoutingApi(apiclient)
page_number = 2 # int | Page number (optional) (default to 1)
page_size = 100 # int | Page size (optional) (default to 25)


api_response = api_instance.get_routing_queues(page_number=page_number, page_size=page_size)
queueslist = api_response.entities


import datetime
from datetime import date, timedelta
now = datetime.datetime.now()- timedelta(1)
yday = now.strftime('%Y-%m-%d')
user_file_name="/Users/meg.luong/Documents/GenC_Python/"+"lame"+".csv"
print(user_file_name)
 
with open(user_file_name, 'w', newline='') as f:
    columns = [ 'queue_name', 'queue_id', 'division_name', 'division_id', 'member_count', 'user_member_count', 'joined_member_count', 'skill_evaluation_method', 'auto_answer', 'enable_transcription', 'enable_manual_assignment', 'calling_party_name', 'calling_party_number']
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    for i in queueslist:
        division = i.division
        print(i.id)
        writer.writerow({'queue_name' : str(i.name),'queue_id' : str(i.id),'division_name' : str(division.name),  'division_id' : str(division.id),'member_count' : int(i.member_count),'user_member_count' : int(i.user_member_count),'joined_member_count' : int(i.joined_member_count), 'skill_evaluation_method' : str(i.skill_evaluation_method), 'auto_answer' : i.auto_answer_only, 'enable_transcription' : i.enable_transcription, 'enable_manual_assignment' : i.enable_manual_assignment, 'calling_party_name' : str(i.calling_party_name), 'calling_party_number' : str(i.calling_party_number)})
