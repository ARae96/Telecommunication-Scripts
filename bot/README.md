# Script Bot - Team Script Manager

The script bot helps the team discover, run, and manage Python scripts in the Script Development repository.

## What It Does

The bot:

1. **Discovers scripts** in the `src/` directory automatically.
2. **Runs scripts safely** in isolated processes with timeouts.
3. **Captures output** from every script run (stdout, stderr, timing).
4. **Logs execution history** so the team can see what ran and when.
5. **Provides guidance** for creating new scripts that work with the bot.

## Quick Start

### List Available Scripts

```python
from bot.manager import ScriptBotManager

manager = ScriptBotManager('.')  # Repository root
manager.refresh_scripts()
print(manager.list_available_scripts())
```

### Run a Script

```python
manager = ScriptBotManager('.')
result = manager.run_script("Add_Permissions_to_Roles")

if result.success:
    print(f"Script finished in {result.elapsed_seconds:.1f} seconds")
    print(result.stdout)
else:
    print(f"Error: {result.stderr}")
```

### Pass Arguments to a Script

```python
result = manager.run_script("Script_Name", args=["arg1", "arg2"])
```

## Structure

```
bot/
├── __init__.py                 # Package exports
├── github_integration.py        # Script discovery from repository
├── script_executor.py           # Safe script execution wrapper
├── manager.py                   # Central bot manager (main interface)
├── tests/
│   └── test_script_executor.py # 6 tests for discovery and execution
├── logs/                        # Execution logs (created on first run)
└── README.md                    # This file

.kiro/steering/
└── script-bot-creation.md       # Guidance for creating new scripts
```

## How Scripts Are Discovered

The bot looks for `.py` files in the `Sandbox/` and `Validated/` directories:

- **Script locations:** Scripts can be in:
  - `Sandbox/<YourName>/` (personal scripts)
  - `Sandbox/Shared Scripts/` (team scripts)
  - `Validated/` (approved scripts)
- **Script name:** Filename stem (e.g., `Add_Permissions_to_Roles.py` → `Add_Permissions_to_Roles`)
- **Description:** First line of the module docstring (the first `"""..."""` at the top of the file)
- **Metadata:** File size, creation date, last modified date

Scripts starting with `_` are skipped (those are usually helpers).

## How Scripts Are Executed

When you ask the bot to run a script:

1. The bot checks that the script file exists in `src/`.
2. The bot starts a new Python process running the script.
3. The bot waits up to 300 seconds (5 minutes) for the script to finish.
4. The bot captures everything the script prints to stdout and stderr.
5. The bot records the result: success/failure, exit code, output, and timing.
6. If the script times out, the bot kills it and returns an error.

### Error Codes

| Code | Meaning |
|------|---------|
| 0    | Script succeeded |
| -1   | Script file not found |
| -2   | Script timed out (exceeded 300 seconds) |
| -3   | Error running the script (unexpected exception) |
| 1-127 | Script's own exit code |

## Tests

Run the tests to verify everything works:

```bash
python -m pytest bot/tests/test_script_executor.py -v
```

Tests cover:

- ExecutionResult data structure
- Script discovery and execution
- Timeout handling
- Real script file existence
- Script docstring detection

All tests pass (6/6).

## Creating New Scripts

See `.kiro/steering/script-bot-creation.md` for full guidance. Quick summary:

1. Create a `.py` file in `src/` with a clear name.
2. Start with a header banner explaining what the script does.
3. Add a docstring at the very top (the bot uses this as the description).
4. Write functions with docstrings following the documentation-style rules.
5. Make sure the script runs as `python src/Your_Script_Name.py`.
6. Return exit code 0 on success, non-zero on failure.

Example header:

```python
# =============================================================================
# What This Script Does - Clear Title
# =============================================================================
# First sentence tells the team what the script does in plain language.
#
# Output (what files or data it creates):
#   A CSV file named output.csv
# =============================================================================
```

## Logging

Execution logs are written to `bot/logs/<script_name>.log` for each script run. Logs include:

- Timestamp of each log line
- Log level (DEBUG, INFO, WARNING, ERROR)
- The message

## Crew Chat Integration

The bot can be run inside Crew chat so team members can interact with it directly:

```python
from bot.crew_bot_session import CrewBotSession

session = CrewBotSession(".")
session.handle_user_message("list")
session.handle_user_message("info Add_Permissions_to_Roles")
session.handle_user_message("run Add_Permissions_to_Roles")
```

See `CREW_BOT_USAGE.md` for team documentation on using the bot in Crew.

## Future Enhancements

Possible next steps:

- [ ] Web dashboard to view available scripts and run them interactively.
- [ ] Script scheduling (run scripts on a schedule, like daily jobs).
- [ ] Script versioning and rollback.
- [ ] Output storage (save script output to files or databases).
- [ ] Permission checks (some scripts only for certain team members).
