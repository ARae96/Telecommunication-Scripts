#!/usr/bin/env python
# =============================================================================
# Test: Crew Chat Interface
# =============================================================================
# This test runs through the bot's chat interface to verify that the handler
# and Crew integration work together. Run this from the repo root:
#
#   python bot/examples/test_crew_chat.py
#
# It shows what the bot does when the user types different commands.
# =============================================================================

import sys
import json
from pathlib import Path

# Add the repo root to the path so we can import the bot package.
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

from bot.crew_bot_session import CrewBotSession


def test_crew_chat():
    """Test the Crew bot chat interface."""
    
    print("=" * 75)
    print("CREW BOT CHAT INTERFACE TEST")
    print("=" * 75)
    print()
    
    # Create a bot session.
    session = CrewBotSession(".")
    
    # Test 1: List scripts.
    print("TEST 1: List available scripts")
    print("-" * 75)
    
    result = session.chat_handler.handle_message("list")
    print(result)
    print()
    
    # Test 2: Get info about a script.
    print("TEST 2: Get info about a script")
    print("-" * 75)
    
    result = session.chat_handler.handle_message("info Add_Permissions_to_Roles")
    print(result)
    print()
    
    # Test 3: Try to get info about a script that does not exist.
    print("TEST 3: Try to get info about a nonexistent script")
    print("-" * 75)
    
    result = session.chat_handler.handle_message("info Fake_Script_Name")
    print(result)
    print()
    
    # Test 4: Show help.
    print("TEST 4: Invalid command (should show help)")
    print("-" * 75)
    
    result = session.chat_handler.handle_message("help")
    print(result)
    print()
    
    # Test 5: Empty message.
    print("TEST 5: Empty message")
    print("-" * 75)
    
    result = session.chat_handler.handle_message("")
    print(result)
    print()
    
    # Test 6: Show status.
    print("TEST 6: Bot status")
    print("-" * 75)
    
    status = session.get_status()
    print(json.dumps(status, indent=2))
    print()
    
    print("=" * 75)
    print("TEST COMPLETE")
    print("=" * 75)


if __name__ == "__main__":
    test_crew_chat()
