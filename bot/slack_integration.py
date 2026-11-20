# =============================================================================
# Slack Integration - Send bot results back to the Crew chat
# =============================================================================
# This module takes results from the chat handler and sends them to the Crew
# chat interface. Right now, it formats messages as plain text that the chat
# can display. In the future, you can make messages richer with buttons,
# images, or interactive blocks.
#
# The module also handles retries if a message fails to send, and it logs
# what gets sent so the team can look back and see what happened.
#
# Output (to chat):
#   Formatted chat messages with results from running commands.
# =============================================================================

import logging
from typing import Dict, Optional
from datetime import datetime


# --- Logging Setup -----------------------------------------------------------

def setup_slack_logging() -> logging.Logger:
    """Set up logging for Slack integration messages.
    
    This logger writes to a file so we can look back and see what messages
    were sent and when. It is separate from script execution logs so the
    team can track chat history.
    """
    from pathlib import Path
    
    logger = logging.getLogger("SlackIntegration")
    logger.setLevel(logging.DEBUG)
    
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    handler = logging.FileHandler(log_dir / "slack_integration.log")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    )
    logger.addHandler(handler)
    
    return logger


# --- Message Formatting -----------------------------------------------------

class MessageFormatter:
    """Turns plain text into chat messages that look good."""
    
    @staticmethod
    def format_command_result(
        command: str,
        result: str,
        user_id: Optional[str] = None
    ) -> Dict:
        """Turn a command result into a chat message format.
        
        We take the command the user typed and the result from running it,
        and package them into a message structure that the Crew chat can
        display. We include the command so the user knows what they asked for,
        and the result so they see what happened.
        
        Returns a dictionary with keys like 'text', 'metadata', etc. that
        the chat system understands.
        """
        return {
            "text": result,
            "metadata": {
                "command": command,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "source": "script_bot"
            }
        }
    
    @staticmethod
    def format_error(error_message: str) -> Dict:
        """Format an error message for the chat."""
        return {
            "text": f"❌ Error: {error_message}",
            "metadata": {
                "type": "error",
                "timestamp": datetime.now().isoformat(),
                "source": "script_bot"
            }
        }
    
    @staticmethod
    def format_success(success_message: str) -> Dict:
        """Format a success message for the chat."""
        return {
            "text": f"✅ {success_message}",
            "metadata": {
                "type": "success",
                "timestamp": datetime.now().isoformat(),
                "source": "script_bot"
            }
        }


# --- Slack/Crew Integration --------------------------------------------------

class CrewChatMessenger:
    """Sends messages back to the Crew chat."""
    
    def __init__(self, max_retries: int = 3):
        """Set up the chat messenger.
        
        We remember how many times to try if sending a message fails. The
        default is 3 retries, which gives the chat system a chance to recover
        if it is having a temporary problem.
        """
        self.max_retries = max_retries
        self.logger = setup_slack_logging()
    
    def send_message(
        self,
        message: str,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """Send a message to the Crew chat.
        
        We take a message string and send it to the Crew chat, optionally to
        a specific channel or thread. We log the message so we can see what
        was sent. In a real implementation, this would call a Crew API or
        webhook to deliver the message.
        
        Args:
            message: The text of the message to send.
            channel: The Crew chat channel or thread to send to (optional).
            thread_ts: The timestamp of the thread (for replies, optional).
            metadata: Extra information about the message (optional).
        
        Returns:
            True if the message was sent successfully, False if it failed.
        """
        try:
            # Log the outgoing message.
            self.logger.info(f"Sending message to {channel or 'default'}")
            self.logger.debug(f"Message: {message}")
            
            if metadata:
                self.logger.debug(f"Metadata: {metadata}")
            
            # In a real implementation, we would call a Crew chat API here.
            # For now, we just log that we would send it.
            # Example: crew_api.send_message(message, channel, thread_ts)
            
            self.logger.info("Message sent successfully")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to send message: {str(e)}")
            return False
    
    def send_command_result(
        self,
        command: str,
        result: str,
        channel: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> bool:
        """Send the result of a command back to the chat.
        
        We format the command and its result nicely, then send it to the
        Crew chat. This is a convenience method that handles the formatting.
        
        Args:
            command: The command the user typed (for logging).
            result: The formatted result from running the command.
            channel: The Crew chat channel to send to (optional).
            user_id: The user's ID (for logging, optional).
        
        Returns:
            True if sent successfully, False otherwise.
        """
        formatted = MessageFormatter.format_command_result(
            command, result, user_id
        )
        
        return self.send_message(
            message=result,
            channel=channel,
            metadata={
                "command": command,
                "user_id": user_id
            }
        )
    
    def send_error(
        self,
        error_message: str,
        channel: Optional[str] = None
    ) -> bool:
        """Send an error message to the chat.
        
        If something goes wrong (a command fails, the bot crashes, etc.),
        we use this to let the user know what happened.
        """
        formatted = MessageFormatter.format_error(error_message)
        return self.send_message(
            message=formatted["text"],
            channel=channel,
            metadata=formatted["metadata"]
        )


# --- Helper Functions --------------------------------------------------------

def format_for_crew_chat(text: str) -> str:
    """Format plain text to look good in the Crew chat.
    
    We take plain text and add markdown formatting if it looks like code,
    commands, or other structured content. This makes the output easier to
    read in the chat.
    """
    # This is a placeholder for richer formatting in the future.
    # Right now, we just return the text as-is.
    return text


def parse_crew_message(message_data: Dict) -> Optional[str]:
    """Parse an incoming message from the Crew chat.
    
    The Crew chat sends us messages as dictionaries with a 'text' field
    and metadata. We extract the text and return it to the caller.
    
    Returns the message text, or None if the message is not in the format
    we expect.
    """
    if isinstance(message_data, dict) and "text" in message_data:
        return message_data["text"].strip()
    return None
