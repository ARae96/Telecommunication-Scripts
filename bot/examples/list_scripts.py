#!/usr/bin/env python
# =============================================================================
# Example: List Available Scripts
# =============================================================================
# This example shows how to use the script bot to discover and list all
# available scripts in the repository. Run this from the repo root:
#
#   python bot/examples/list_scripts.py
# =============================================================================

import sys
import json
from pathlib import Path

# Add the repo root to the path so we can import the bot package.
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

from bot.manager import ScriptBotManager


def main():
    """List all available scripts and show the bot status."""
    
    # Create a bot manager for the current repository.
    # Use '.' for the current directory, or pass an absolute path.
    manager = ScriptBotManager('.')
    
    # Refresh the list of scripts (scan the src/ directory).
    print("Scanning for scripts...")
    manager.refresh_scripts()
    print()
    
    # Show the list in a readable format.
    print(manager.list_available_scripts())
    print()
    
    # Show the bot's status (count of scripts, last refresh, etc.).
    print("Bot Status:")
    print(json.dumps(manager.get_status(), indent=2))


if __name__ == "__main__":
    main()
