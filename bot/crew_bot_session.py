# =============================================================================
# Crew Bot Session - Main entry point for running the bot in Crew
# =============================================================================
# This module wires together the chat handler and Slack integration to create
# a bot session that can be run inside the Crew chat interface. When the user
# types a message in Crew, this session receives it, parses it with the chat
# handler, and sends the result back to the chat through the Slack integration.
#
# Output (to chat):
#   Messages with script listings, details, and run results from commands.
# =============================================================================

import logging
from typing import Dict, Optional
from pathlib import Path

from .chat_handler import ChatHandler
from .slack_integration import CrewChatMessenger, parse_crew_message


# --- Logging Setup -----------------------------------------------------------

def setup_session_logging() -> logging.Logger:
    """Set up logging for the bot session."""
    logger = logging.getLogger("CrewBotSession")
    logger.setLevel(logging.DEBUG)
    
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    handler = logging.FileHandler(log_dir / "crew_bot_session.log")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    )
    logger.addHandler(handler)
    
    return logger


# --- Bot Session Class -------------------------------------------------------

class CrewBotSession:
    """A bot session that runs inside the Crew chat."""
    
    def __init__(self, repo_path: str = "."):
        """Set up a bot session for a repository.
        
        We create a chat handler that understands commands and a messenger
        that sends results back to the Crew chat. The repo_path should point
        to the root of the Script Development repository.
        
        Args:
            repo_path: Path to the Script Development repository.
        """
        self.repo_path = repo_path
        self.chat_handler = ChatHandler(repo_path)
        self.messenger = CrewChatMessenger()
        self.logger = setup_session_logging()
        self.logger.info(f"Bot session started for repo: {repo_path}")
    
    def handle_user_message(
        self,
        message: str,
        user_id: Optional[str] = None,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None
    ) -> bool:
        """Handle a message from a user in the Crew chat.
        
        We receive the message text, figure out what command the user wants
        to run, execute the command through the chat handler, and send the
        result back to the Crew chat.
        
        Args:
            message: The text the user typed.
            user_id: The user's Crew ID (for logging and context).
            channel: The Crew chat channel where the message came from.
            thread_ts: The thread ID (for threaded replies, optional).
        
        Returns:
            True if the message was handled successfully, False if an error
            occurred.
        """
        try:
            self.logger.info(f"Received message from {user_id or 'unknown'}")
            self.logger.debug(f"Message: {message}")
            
            # Parse and handle the message through the chat handler.
            result = self.chat_handler.handle_message(message)
            
            self.logger.info("Message handled successfully")
            
            # Send the result back to the Crew chat.
            sent = self.messenger.send_command_result(
                command=message,
                result=result,
                channel=channel,
                user_id=user_id
            )
            
            if not sent:
                self.logger.warning("Failed to send result to chat")
                return False
            
            return True
        
        except Exception as e:
            self.logger.exception(f"Error handling message: {str(e)}")
            
            # Try to send an error message back to the chat.
            self.messenger.send_error(
                f"An error occurred while processing your command: {str(e)}",
                channel=channel
            )
            
            return False
    
    def handle_message_data(
        self,
        message_data: Dict,
        user_id: Optional[str] = None,
        channel: Optional[str] = None
    ) -> bool:
        """Handle a message from the Crew API.
        
        The Crew chat API sends messages as dictionaries with structured
        fields. We extract the message text from the dictionary and handle
        it like a regular user message.
        
        Args:
            message_data: A dictionary with the message data from Crew.
            user_id: The user's Crew ID (optional).
            channel: The Crew chat channel (optional).
        
        Returns:
            True if handled successfully, False otherwise.
        """
        message = parse_crew_message(message_data)
        
        if not message:
            self.logger.warning("Could not parse message data from Crew")
            return False
        
        thread_ts = message_data.get("thread_ts")
        
        return self.handle_user_message(
            message=message,
            user_id=user_id,
            channel=channel,
            thread_ts=thread_ts
        )
    
    def get_status(self) -> Dict:
        """Return the status of this bot session."""
        status = self.chat_handler.manager.get_status()
        status["session"] = "active"
        return status


# --- Crew Integration Entry Point -------------------------------------------

class CrewBotIntegration:
    """The main entry point for running the bot in Crew.
    
    This class handles the integration with the Crew platform. When Crew
    calls the bot, it goes through this class to create or retrieve a
    session and route the message to it.
    """
    
    def __init__(self, repo_path: str = "."):
        """Set up the Crew integration.
        
        Args:
            repo_path: Path to the Script Development repository.
        """
        self.repo_path = repo_path
        self.sessions: Dict[str, CrewBotSession] = {}
        self.logger = setup_session_logging()
    
    def get_or_create_session(self, session_id: str) -> CrewBotSession:
        """Get an existing session or create a new one.
        
        Each Crew conversation gets its own bot session so we can track
        history and state separately for each user or channel.
        
        Args:
            session_id: A unique ID for the Crew session (user ID or channel).
        
        Returns:
            A CrewBotSession for this conversation.
        """
        if session_id not in self.sessions:
            self.sessions[session_id] = CrewBotSession(self.repo_path)
        
        return self.sessions[session_id]
    
    def handle_crew_message(
        self,
        message: str,
        session_id: str,
        user_id: Optional[str] = None,
        channel: Optional[str] = None
    ) -> str:
        """Handle a message from the Crew chat.
        
        This is the main entry point that Crew calls when a user sends a
        message to the bot. We get or create a session, handle the message,
        and return the result.
        
        Args:
            message: The text the user typed.
            session_id: A unique ID for this Crew session.
            user_id: The user's Crew ID (optional).
            channel: The Crew chat channel (optional).
        
        Returns:
            The result message to send back to the user.
        """
        session = self.get_or_create_session(session_id)
        
        # Handle the message. If it fails, we get back False, but the session
        # already sent an error message to the chat, so we just return a
        # generic message here.
        session.handle_user_message(
            message=message,
            user_id=user_id,
            channel=channel
        )
        
        # Note: In a real Crew integration, the result message is already
        # sent by the messenger. This return value is for testing or logging.
        return "Message processed"


# --- Example Usage -----------------------------------------------------------

if __name__ == "__main__":
    # Example of how to use the bot session.
    
    session = CrewBotSession(".")
    
    print("Script Bot Session Started")
    print("Type commands to test the bot:")
    print("  list")
    print("  info Add_Permissions_to_Roles")
    print("  run Add_Permissions_to_Roles")
    print("  exit")
    print()
    
    while True:
        user_input = input("You: ").strip()
        
        if user_input.lower() == "exit":
            break
        
        if not user_input:
            continue
        
        # Handle the user's message.
        session.handle_user_message(user_input, user_id="test_user")
        
        # In a real Crew integration, the messenger sends the result to chat.
        # In this test, we just show a placeholder.
        print("(Result sent to chat)")
        print()
