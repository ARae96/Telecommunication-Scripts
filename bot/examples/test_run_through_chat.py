#!/usr/bin/env python
# =============================================================================
# Test: Run a Script Through the Chat Interface
# =============================================================================
# This test verifies that we can run a real script through the chat interface
# and get back the results. Run this from the repo root:
#
#   python bot/examples/test_run_through_chat.py
# =============================================================================

import sys
from pathlib import Path

# Add the repo root to the path so we can import the bot package.
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

from bot.crew_bot_session import CrewBotSession


def test_run_through_chat():
    """Test running a real script through the chat interface."""
    
    print("=" * 75)
    print("RUN SCRIPT THROUGH CHAT INTERFACE TEST")
    print("=" * 75)
    print()
    
    # Create a bot session.
    session = CrewBotSession(".")
    
    # List scripts first so we know what is available.
    print("Available scripts:")
    print("-" * 75)
    result = session.chat_handler.handle_message("list")
    print(result)
    print()
    
    # Now try to run a script. We will test with a script that should
    # exit cleanly without taking a long time.
    print("Running: Add_Permissions_to_Roles")
    print("-" * 75)
    
    # Use the chat handler to parse and run the command.
    result = session.chat_handler.handle_message("run Add_Permissions_to_Roles")
    print(result)
    print()
    
    print("=" * 75)
    print("TEST COMPLETE")
    print("=" * 75)


if __name__ == "__main__":
    test_run_through_chat()
