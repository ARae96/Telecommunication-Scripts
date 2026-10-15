import PureCloudPlatformClientV2
import os
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint


os.environ['GENESYS_CLOUD_CLIENT_ID'] = '97e23c71-abaf-4321-b198-cb7c8b725c12'
os.environ['GENESYS_CLOUD_CLIENT_SECRET'] = 'G47C__POHm0wxdsKFzDTAFPWEwYvjXbkgbSfsN_4TxT_EaASwtz3VqBqHu9g'

apiclient = PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(os.environ['GENESYS_CLOUD_CLIENT_ID'],
                                                                                          os.environ['GENESYS_CLOUD_CLIENT_SECRET'])
authApi = PureCloudPlatformClientV2.AuthorizationApi(apiclient)
print(authApi.get_authorization_permissions())

# API's are /api/v2/routing/queues/{queueId}/members & /api/v2/routing/queues/{queueId}/members
# The first gets the members of each queue and the second adds or removes people from the queue
# Mirroring the Inbound and Outbound members list for queues
# Add apiclient into the api_instance () 


#This function adds a list of members to a given queueID
#Inputs : queueId, list of Genesys users ids
def addMembersToQueue(queueId, listOfUsers):
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.RoutingApi(apiclient)
    queue_id = queueId # str | Queue ID
    body = listOfUsers # list[QueueMember] | Queue Members
    try:
    # Bulk add or delete up to 100 queue members
        api_instance.post_routing_queue_members(queue_id, body)
    except ApiException as e:
        print("Exception when calling RoutingApi->post_routing_queue_members: %s\n" % e)


# We will add the queue ID as a list later not one at a time
# page_size is the number of objects

#This function pulls users from a given Genesys queue and adds them to a list
def getQueueMembers(queueId):
    listofusers = []
    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.RoutingApi(apiclient)
    queue_id =  queueId# str | Queue ID
    page_number = 1 # int |  (optional) (default to 1)
    page_size = 100 # int | Max value is 100 (optional) (default to 25)
    #joined = True # bool | Filter by joined status (optional)

    try:
        # Get the members of this queue.
        api_response = api_instance.get_routing_queue_members(queue_id, page_number=page_number, page_size=page_size)
        listofmembers = api_response.entities
        for member in listofmembers:
            idDict = {}
            idDict["id"] = member.id
            listofusers.append(idDict)
            #listofusers.append(member.id)
    except ApiException as e:
        print("Exception when calling RoutingApi->get_routing_queue_members: %s\n" % e)

    return listofusers

#Pull Members of an Enrollment queue 
originalQueue = '3d07a883-3127-4076-9a93-f1ab808b0c34'
listofusers = getQueueMembers(originalQueue)
#print(len(listofusers))
print(listofusers)
#Put those members into a list
addMembersToQueue("8cf82c32-9aa3-4cb7-974d-3cc41086afaa", listofusers)
#Add them to a different queue