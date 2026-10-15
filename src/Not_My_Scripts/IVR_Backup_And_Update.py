import logging
import json
import aiohttp
import base64
import asyncio
from PureCloudPlatformClientV2 import DomainEntityRef
from PureCloudPlatformClientV2.configuration import Configuration
from PureCloudPlatformClientV2.rest import ApiException
import PureCloudPlatformClientV2

# Setup logging
logging.basicConfig(level=logging.INFO)

# Constants
HTTP_SUCCESS = 200
BASE_PURECLOUD_AUTH_HOST = 'https://login.{domain}'
BASE_PURECLOUD_API_HOST = 'https://api.{domain}'
PAGE_SIZE = 100


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


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, DomainEntityRef):
            return {
                "id": getattr(obj, 'id', None),
                "name": getattr(obj, 'name', None),
                "self_uri": getattr(obj, 'self_uri', None)
            }
        return super().default(obj)


class IVRDetailsExtractor:
    def __init__(self, token):
        self.token = token

    async def gather_ivr_ids_and_names(self):
        api_instance = PureCloudPlatformClientV2.ArchitectApi()
        ivr_details = []
        page_number = 1

        while True:
            try:
                api_response = api_instance.get_architect_ivrs(page_size=PAGE_SIZE, page_number=page_number)
                if not api_response.entities:
                    break
                
                # Filter out entities where closedHoursFlow is None or name contains 'Enroll', 'Inactive', 'Do Not Use'
                filtered_entities = [
                    entity for entity in api_response.entities 
                    if entity.closed_hours_flow is not None 
                    and all(keyword not in entity.name.lower() for keyword in ['enroll', 'inactive', 'do not use'])
                ]
                ivr_details.extend(filtered_entities)
                
                page_number += 1
            except ApiException as e:
                logging.error(f"Exception when calling ArchitectApi->get_architect_ivrs: {e}")
                break
        return ivr_details

    async def update_test_ivrs(self):
        all_ivr_details = await self.gather_ivr_ids_and_names()
        ivr_backup = {ivr.id: {"ivr_details": self.ivr_to_dict(ivr)} for ivr in all_ivr_details}

        with open('ivr_backup.json', 'w') as backup_file:
            json.dump(ivr_backup, backup_file, indent=4, cls=CustomJSONEncoder) 
        '''
        api_instance = PureCloudPlatformClientV2.ArchitectApi()
        updated_flow_id = "98b88997-957e-451e-a4d7-3ab28c94c825"
        updated_flow_name = "98.1_AllStaff_All"

        for ivr in all_ivr_details:
                body = ivr_backup[ivr.id]["ivr_details"].copy()
                
                # Remove the 'version' key from the body
                body.pop('version', None)
                
                if body["closedHoursFlow"]:
                    body["closedHoursFlow"]["id"] = updated_flow_id
                    body["closedHoursFlow"]["name"] = updated_flow_name

                try:
                    print(f"Updating IVR {ivr.id} with {body}")
                    
                    # api_instance.put_architect_ivr(ivr.id, body)
                except ApiException as e:
                    logging.error(f"Exception when updating IVR {ivr.id}: {e}")
        '''
    @staticmethod
    def ivr_to_dict(ivr):
        to_dict = lambda entity: None if not entity else {"id": entity.id, "name": entity.name, "self_uri": entity.self_uri}
        return {
            "name": ivr.name,
            "division": to_dict(ivr.division),
            "description": ivr.description,
            "version": ivr.version,
            "dnis": ivr.dnis,
            "openHoursFlow": to_dict(ivr.open_hours_flow),
            "closedHoursFlow": to_dict(ivr.closed_hours_flow),
            "holidayHoursFlow": to_dict(ivr.holiday_hours_flow),
            "scheduleGroup": ivr.schedule_group
        }


if __name__ == "__main__":
    config = {
        "domain": "mypurecloud.com",
        "client_id": "",
        "client_secret": ""
    }
    api_token_handler = APIToken(config)

    async def main():
        token = await api_token_handler.get_token()
        logging.info(f"Obtained token: {token[:10]}...")
        api_host = BASE_PURECLOUD_API_HOST.format(domain=config['domain'])
        PureCloudPlatformClientV2.configuration.host = api_host
        PureCloudPlatformClientV2.configuration.access_token = token

        details_extractor = IVRDetailsExtractor(token)
        await details_extractor.update_test_ivrs()

    asyncio.run(main())