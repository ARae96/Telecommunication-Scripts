# Created in Data Bricks https://wgu-prod.cloud.databricks.com/editor/notebooks/709363860717432?o=6100882033744784#command/8127758561262787

def getRoles():
  # create an instance of the API class
    api_instance = PureCloudPlatformClientV2.AuthorizationApi()
    page_size = 100 # int | The total page size requested (optional) (default to 25)
    page_number = 1 # int | The page number requested (optional) (default to 1)

    all_roles = []

    try:
        while True:  
            # Retrieve a list of all roles defined for the organization
            api_response = api_instance.get_authorization_roles(page_size=page_size, page_number=page_number)
            
            response_dict = api_response.to_dict()
            roles = response_dict['entities']
            all_roles.extend(roles)

            # Check for more pages
            if len(roles) < page_size:
                break
            page_number += 1

        return all_roles
          
    except ApiException as e:
        logger.error("Exception when calling AuthorizationApi->get_authorization_roles: %s\n" % e)
        print(e)
        
def buildRolesDf(roles):
    
    result = []

    for i in roles:
        for p in i.get("permission_policies") or []:
            for action in (p.get("action_set") or []):
                result.append({
                    "role_name": i.get("name"),
                    "default": i.get("default"),
                    "user_count": i.get("user_count"),
                    "domain": p.get("domain"),
                    "entity_name": p.get("entity_name"),
                    "action": action,
                    "permission": "".join(p.get("domain") + "-" + p.get("entity_name") + "-" + action),
                })

    return result