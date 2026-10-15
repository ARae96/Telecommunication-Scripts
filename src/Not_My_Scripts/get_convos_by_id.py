import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
from dotenv import load_dotenv
import os
import json

load_dotenv()


apiclient = (
    PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(
        os.environ["CLIENTID"], os.environ["CLIENTSECRET"]
    )
)

api_instance = PureCloudPlatformClientV2.ConversationsApi(apiclient)
conversation_id = "794a4179-b0b8-42e5-8085-dda6c0b4972e"  # str | conversationId

try:
    api_response = api_instance.get_analytics_conversation_details(conversation_id)
    data = api_response.to_json()
    data_loaded = json.loads(data)
    print(data_loaded["conversation_start"])
except ApiException as e:
    print(
        "Exception when calling ConversationsApi->get_analytics_conversation_details: %s\n"
        % e
    )
