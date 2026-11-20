# =============================================================================
# Script Bot - Main Entry Point for Crew Integration
# =============================================================================
# This is the main entry point for running the script bot inside Crew. When
# Crew calls the bot, it comes through this file. This file wires together
# the chat handler and Slack integration so the bot can receive messages from
# Crew users and send results back.
#
# Output (to Crew chat):
#   Messages listing scripts, showing script details, and reporting run results.
#
# See also:
#   bot/crew_bot_session.py (the session handler)
#   bot/manager.py (the core script manager)
# =============================================================================

import sys
from pathlib import Path

# Add the bot module to the path so we can import it.
bot_dir = Path(__file__).parent / "bot"
sys.path.insert(0, str(bot_dir))

from bot.crew_bot_session import CrewBotIntegration


# --- Main Entry Point --------------------------------------------------------

def main():
    """Start the bot and handle messages from Crew.
    
    This function sets up the CrewBotIntegration and runs an interactive
    loop to test the bot. In a real Crew deployment, Crew itself would call
    the handle_crew_message method directly through an API.
    """
    
    # Set up the bot integration for the current repository.
    repo_path = str(Path(__file__).parent)
    bot = CrewBotIntegration(repo_path)
    
    print("Script Bot Ready for Crew")
    print("=" * 50)
    print()
    print("The bot is now ready to receive messages from Crew.")
    print()
    print("In a real Crew deployment, team members can type:")
    print("  • list")
    print("  • info <script_name>")
    print("  • run <script_name> [args...]")
    print()
    print("For testing, type commands below:")
    print("  • exit to quit")
    print()
    
    while True:
        user_input = input("Test: ").strip()
        
        if user_input.lower() == "exit":
            print("Bot stopped.")
            break
        
        if not user_input:
            continue
        
        # Simulate a Crew message by calling the main handler.
        result = bot.handle_crew_message(
            message=user_input,
            session_id="test_session",
            user_id="test_user"
        )
        
        print(f"Result: {result}")
        print()


# --- Crew Bot API (called by Crew) -------------------------------------------

def handle_crew_message(message: str, session_id: str, user_id: str = None, 
                        channel: str = None) -> str:
    """Handle a message from Crew.
    
    This is the entry point that Crew calls when a user sends a message to
    the bot. It returns a result message to send back to the user.
    
    Args:
        message: The text the user typed.
        session_id: A unique ID for this Crew session.
        user_id: The user's Crew ID (optional).
        channel: The Crew chat channel (optional).
    
    Returns:
        A message to send back to the user.
    """
    repo_path = str(Path(__file__).parent)
    bot = CrewBotIntegration(repo_path)
    
    return bot.handle_crew_message(
        message=message,
        session_id=session_id,
        user_id=user_id,
        channel=channel
    )


# --- Script Entry Point ------------------------------------------------------

if __name__ == "__main__":
    main()
