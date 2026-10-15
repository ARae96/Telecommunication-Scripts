import csv
import datetime
import aiohttp
import base64
import asyncio
import json
import logging
from PureCloudPlatformClientV2.rest import ApiException
import PureCloudPlatformClientV2
import pprint
# Setup logging
logging.basicConfig(level=logging.INFO)

# Constants
HTTP_SUCCESS = 200
HTTP_RATE_LIMIT_ERROR = 429
BASE_PURECLOUD_AUTH_HOST = 'https://login.{domain}'
BASE_PURECLOUD_API_HOST = 'https://api.{domain}'
PAGE_SIZE = 200

# Token Fetching
class APIToken:
    def __init__(self, config):
        self.config = config
        self.token = None

    async def get_token(self):
        if not self.token:
            await self.refresh_token()
        return self.token

    async def refresh_token(self):
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

class DomainEntityRef:
    def __init__(self, id, name, self_uri):
        self.id = id
        self.name = name
        self.self_uri = self_uri


class CustomJSONDecoder(json.JSONDecoder):
    """Custom JSON decoder to convert JSON object to DomainEntityRef."""
    
    
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)
        
    def object_hook(self, dct):
        if 'id' in dct and 'name' in dct and 'self_uri' in dct:
            return DomainEntityRef(id=dct['id'], name=dct['name'], self_uri=dct['self_uri'])
        return dct
    
# Channel and Subscription
class IVRDetailsExtractor:
    def __init__(self, token):
        self.token = token

    async def revert_test_ivrs(self):
        ivr_backup = self.load_ivr_backup()
        api_instance = PureCloudPlatformClientV2.ArchitectApi()

        for ivr_id, data in ivr_backup.items():
            original_ivr_details = data["ivr_details"]
            
            # Drop/pop the 'version' key from original_ivr_details
            original_ivr_details.pop('version', None)
            
            try:
                print(f"Reverting IVR {ivr_id} with {original_ivr_details}")
                
                # api_response = api_instance.put_architect_ivr(ivr_id, original_ivr_details)
                # print(api_response)
            except ApiException as e:
                logging.error(f"Exception when reverting IVR {ivr_id}: {e}")

    def load_ivr_backup(self):
        with open('ivr_backup.json', 'r') as backup_file:
            data = json.load(backup_file)
        return data
                
                
# Main Execution
if __name__ == "__main__":
    config = {
        "domain": "mypurecloud.com",
        "client_id": "",
        "client_secret": ""
    }
    api_token_handler = APIToken(config)

    async def main():
        token = await api_token_handler.get_token()
        logging.info(f"Obtained token: {token[:10]}...")  # logging a part of the token for security reasons
        api_host = BASE_PURECLOUD_API_HOST.format(domain=config['domain'])
        PureCloudPlatformClientV2.configuration.host = api_host
        PureCloudPlatformClientV2.configuration.access_token = token
        
        details_extractor = IVRDetailsExtractor(token)
        await details_extractor.revert_test_ivrs()

    asyncio.run(main())