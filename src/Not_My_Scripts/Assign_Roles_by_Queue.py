import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
import os

os.environ['GENESYS_CLOUD_CLIENT_ID'] = ''
os.environ['GENESYS_CLOUD_CLIENT_SECRET'] = ''
os.environ['GENESYS_CLOUD_REGION'] = 'us_east_1'  # eg. us_east_1
CLIENT_ID = os.environ['GENESYS_CLOUD_CLIENT_ID']
CLIENT_SECRET = os.environ['GENESYS_CLOUD_CLIENT_SECRET']
ORG_REGION = os.environ['GENESYS_CLOUD_REGION']  # eg
apiclient = PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(CLIENT_ID, CLIENT_SECRET)


#Pulls users associated with a queue into a list
#input : Queue ID
#output : list of user objects
def grabUsersFromQueue(queueId):
    listofusers = []
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.RoutingApi(apiclient)
    queue_id = queueId # str | Queue ID
    page_number = 1 # int |  (optional) (default to 1)
    page_size = 100 # int | Max value is 100 (optional) (default to 25)
    joined = True # bool | Filter by joined status (optional)

    try:
        # Get the members of this queue.
        api_response = api_instance.get_routing_queue_members(queue_id, page_number=page_number, page_size=page_size, joined=joined)
        listofusers.extend(api_response.entities)
        while api_response.entities:
            page_number +=1 
            api_response = api_instance.get_routing_queue_members(queue_id, page_number=page_number, page_size=page_size, joined=joined)
            listofusers.extend(api_response.entities)
    except ApiException as e:
        print("Exception when calling RoutingApi->get_routing_queue_members: %s\n" % e)

    return listofusers

#Assigns a role with a given list of divisions
#input : RoleID, list of divisions tied to role, list of users being assigned role
#output : None
def assignRole(roleId, divisionlist, listofusers):
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.AuthorizationApi(apiclient)
    role_id = roleId # str | Role ID
    body = PureCloudPlatformClientV2.SubjectDivisions() # SubjectDivisions | Subjects and Divisions
    subject_type = "PC_USER" # str | what the type of the subjects are (PC_GROUP, PC_USER or PC_OAUTH_CLIENT) (optional) (default to 'PC_USER')
    body.division_ids = divisionlist

    for i in listofusers:
        try:
            body.subject_ids = [i.id]
            # Bulk-grant subjects and divisions with an organization role.
            api_response  = api_instance.post_authorization_role(role_id, body, subject_type=subject_type)
        except ApiException as e:
            print("Exception when calling AuthorizationApi->post_authorization_role: %s\n" % e)
            print(i)
            continue

#Checks if a user is a member of a specified queue
#input : userID, name of queue to check
#output : None
def checkqueuemembership(userId,queueNameLookup):
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.UsersApi(apiclient)
    user_id = userId  # str | User ID
    page_size = 100 # int | Page size (optional) (default to 25)
    page_number = 1 # int | Page number (optional) (default to 1)
    joined = True # bool | Is joined to the queue (optional) (default to True)

    try:
        # Get queues for user
        api_response = api_instance.get_user_queues(user_id, page_size=page_size, page_number=page_number, joined=joined)
        for i in api_response.entities:
            if i.name == queueNameLookup:
                print("User " + userId + " is in the SD Queue and SD Staff queue")
            else:
                print("User " + userId + " is NOT the SD Queue")
    except ApiException as e:
        print("Exception when calling UsersApi->get_user_queues: %s\n" % e)

#Agent Copilot Role
roleID = "8a3dab0e-747c-4c58-9f5f-e7cf83717c42"
#Service Desk Division
divsionlist = ["31ff025e-5de8-49f3-b577-3a96786cb164"]

#academyQueueID  = "d0816199-bb30-4e8b-9480-d5546a7d7cc5"
sdStaffQueueID  = "b60d8687-1459-4806-a1c1-8996b94521ce"

queueMemberList = grabUsersFromQueue(sdStaffQueueID)
print(queueMemberList)
print(len(queueMemberList))

#testlist = ["57aa7f10-d853-4758-827b-fac2b7246a35"]

#for i in queueMemberList:
    #checkqueuemembership(i.id,"Service Desk Students")

#assignRole(roleID,divsionlist,queueMemberList)
