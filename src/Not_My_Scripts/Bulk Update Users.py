import time
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint

# Configure OAuth2 access token for authorization: PureCloud OAuth
PureCloudPlatformClientV2.configuration.access_token = 

def getUserByEmail(email): 
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
    try:
            # Search users
            api_response = api_instance.post_users_search(body)
            id = api_response.results[0].id
            return id
    except ApiException as e:
            print("Exception when calling UsersApi->post_users_search: %s\n" % e)
def removepermissions(id):
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.AuthorizationApi()
    subject_id = id # str | Subject ID (user or group)
    #create role and division pair
    pair = PureCloudPlatformClientV2.RoleDivisionPair()
    pair.role_id = "4ab1c48a-5a6b-4962-a661-f5b4053cdbfe"
    pair.division_id = "df1b7ef4-744c-4b47-8aad-9dc6b2ecb9e0"
    #creating body
    body = PureCloudPlatformClientV2.RoleDivisionGrants() # RoleDivisionGrants | Pairs of role and division IDs
    body.grants = [pair]
    subject_type = 'PC_USER' # str | what the type of the subject is (PC_GROUP, PC_USER or PC_OAUTH_CLIENT) (optional) (default to PC_USER)


    try:
        # Replace subject's roles and divisions with the exact list supplied in the request.
        api_instance.post_authorization_subject_bulkreplace(subject_id, body, subject_type=subject_type)
    except ApiException as e:
        print("Exception when calling AuthorizationApi->post_authorization_subject_bulkreplace: %s\n" % e)
def getQueueIDs(id):
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.UsersApi()
    user_id = id # str | User ID
    page_size = 100 # int | Page size (optional) (default to 25)
    page_number = 1 # int | Page number (optional) (default to 1)

    try:
        # Get queues for user
        api_response = api_instance.get_user_queues(user_id, page_size=page_size, page_number=page_number)
        entities = api_response.entities
        #Create array with every Queue user is apart of, set variables
        loop = len(entities)
        x = 0
        queueIDs = []
        while x < loop : 
            queueIDs.append(entities[x].id)
            x += 1
        return queueIDs
    except ApiException as e:
        print("Exception when calling UsersApi->get_user_queues: %s\n" % e)
def removeFromQueues(queueIDs, id):
    api_instance = PureCloudPlatformClientV2.RoutingApi()
    for x in queueIDs:
        try:
            api_instance.delete_routing_queue_member(x, id)
        except ApiException as e:
            print("Exception when calling RoutingApi->delete_routing_queue_member: %s\n" % e)
def assignQueue(id, programName):
    api_instance = PureCloudPlatformClientV2.RoutingApi()
    queue_data = api_instance.get_routing_queues(name=programName)
    queue_id = queue_data.entities[0].id # str | Queue ID
    set = {'id' : id}
    body = [set] # list[WritableEntity] | Queue Members
    delete = False # bool | True to delete queue members (optional) (default to false)


    try:
        # Bulk add or delete up to 100 queue members
        api_instance.post_routing_queue_members(queue_id, body, delete=delete)
    except ApiException as e:
        print("Exception when calling RoutingApi->post_routing_queue_members: %s\n" % e)
def assignDivision(programName, id):
    api_instance = PureCloudPlatformClientV2.RoutingApi()
    queue_data = api_instance.get_routing_queues(name=programName)
    queue_division = queue_data.entities[0].division # str | Queue ID
    divisionid = queue_division.id
    api_instance = PureCloudPlatformClientV2.AuthorizationApi()

    object_type = 'USER' # str | The type of the objects. Must be one of the valid object types
    bodyD = [id]

    try:
        # Assign a list of objects to a division
        api_instance.post_authorization_division_object(divisionid, object_type, bodyD)
    except ApiException as e:
        print("Exception when calling AuthorizationApi->post_authorization_division_object: %s\n" % e)
def assignGroupPerms(groupName,id):
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.GroupsApi()
    search_api = PureCloudPlatformClientV2.SearchApi()
    api_instance = PureCloudPlatformClientV2.GroupsApi()
    bodyAssignGroup = PureCloudPlatformClientV2.GroupMembersUpdate()
    
    query = PureCloudPlatformClientV2.GroupSearchCriteria()
    query.type = 'EXACT'
    query.value = groupName
    query.fields = ['name']
    query.operator = 'AND'

    body = PureCloudPlatformClientV2.GroupSearchRequest()
    body.query = [query]

    try:
        # Search groups
        api_response = api_instance.post_groups_search(body)
        array = api_response.results
        groupid = array[0].id
        getGroup = api_instance.get_group(groupid)
        version = getGroup.version
        bodyAssignGroup.version = version
        bodyAssignGroup.member_ids = [id]
        api_response = api_instance.post_group_members(groupid, bodyAssignGroup)

    except ApiException as e:
        print("Exception when calling GroupsApi->post_groups_search: %s\n" % e)
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.GroupsApi()
    search_api = PureCloudPlatformClientV2.SearchApi()


email = input('Please enter in a users email: ')
id = getUserByEmail(email)
programName = input('Please enter in a program/division: ')
print('Clearing out all previous roles/Queues')
queueIDs = getQueueIDs(id)
removeFromQueues (queueIDs, id)
removepermissions(id)
assignGroupPerms(programName, id)
print('Assigning new role and Queues')
assignDivision(programName, id)
assignQueue(id,programName)
print('User ' + email + ' has been successfully updated to be under ' + programName)
