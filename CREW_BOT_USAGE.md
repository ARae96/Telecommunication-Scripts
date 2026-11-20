# Script Bot Usage Guide - Crew Chat

The script bot helps you discover and run Python scripts in the Script Development repository from Crew. Instead of opening the terminal, you can type commands in Crew chat.

## Quick Start

Type these commands in Crew chat with the bot:

### List All Available Scripts

```
list
```

The bot shows every script in the `src/` directory with its description.

### Get Info About a Script

```
info Add_Permissions_to_Roles
```

The bot shows the script's full description, when it was last updated, and how to run it.

### Run a Script

```
run Add_Permissions_to_Roles
```

The bot runs the script and reports the result. The bot captures all output and tells you how long it took.

### Run a Script With Arguments

```
run My_Script arg1 arg2
```

The bot passes arguments to the script. Arguments are space-separated.

## How It Works

1. You type a command in Crew chat.
2. The bot receives your command and parses it.
3. The bot runs the script (if you asked for "run").
4. The script runs in a safe, isolated process.
5. The bot captures all output and any errors.
6. The bot sends the result back to Crew chat.

The bot runs scripts with a 5-minute timeout. If a script takes longer than 5 minutes, the bot stops it and tells you it timed out.

## Command Reference

| Command | What It Does |
|---------|--------------|
| `list` | Show all available scripts |
| `info <name>` | Show details about a script |
| `run <name>` | Run a script and show the result |
| `run <name> arg1 arg2` | Run a script with arguments |
| `help` | Show this help text |

## Understanding Script Output

When you run a script, the bot tells you:

- **Success or failure:** The script succeeded (exit code 0) or failed.
- **Time taken:** How many seconds the script ran.
- **Output:** Everything the script printed.
- **Errors:** Any errors the script produced (stderr).

If the script fails, look at the error message. It usually tells you what went wrong. For example, if a required `.env` file is missing, the error says so.

## Creating Your Own Scripts

See `.kiro/steering/script-bot-creation.md` for full guidance on writing scripts that work with the bot.

Quick checklist:

1. Create a `.py` file in `src/` with a clear name.
2. Add a docstring at the very top (the bot uses this as the description).
3. Write the script to take command-line arguments with `sys.argv`.
4. Return exit code 0 on success, non-zero on failure.
5. Print clear messages so the team knows what happened.

## Examples

### See All Scripts

```
You: list

Bot: Available scripts (5 total):
  • Add_Permissions_to_Roles — Add permissions to Genesys Cloud roles
  • Export_User_Data — Export user data from Genesys Cloud to CSV
  • Check_Adherence — Check current adherence for management units
  • Backup_WFM_Data — Backup Workforce Management data
  • Cleanup_Old_Logs — Remove old log files
```

### Run a Script

```
You: run Add_Permissions_to_Roles

Bot: Running Add_Permissions_to_Roles...
  ✓ Success (exit code 0, 2.3 seconds)
  
  Output:
  Starting Add_Permissions_to_Roles...
  Loaded 5 roles from Genesys Cloud.
  Added permissions to 3 roles.
  Done. 2 changes made.
```

### Script Failed

```
You: run Export_User_Data

Bot: Running Export_User_Data...
  ✗ Failed (exit code 1, 0.5 seconds)
  
  Error:
  Error: .env file not found
  Please copy .env.example to .env and add your credentials.
```

## Troubleshooting

### Script timed out

If the bot says the script timed out, it ran for longer than 5 minutes. Either:

- Check if the script is stuck waiting for input.
- Check if the script is doing something very slow (like downloading a lot of data).
- Run the script manually from the terminal to debug.

### Script not found

If the bot says the script does not exist, check:

- The script name is spelled correctly (case matters).
- The script is in the `src/` directory.
- The `.py` extension is not included in the command.

### "Error: Could not run the script"

The bot tried to run the script but something went wrong before it started. This usually means:

- The script file is missing or corrupt.
- Python is not installed correctly.
- A required package is missing.

Try running the script manually from the terminal to see the full error.

## Team Workflow

The bot works best when:

1. Everyone names scripts clearly (e.g., `Add_Permissions_to_Roles` not `x`).
2. Scripts have docstrings at the top so the bot can show descriptions.
3. Scripts handle errors with clear messages.
4. Team members document what each script does in `.kiro/steering/script-bot-creation.md`.

## For Developers

See `bot/README.md` for technical details about how the bot works.

To run the bot for testing:

```bash
python crew_bot.py
```

The bot starts an interactive session where you can type commands to test it locally.
