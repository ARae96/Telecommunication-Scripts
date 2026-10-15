
import time
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

api_instance = PureCloudPlatformClientV2.UsersApi(apiclient)
api_instance_auth = PureCloudPlatformClientV2.AuthorizationApi(apiclient)


convoids = []
#Function that checks if a recording exists for a specific conversation
def disconnect_interactions(conversationID):
    api_instance = PureCloudPlatformClientV2.ConversationsApi(apiclient)
    conversation_id = conversationID # str | Conversation ID

    try:
        # Get all of a Conversation's Recordings.
        api_response = api_instance.post_conversation_disconnect(conversation_id)
        for i in api_response:
            print('{} successfully disconnected {} '.format(conversation_id, i))
        return
    except ApiException as error:
        if error.reason:
            print(error.reason)
            return
        else:
            giveup(error)
            return

#function that querys conversation details, filters out the following : DivisionID, Outbound, and Voice media. Conversation IDs that match filter will be appended to the convoids list


result_waiting = []

def get_waiting_interactions():
    
    api_instance = PureCloudPlatformClientV2.AnalyticsApi(apiclient)
    body = PureCloudPlatformClientV2.QueueObservationQuery()
    body = {
        "filter": {
            "type": "and",
            "predicates": [
            {
                "type": "dimension",
                "dimension": "mediaType",
                "operator": "matches",
                "value": "message"
            },
            {
                "type": "dimension",
                "dimension": "queueId",
                "operator": "matches",
                "value": "3a995e63-1589-44be-bfec-4ff218500c57"
                #b75e16f3-4cf7-42f5-8dd0-dadb95638146
                #b60d8687-1459-4806-a1c1-8996b94521ce
            }
            ]
            },
        "metrics": [
        "oWaiting"
        ],
        "detailMetrics": [
        "oWaiting"
        ]
        }
    try:
        api_response = api_instance.post_analytics_queues_observations_query(body)
        print(api_response)
        result = api_response.results[0].data
        result_waiting = result[0].observations
        #print(result_waiting)
        count = 0
        if result_waiting == None:
            return
        else:
            
            for i in result_waiting:
                conv = result_waiting[count].conversation_id
                count+=1
                print(conv)
                if conv in convoids:
                    continue
                else:
                    convoids.append(conv)
    
    except ApiException as error:
        if error.reason == "Not Found":
            print("No conversations found")
            return
        else:
            return   
def sendMessage(convoid):
    

    # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.ConversationsApi(apiclient)
    body = PureCloudPlatformClientV2.SendAgentlessOutboundMessageRequest() # SendAgentlessOutboundMessageRequest | Create agentless outbound messaging request
    body.from_address = "+13852573860"
    body.to_address = "+18014557734"
    body.to_address_messenger_type = "sms"
    body.text_body = "[AUTOREPLY] We are aware of an issue preventing access to the Student Portal. We are temporarily disabling SMS support in order to ensure that students calling in with other issues are supported. In the meantime, please open a ticket at servicedesk@wgu.edu with your student username to open a ticket."
    try:
        # Send an agentless outbound message
        api_response = api_instance.post_conversations_messages_agentless(body)
        pprint(api_response)
    except ApiException as e:
        print("Exception when calling ConversationsApi->post_conversations_messages_agentless: %s\n" % e)
    
def main():
        
    #retrieve DNIS values from each conversation, converts them into (###) ###-#### format
    get_waiting_interactions()
    print(convoids)
    for c in convoids:
        index = int(convoids.index(c))+1
        print("Disconnecting interaction " + str(index) + " out of " + str(len(convoids)))
        disconnect_interactions(c)
        sendMessage(c)

main()
