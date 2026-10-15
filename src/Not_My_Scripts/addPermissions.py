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

def combinepermissions(roleUpdatePerms, roleAml):
    #function that pulls both permission sets of roles and combines them
    api_instance = PureCloudPlatformClientV2.AuthorizationApi(apiclient)
    #retrieve permission sets from both roles
    get_role = api_instance.get_authorization_role(roleUpdatePerms)
    permissionshave = get_role.permission_policies
    matched_role = api_instance.get_authorization_role(roleAml)
    permissionsneed = matched_role.permission_policies
    newPermSet = []
    duplicate = 0
    #Check for any permissions that are in both lists :
    for i in permissionshave:
        if i in permissionsneed:
            duplicate += 1
            continue
        else:
            newPermSet.append(i)
            
    newPermSet = newPermSet + permissionsneed

    #Testing number of permissions to make sure they properly combine to the expected amount    
 
    return newPermSet

def main(roleUpdatePerms, roleAml):
    #main function that pushes update to the role, calls to the combinepermissions function
    api_instance = PureCloudPlatformClientV2.AuthorizationApi(apiclient)
    body = PureCloudPlatformClientV2.DomainOrganizationRoleUpdate() # DomainOrganizationRoleUpdate | Organization role
    get_role = api_instance.get_authorization_role(roleUpdatePerms)
    body.name = get_role.name
    body.permission_policies = combinepermissions(roleUpdatePerms, roleAml)

    try:
        # Update an organization role.
        api_response = api_instance.put_authorization_role(roleUpdatePerms, body)
        pprint(api_response)
        permissionshave = get_role.permission_policies
        print(len(permissionshave))
    except ApiException as e:
        print("Exception when calling AuthorizationApi->put_authorization_role: %s\n" % e)

#initialize variables 
#ID of the role we are wanting to update 
roleUpdatePerms = '87b34660-5533-42bc-acf6-b102bf30b73e'
#ID of the role with the permissions we are adding 
roleAml = 'a6558338-2809-4e8f-b3e3-6d6a0f613abb'

#main(roleUpdatePerms, roleAml)






rolesToUpdate = ['e291bdab-fc47-46e5-bccf-7d76d22f53cb', '4920964e-0649-41df-bc13-cc601ec8be25', 'e2f71c54-9878-4162-98ed-a938c05756f2', '379a2ec7-ca8b-4f74-b69b-de512b7f6712', 'b525165a-8e12-42f3-ad80-d2d43ab7622b', '8a54e65e-6d6f-4b42-b4f6-05638220cec6', 'c6dd698a-0272-4f4c-960d-f8e5483df028', '52d17ff8-e6eb-48de-bbc2-29c512aa539a', '007ae6c8-e42b-4714-ac90-4cd9344cf302', '2597e131-bb62-4ece-8773-763229cdb9c8', '2862d5cd-7139-4be6-9666-e372e3dbf037', '03eb5f07-845c-4702-b134-9ea12711b751', '0275ed3b-9354-432d-a3b9-867d29ada7c8', 'cb15d282-6843-4760-8728-c72fb165ff32', '223260fb-125d-46d1-b033-f955b2d0fff2']

print(rolesToUpdate)
for i in rolesToUpdate: 
    api_instance = PureCloudPlatformClientV2.AuthorizationApi(apiclient)
        #retrieve permission sets from both roles
    get_role = api_instance.get_authorization_role(i)
    print(get_role.name)

