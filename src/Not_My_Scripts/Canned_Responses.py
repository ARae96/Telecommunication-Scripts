# Created in Data Bricks https://wgu-prod.cloud.databricks.com/editor/notebooks/3179667252087605?o=6100882033744784#command/6013925061424105


#This function pulls all canned responses out of a library
#input : libraryID
#output : list of response objects
def pullResponses(libraryId):
  # create an instance of the API class
  api_instance = PureCloudPlatformClientV2.ResponseManagementApi()
  page_number = 1 # int | Page number (optional) (default to 1)
  page_size = 100 # int | Page size (optional) (default to 25)

  try:
      # Get details about an existing response.
      api_response = api_instance.get_responsemanagement_responses(libraryId,page_number = page_number,page_size =page_size)
      return api_response.entities
  except ApiException as e:
      logger.error("Exception when calling ResponseManagementApi->get_responsemanagement_response: %s\n")
      print(e)


#places all responses into readable dataframe
#input : list of response objects
#output: dataframe
def buildCannedResponseDf(listofresponses):
    rows = []

    for i in listofresponses:
        i_dict = i.to_dict()
        prettytext = BeautifulSoup(i_dict['texts'][0]['content'],'html.parser')
        rows.append({
            "id":i_dict['id'],
            "name": i_dict['name'],
            "libraries": i_dict['libraries'][0]['name'],
            "texts": prettytext.get_text(),
        })
    return rows


def handler():
   responselist = []
   librarylist =  ['069a1a9c-77e9-4767-9661-8ffdbb323434','301a52ff-9599-4802-822a-f44f1fdb1d0f']
   #sdStudentLibaryId = '069a1a9c-77e9-4767-9661-8ffdbb323434'
   #sdStaffLibraryId = '301a52ff-9599-4802-822a-f44f1fdb1d0f'
   #pullResponses(sdStaffLibraryId)
   for i in librarylist:
         responselist.extend(pullResponses(i))
   #print(responselist[0])
   dataframe = buildCannedResponseDf(responselist)
   display(dataframe)