import time
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
import os




os.environ['GENESYS_CLOUD_CLIENT_ID'] = ''
os.environ['GENESYS_CLOUD_CLIENT_SECRET'] = ''
os.environ['GENESYS_CLOUD_REGION'] = 'us_east_1'  # eg. us_east_1
CLIENT_ID = os.environ['GENESYS_CLOUD_CLIENT_ID']
CLIENT_SECRET = os.environ['GENESYS_CLOUD_CLIENT_SECRET']
ORG_REGION = os.environ['GENESYS_CLOUD_REGION']  # eg. us_east_1
apiclient = PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(CLIENT_ID, CLIENT_SECRET)

api_instance = PureCloudPlatformClientV2.UsersApi(apiclient)
api_instance_auth = PureCloudPlatformClientV2.AuthorizationApi(apiclient)


queueusers = []
def assignroutingLanguage(id):
    
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.RoutingApi(apiclient)
    user_id = id # str | User ID
    body = PureCloudPlatformClientV2.UserRoutingLanguagePost() # UserRoutingLanguagePost | Language
    body.id = "2ff3f804-80c3-4729-9ff3-bef5f96703d6"
    body.proficiency = "5"

    try:
        # Add routing language to user
        api_response = api_instance.post_user_routinglanguages(user_id, body)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling RoutingApi->post_user_routinglanguages: %s\n" % e)
def assignskill(id):
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.UsersApi(apiclient)
    user_id = id # str | User ID
    body = PureCloudPlatformClientV2.UserRoutingSkillPost() # UserRoutingSkillPost | Skill
    body.id = "c73635f2-9de1-4a8a-b82f-19fc31b99478"
    body.proficiency = "5"

    try:
        # Add routing skill to user
        api_response = api_instance.post_user_routingskills(user_id, body)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling UsersApi->post_user_routingskills: %s\n" % e)
        
def getUsers():
    
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.RoutingApi(apiclient)
    queue_id = 'ddd44d59-544f-4929-9e9d-8d7568c7ae31'
# str | Queue ID
    page_number = 1 # int |  (optional) (default to 1)
    page_size = 100 # int | Max value is 100 (optional) (default to 25)

    try:
        # Get the members of this queue.
        api_response = api_instance.get_routing_queue_members(queue_id, page_number=page_number, page_size=page_size)
        users = (api_response.entities)
        for i in users:
            queueusers.append(i.id)
            
    except ApiException as e:
        print("Exception when calling RoutingApi->get_routing_queue_members: %s\n" % e)
        
getUsers()
for i in queueusers:
    assignroutingLanguage(i)
