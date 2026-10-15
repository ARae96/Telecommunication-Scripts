gbimport base64, sys, os
import PureCloudPlatformClientV2

os.environ['GENESYS_CLOUD_CLIENT_ID'] =
os.environ['GENESYS_CLOUD_CLIENT_SECRET'] = 
os.environ['GENESYS_CLOUD_REGION'] = 'us_east_1'  # eg. us_east_1
CLIENT_ID = os.environ['GENESYS_CLOUD_CLIENT_ID']
CLIENT_SECRET = os.environ['GENESYS_CLOUD_CLIENT_SECRET']
ORG_REGION = os.environ['GENESYS_CLOUD_REGION']  # eg. us_east_1
apiclient = PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(CLIENT_ID, CLIENT_SECRET)
# Local reference for routing API
routing_api = PureCloudPlatformClientV2.RoutingApi(apiclient)

def getQueues(queueList):
    """
    Retrieve a list of all pureCloud queue objects in current environment
    
    Limited to ~3000 results
    
    :raises ValueError: lists of queue too long, only 3000 results supported
    :returns: list of all PureCloud queue objects in current environment
    """
    queueList = []
    for page in range(1,30): # TODO: Unify pages functionality
        response = routing_api.get_routing_queues(page_size=100,page_number=page)
        # Check if last page (empty response)
        if len(response.entities) == 0 : break
        queueList += response.entities
    else:
        raise ValueError('Interval too long: More than 3000 results')
    return queueList

def getWrapupCodes(wrapupList):
    wrapupList = []
    for page in range(1,30):
        response = routing_api.get_routing_wrapupcodes(page_size=100,page_number=page)
        # Check if last page (empty response)
        if len(response.entities) == 0 : break
        wrapupList += response.entities
    else:
        raise ValueError('Interval too long: More than 3000 results')
    print(wrapupList)
    return wrapupList

def getQueueWrapupCodes(wrapupList):
    wrapupList = []
    response = routing_api.get_routing_queue_wrapupcodes()
    wrapupList += response.entities
    print(wrapupList)
    return wrapupList    


def printQueueList():
    queues = getQueues()
    for q in queues:
        print(q.id,"\t",q.name)
        
que = printQueueList(getQueues)

print(que)
