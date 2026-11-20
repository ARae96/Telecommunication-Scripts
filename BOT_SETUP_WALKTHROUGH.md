# Script Bot Setup Walkthrough

This guide walks your team through setting up and using the script bot to discover and run Python scripts from Crew chat.

## Part 1: Before You Start

Make sure you have:

- Python 3.8 or newer on your machine
- The Communication-Infrastructure repo cloned from GitHub
- Your personal `.env` file with Genesys credentials:
  - `GENESYS_CLOUD_CLIENT_ID`
  - `GENESYS_CLOUD_CLIENT_SECRET`

Your `.env` file goes in the `Dev Tools/Python Scipts/` folder.

## Part 2: Test the Bot Locally

### Step 1: Open a terminal

```bash
cd "Dev\ Tools/Python\ Scipts"
```

(Replace with the actual path where you cloned the Communication-Infrastructure repo.)

### Step 2: List all available scripts

```bash
python -c "
from bot.manager import ScriptBotManager
manager = ScriptBotManager('.')
manager.refresh_scripts()
print(manager.list_available_scripts())
"
```

You should see a list of all scripts in `Sandbox/` and `Validated/` folders:

```
Available scripts:

  - Add_Permissions_to_Roles: Assigns permissions to roles in Genesys Cloud
  - Role_Migration: Migrates roles from one business unit to another
  - ...
```

### Step 3: Get info about a specific script

```bash
python -c "
from bot.manager import ScriptBotManager
manager = ScriptBotManager('.')
info = manager.get_script_info('Add_Permissions_to_Roles')
if info:
    print(f'Script: {info.name}')
    print(f'Path: {info.path}')
    print(f'Description: {info.description}')
"
```

### Step 4: Run a test script

```bash
python -c "
from bot.manager import ScriptBotManager
manager = ScriptBotManager('.')
result = manager.run_script('UserID_to_Name')
print(f'Success: {result.success}')
print(f'Time: {result.elapsed_seconds:.2f}s')
print(f'Output: {result.stdout[:200]}...')
"
```

If this works, your local setup is ready.

## Part 3: Run Scripts from Crew Chat

### Step 1: Open Kiro Crew

In your browser, open the Kiro Crew dashboard.

### Step 2: Go to Bots

Click **Bots** in the left menu.

### Step 3: Open Ramona (the bot)

Click on **Ramona** to open the bot conversation.

### Step 4: List scripts

Type in the chat:

```
list scripts
```

The bot replies with all 16 scripts in `src/`.

### Step 5: Get script details

Type:

```
info Add_Permissions_to_Roles
```

The bot shows the script name, description, file path, and size.

### Step 6: Run a script

Type:

```
run UserID_to_Name
```

The bot runs the script and shows the output (first 1000 characters). Output appears in the chat.

### Step 7: Run a script with arguments

Some scripts take arguments. Type:

```
run Script_Name arg1 arg2
```

Arguments are passed to the script in order.

## Part 4: Understanding the Bot Output

### Success case

```
Script: UserID_to_Name
Status: ✅ Success
Time: 2.3s
Output:
  User_1: John Doe
  User_2: Jane Smith
```

### Error case

```
Script: Add_Permissions_to_Roles
Status: ❌ Failed
Error: Script not found
```

### Timeout case

```
Script: Long_Running_Script
Status: ⏱️ Timeout
Message: Script exceeded 300 seconds (5 minutes)
```

## Part 5: Writing a New Script

Want to create a new script that the bot discovers automatically? See `.kiro/steering/script-bot-creation.md` for the template and guidelines.

Key rules:

1. Put your script in `Sandbox/<YourName>/` folder (or `Sandbox/Shared Scripts/` for team scripts)
2. Add a module docstring at the top (the first `"""..."""`)
3. First line of docstring is the description the bot shows
4. Import shared modules for standard patterns
5. Use `.env` for credentials

Example:

```python
# =============================================================================
# My New Script - What it does
# =============================================================================
# This script does something useful with Genesys Cloud. It takes user input
# for role IDs and outputs results to a CSV file.
#
# Output (files written to current directory):
#   results_<timestamp>.csv
#      One row per role processed.
# =============================================================================

from confirm_prompt import user_confirms
from genesys_common import get_client, handle_auth_error

# ... rest of script
```

Save it as `Sandbox/<YourName>/My_New_Script.py` or `Sandbox/Shared Scripts/My_New_Script.py`. The bot finds it automatically.

## Part 6: Troubleshooting

### Bot doesn't find a script

Make sure:
- Script is in `Sandbox/` or `Validated/` (the bot scans these folders)
- Script filename matches the name you use in chat (case-sensitive)
- Script name does not start with `_` (those are skipped as helpers)

### Script runs but hangs

Scripts have a 5-minute timeout. If a script takes longer, it times out and the bot kills it.

### Script fails with "credentials error"

Check:
- `.env` file exists in repo root
- `GENESYS_CLOUD_CLIENT_ID` and `GENESYS_CLOUD_CLIENT_SECRET` are set
- Credentials are correct

### Bot says "Command not recognized"

The bot only understands three commands:
- `list scripts` — show all scripts
- `info <script_name>` — show details for one script
- `run <script_name> [args...]` — run a script

Make sure you spell the command exactly.

## Part 7: Next Steps

1. **Test locally** — follow Part 2 to confirm everything works
2. **Test in Crew** — follow Part 3 to run scripts from chat
3. **Share with team** — send this walkthrough to your team members
4. **Gather feedback** — ask the team what scripts they need or what's missing

## Questions?

See the full README at `bot/README.md` for technical details.
