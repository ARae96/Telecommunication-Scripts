Scripts to handle onboarding process. 

template sheet : https://westerngovernorsuniversity.sharepoint.com/:x:/r/sites/SiteSupport/Shared%20Documents/Employee%20Onboarding%20and%20Offboarding%20Support/Templates/PureCloud/Master%20Phone%20Template%20Overlord.xlsx?d=wa1fb157b5892479a96c1569196de2425&csf=1&web=1&e=wyemo7

Steps: 
1. Export new hire task in ServiceNow to csv
2. copy csv into 'Data' tab of template sheet
3. Create templates for any rows in 'Template Prebuild' tab that have #N/A cell values (see NOTE below for how to create templates) 
4. Ensure all rows have email cell filled out. If email is missing find the new hires email in iiq. 
4. Using Phone Number assset table in ServiceNow, check if numbers are active in Genesys and paste values into template for rows that are blank(users that do not need numbers will have 'NO PHONE' or 'Teams'
5. In the template sheet, check for any rows that have 'TEAMS' in the phone_work column. Assign those tasks in ServiceNow to TLM group and Kevin White, add 'teams' to worknotes
7. In ServiceNow close all tasks that were exported appropriately by selecting if they need a number, if user needed a number, paste the number value you used in the excel sheet into the task. This will update the phone number asset table.                                                                                                                                               
8. Go to 'Template Final' tab of excel sheet and copy contents into a new csv workbook.
10. Go to 'WebRTCTemplate' tab of excel sheet and copy contents into a new csv workbook.                                                                                                                                                 
9. Manually check through contents and make sure everything lines up. Navigate to GenesysCloud and bulk import the csv in within the people section.
10. Run the 'Template Final' csv you created through the 'validatenumbers.py' script
11. Run the 'WebRTCTemplate' csv you created through the 'webrtc_automation.py' script                                                                                                                                                
12. check for any api error responses and address them appropriately.                                                                                                                                                                                                                                                  
                                                                                                                                                
                                                                                                                                                
NOTE - CREATING TEMPLATES: 
templates are created off a job title basis, usually when a new title comes though, the list of roles they require is already predefined under a different title. 
The users who do not require roles/numbers: 
-users with a contractor title(with the exception of app support)     
-users with an evaluator title
-users under the prelicensure department                                                                                                                                                
-users whose AML requires a team number
OTHER IMPORTANT NOTE : any variation of a course instructor/ program mentor title will only require the Faculty Agent role with the division under their college. i.e course instructor - H title under the college of IT will only require facultyagent[InformationTechnologyCI] role. 
                                                                                                                                              
You may also user the user_template_automation.py script to create templates, however, you must validate the AML provided and confirm the template does not incorrectly apply any additional roles that are out of scope.
