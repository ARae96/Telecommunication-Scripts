import aiohttp
import base64
import asyncio
import logging
from PureCloudPlatformClientV2.rest import ApiException
import PureCloudPlatformClientV2
from pprint import pprint as pp
import time
import random

# Setup logging
logging.basicConfig(level=logging.INFO)

# Constants
HTTP_SUCCESS = 200
RETRY_RESPONSE_CODES = [429, 502, 503, 504]
API_RETRY_INTERVAL_SECONDS = 30
API_RETRY_COUNT = 5
BASE_PURECLOUD_AUTH_HOST = 'https://login.{domain}'
BASE_PURECLOUD_API_HOST = 'https://api.{domain}'
PAGE_SIZE = 100
BACKOFF_FACTOR = 2
MIN_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 120


# Decorator for exponential backoff and retry
def backoff_decorator(retry_count=API_RETRY_COUNT):
    def retry_on_exception(func):
        async def wrapper(*args, **kwargs):
            backoff_time = MIN_BACKOFF_SECONDS
            for _ in range(retry_count):
                try:
                    return await func(*args, **kwargs)
                except ApiException as e:
                    if e.status == 401:  # Unauthorized, indicating token may have expired
                        logging.warning("Unauthorized request, refreshing token...")
                        await args[0].token_handler.refresh_token()  # Using token handler to refresh
                    elif e.status in RETRY_RESPONSE_CODES:  # Rate Limit or other retryable errors
                        logging.warning(f"Encountered {e.status}. Retrying in {backoff_time} seconds.")
                        time.sleep(backoff_time)
                        backoff_time = min(backoff_time * BACKOFF_FACTOR, MAX_BACKOFF_SECONDS)
                        backoff_time += random.uniform(0, 0.1 * backoff_time)  # Add some jitter
                    else:
                        raise e
            raise ApiException("Max retries exceeded.")
        return wrapper
    return retry_on_exception

# Token Fetching
class APIToken:
    """Handles the PureCloud API token fetch and refresh operations."""
    def __init__(self, config):
        self.config = config
        self.token = None

    async def get_token(self):
        """Retrieve the API token, refreshing if necessary."""
        if not self.token:
            await self.refresh_token()
        return self.token

    async def refresh_token(self):
        """Refresh the API token."""
        client_id = self.config['client_id']
        client_secret = self.config['client_secret']
        client_domain = self.config['domain']

        auth_host = BASE_PURECLOUD_AUTH_HOST.format(domain=client_domain)
        auth_endpoint = '{}/oauth/token'.format(auth_host)

        client_creds = f"{client_id}:{client_secret}".encode('utf-8')
        authorization = base64.b64encode(client_creds).decode('ascii')

        body = {'grant_type': 'client_credentials'}
        headers = {
            'Authorization': f'Basic {authorization}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(auth_endpoint, data=body, headers=headers) as response:
                if response.status == HTTP_SUCCESS:
                    self.token = (await response.json())['access_token']
                
                else:
                    logging.error(f"Failed to fetch API token: {response.text()}")
        if not self.token:
            raise ApiException("Failed to fetch or refresh the token.")

class UtilizationHandler:
    """Handles operations related to PureCloud user utilization."""
    
    QUEUE_ID = "183e44b6-be73-4246-870a-2a25d6b28e5b"
    
    def __init__(self, token_handler):
        self.token_handler = token_handler
    
    @staticmethod
    def generate_utilization_body():
        """Generate the standard utilization body for API calls."""
        return {
            "utilization": {
                "call": {
                    "maximumCapacity": 1,
                    "interruptableMediaTypes": [
                        "message"
                    ]
                },
                "email": {
                    "maximumCapacity": 1
                },
                "message": {
                    "maximumCapacity": 10,
                    "interruptableMediaTypes": [
                        "call"
                    ]
                },
                "chat": {
                    "maximumCapacity": 1
                },
                "callback": {
                    "maximumCapacity": 1
                }
            }
        }
    
    @backoff_decorator()    
    async def gather_user_ids(self, api_instance):
        """Gather user IDs from the PureCloud platform."""
        user_data = []
        page_number = 1
        
        while True:
            try:
                api_response = api_instance.get_routing_queue_members(queue_id=self.QUEUE_ID,page_size=PAGE_SIZE, page_number=page_number)
                if not api_response.entities:
                    break
                user_data.extend([(user.id) for user in api_response.entities])
                if len(api_response.entities) < PAGE_SIZE:
                    break
                page_number += 1
            except ApiException as e:
                logging.error(f"Exception when calling IntegrationsApi->get_integrations_actions: {e}")
                break
        return user_data
    
    @backoff_decorator()
    async def update_utilization(self):
        """Update the utilization of users on the PureCloud platform."""
         
        routing_api_instance = PureCloudPlatformClientV2.RoutingApi()
        user_data = await self.gather_user_ids(routing_api_instance)
        users_api_instance = PureCloudPlatformClientV2.UsersApi()
        body = self.generate_utilization_body()
        
        # uncomment the following line to test with a single user
        #test_data = ['401cd451-ff62-47b4-9904-bd0b3d51f1a3']
        # uncomment the following line to test with a single user
        #for user_id in test_data:
        
        for user_id in user_data:
            try:
                api_response = users_api_instance.put_routing_user_utilization(user_id, body=body)
                pp(api_response)
            except ApiException as e:
                logging.error(f"Exception when calling get_integrations_action for ID {user_id}: {e}")

# Main Execution
if __name__ == "__main__":
    config = {
        "domain": "mypurecloud.com",
        "client_id": ,
        "client_secret": 
    }
    api_token_handler = APIToken(config)

    async def main():
        token = await api_token_handler.get_token()
        logging.info(f"Obtained token: {token[:10]}...")  # logging a part of the token for security reasons
        api_host = BASE_PURECLOUD_API_HOST.format(domain=config['domain'])
        PureCloudPlatformClientV2.configuration.host = api_host
        PureCloudPlatformClientV2.configuration.access_token = token
        
        details_extractor = UtilizationHandler(api_token_handler)
        await details_extractor.update_utilization()

    asyncio.run(main())
