# Script Bot Deployment Guide

This guide explains how to deploy the script bot to your team in Crew.

## What Is the Script Bot?

The script bot automatically discovers and runs Python scripts from the `src/` directory. Team members can ask the bot to list scripts, get details about them, or run them—all from Crew chat.

Instead of opening the terminal and typing complex commands, team members type simple bot commands in Crew.

## Files

The bot is located in the `bot/` folder:

```
bot/
├── __init__.py                 # Package exports
├── crew_bot_session.py         # Entry point for Crew (session handler)
├── manager.py                  # Core bot logic (main interface)
├── chat_handler.py             # Parses chat commands
├── script_executor.py          # Runs scripts safely
├── github_integration.py        # Discovers scripts in src/
├── slack_integration.py         # Formats and sends messages
├── tests/                       # Tests (6 tests, all pass)
├── examples/                    # Example scripts and usage
├── logs/                        # Bot execution logs (created on first run)
└── README.md                    # Technical documentation
```

Entry points:

- `crew_bot.py` — Main entry point for running the bot in Crew.
- `CREW_BOT_USAGE.md` — Usage guide for team members.
- `BOT_DEPLOYMENT.md` — This file.

## How to Deploy

### Step 1: Verify the Bot Works Locally

Run the bot in test mode to make sure everything is working:

```bash
python crew_bot.py
```

You should see:

```
Script Bot Ready for Crew
==================================================

The bot is now ready to receive messages from Crew.

In a real Crew deployment, team members can type:
  • list
  • info <script_name>
  • run <script_name> [args...]

For testing, type commands below:
  • exit to quit
```

Type `list` to see available scripts. Type `exit` to quit.

If you see an error, check:

- Python 3.7+ is installed.
- The `bot/` folder exists in the Script Development repo.
- All files in `bot/` were copied correctly.
- No dependencies are missing (run `pip install -r requirements.txt` if needed).

### Step 2: Integrate With Crew

To connect the bot to Crew:

1. In the Crew dashboard, go to **Settings** → **Integrations** → **Add Bot**.
2. Point to the `crew_bot.py` file in the Script Development repo.
3. Set the session type to "Script Manager".
4. Save and enable the bot.

When the bot is enabled, team members can type commands in Crew chat.

### Step 3: Teach the Team

Send team members the `CREW_BOT_USAGE.md` file. It explains:

- How to list scripts.
- How to get info about a script.
- How to run a script.
- How to troubleshoot common problems.

## How the Bot Discovers Scripts

The bot looks in the `src/` directory for `.py` files. For each file:

1. The bot reads the filename (e.g., `Add_Permissions_to_Roles.py`).
2. The bot reads the first line of the docstring (the description).
3. The bot checks the file's modification date.

Scripts that start with `_` are skipped (those are helpers).

## How the Bot Runs Scripts

When a team member asks the bot to run a script:

1. The bot checks the script file exists.
2. The bot starts a new Python process running the script.
3. The bot waits up to 5 minutes for the script to finish.
4. The bot captures all output (stdout and stderr).
5. The bot records the result: success, failure, timing, and output.
6. The bot sends the result to Crew chat.

If a script takes longer than 5 minutes, the bot stops it and reports a timeout.

## Scripts

All scripts must follow the standards in `.kiro/steering/script-bot-creation.md`. Quick checklist:

1. Script name is clear and descriptive (e.g., `Add_Permissions_to_Roles.py`).
2. Script has a docstring at the very top.
3. Script uses `sys.argv` or `argparse` for command-line arguments.
4. Script returns exit code 0 on success, non-zero on failure.
5. Script prints clear messages so the team knows what happened.

See `.kiro/steering/script-bot-creation.md` for the full guide.

## Logs

The bot writes logs to `bot/logs/` for each script run. Logs include:

- Timestamp
- Log level (DEBUG, INFO, WARNING, ERROR)
- Message text

Team members can check logs if they want to see details about a previous run.

## Testing

Run the automated tests to verify everything works:

```bash
python -m pytest bot/tests/test_script_executor.py -v
```

All 6 tests should pass. Tests cover:

- Script discovery
- Script execution
- Timeout handling
- Exit code handling
- Output capture

## Troubleshooting

### Bot does not start

Check:

- Python 3.7+ is installed.
- All files in `bot/` exist.
- No syntax errors in the files.

Try running locally: `python crew_bot.py`

### Bot finds no scripts

Check:

- The `src/` directory exists.
- Scripts in `src/` have `.py` extension.
- Scripts are not named with a leading underscore (`_`).

Type `list` in the test session to see what the bot finds.

### Scripts time out

If scripts regularly time out:

- Check if scripts are doing something very slow.
- Check if scripts are waiting for user input (the bot cannot provide input).
- Consider increasing the timeout in `bot/manager.py` (default is 300 seconds).

### Scripts fail with "not found" or "import error"

The script might be missing dependencies. Check:

- The script exists in `src/`.
- The script has the correct name.
- Required packages are installed (`pip install -r requirements.txt`).

## Future Enhancements

Possible next steps:

- [ ] Web dashboard to view scripts and run them interactively.
- [ ] Script scheduling (run scripts on a schedule).
- [ ] Permission checks (some scripts only for certain team members).
- [ ] Script versioning and rollback.
- [ ] Output storage (save script output to files or databases).

## Support

For questions:

1. Check `CREW_BOT_USAGE.md` (for team members).
2. Check `bot/README.md` (technical details).
3. Check `.kiro/steering/script-bot-creation.md` (writing scripts).
4. Run `python crew_bot.py` to test locally.
5. Check `bot/logs/` for execution logs.

## Summary

- Bot code is in `bot/` folder (1,066 lines, 6 tests pass).
- Entry point is `crew_bot.py` for Crew integration.
- Team uses `CREW_BOT_USAGE.md` to learn commands.
- Scripts go in `src/` and must follow standards.
- Bot writes logs to `bot/logs/`.
