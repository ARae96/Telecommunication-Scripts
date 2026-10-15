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


#Global variables
#ID of user getting their perms updated
user_id = 
#USER ID OF AML YOU ARE MATCHING PERMISSIONS/DIVISION TO 
AML = 


#Role class object that stores role and division ID into object
class Role:
    def __init__(self, roleId, division):
       self.roleId = roleId
       self.division = division
    #Class function that pushes /api/v2/authorization/subjects/{subjectId}/bulkadd API call using the roleid and division it has assigned
    def assignRole(self):
        # create an instance of the API class
        api_instance = PureCloudPlatformClientV2.AuthorizationApi(apiclient)
        subject_id = user_id # str | Subject ID (user or group)
        body = PureCloudPlatformClientV2.RoleDivisionGrants()
        body.grants = [PureCloudPlatformClientV2.RoleDivisionPair()]
        body.grants[0].role_id = self.roleId
        body.grants[0].division_id = self.division

        subject_type = "PC_USER" # str | what the type of the subject is (PC_GROUP, PC_USER or PC_OAUTH_CLIENT) (optional) (default to 'PC_USER')

        try:
            # Bulk-grant roles and divisions to a subject.
            
            api_instance.post_authorization_subject_bulkadd(subject_id, body, subject_type=subject_type)
        except ApiException as e:
            print("Exception when calling AuthorizationApi->post_authorization_subject_bulkadd: %s\n" % e)


#Clears all users roles then gets all roles and pertaining divisions assigned to user, stores in Role object and calls the assignRole object function
def getRoles():

    #Removes all of user's previous roles with the exception of Employee - Home
    api_instance = PureCloudPlatformClientV2.AuthorizationApi(apiclient)
    subject_id = user_id # str | Subject ID (user or group)
    body = PureCloudPlatformClientV2.RoleDivisionGrants() # RoleDivisionGrants | Pairs of role and division IDs
    subject_type = "PC_USER" # str | what the type of the subject is (PC_GROUP, PC_USER or PC_OAUTH_CLIENT) (optional) (default to 'PC_USER')
    body.grants = [PureCloudPlatformClientV2.RoleDivisionPair()]
    body.grants[0].role_id = 
    body.grants[0].division_id = 


    try:
        # Replace subject's roles and divisions with the exact list supplied in the request.
        api_instance.post_authorization_subject_bulkreplace(subject_id, body, subject_type=subject_type)
    except ApiException as e:
        print("Exception when calling AuthorizationApi->post_authorization_subject_bulkreplace: %s\n" % e)


    subject_id = AML # str | Subject ID (user or group)

    try:
        # Returns a listing of roles and permissions for a user.
        api_response = api_instance.get_authorization_subject(subject_id)
        role = api_response.grants
        count=0
        for i in role:
            role = Role(i.role.id, i.division.id)
            role.assignRole()
    except ApiException as e:
        print("Exception when calling AuthorizationApi->get_authorization_subject: %s\n" % e)

getRoles()
