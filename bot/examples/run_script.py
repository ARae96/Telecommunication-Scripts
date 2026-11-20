#!/usr/bin/env python
# =============================================================================
# Example: Run a Script Through the Bot
# =============================================================================
# This example shows how to use the script bot to run a script and see what
# happened (output, errors, timing). Run this from the repo root:
#
#   python bot/examples/run_script.py Add_Permissions_to_Roles
#
# You can also pass arguments to the script:
#
#   python bot/examples/run_script.py Script_Name arg1 arg2 ...
# =============================================================================

import sys
import json
from pathlib import Path

# Add the repo root to the path so we can import the bot package.
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

from bot.manager import ScriptBotManager


def main():
    """Run a script and show the results."""
    
    if len(sys.argv) < 2:
        print("Usage: python run_script.py <script_name> [args...]")
        print()
        print("Example:")
        print("  python run_script.py Add_Permissions_to_Roles")
        sys.exit(1)
    
    script_name = sys.argv[1]
    args = sys.argv[2:] if len(sys.argv) > 2 else None
    
    # Create a bot manager for the current repository.
    manager = ScriptBotManager('.')
    
    # Show what we are about to run.
    print(f"Running: {script_name}")
    if args:
        print(f"Arguments: {' '.join(args)}")
    print()
    
    # Run the script.
    result = manager.run_script(script_name, args=args)
    
    # Show the result.
    print("=== Result ===")
    print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Exit code: {result.return_code}")
    print(f"Time: {result.elapsed_seconds:.2f} seconds")
    print()
    
    if result.stdout:
        print("=== Output ===")
        print(result.stdout)
        print()
    
    if result.stderr:
        print("=== Errors ===")
        print(result.stderr)
        print()
    
    # Show the full result as JSON for logging or automation.
    print("=== Full Result (JSON) ===")
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
