# =============================================================================
# Chat Handler - Parse commands from Crew chat and route them to the bot
# =============================================================================
# This module handles chat messages from team members in Crew. It reads what
# the user types, figures out what they want (list scripts, show details, or
# run one), and sends it to the right bot function. Then it formats the
# results back into a message the chat can show.
#
# Commands understood:
#   list - Show all available scripts
#   info <script_name> - Show details about a script
#   run <script_name> [args...] - Run a script with optional arguments
#
# Output (to chat):
#   Formatted messages with script lists, details, and run results.
# =============================================================================

import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from .manager import ScriptBotManager
from .script_executor import ExecutionResult
from .github_integration import ScriptFile


# --- Command Parsing ---------------------------------------------------------

@dataclass
class ChatCommand:
    """A command parsed from what the user typed in chat."""
    command: str  # "list", "info", or "run"
    script_name: Optional[str] = None
    args: Optional[List[str]] = None
    
    def __str__(self) -> str:
        """Show the command in a readable way."""
        if self.command == "list":
            return "list"
        elif self.command == "info":
            return f"info {self.script_name}"
        elif self.command == "run":
            args_str = f" {' '.join(self.args)}" if self.args else ""
            return f"run {self.script_name}{args_str}"
        return self.command


# --- Chat Handler -----------------------------------------------------------

class ChatHandler:
    """Understands what the user wants from their chat message and runs it."""
    
    def __init__(self, repo_path: str = "."):
        """Set up the chat handler for a repository.
        
        We create a bot manager that will handle listing scripts, getting
        details, and running them. The repo_path should point to the root
        of the Script Development repository.
        """
        self.manager = ScriptBotManager(repo_path)
        self.manager.refresh_scripts()
    
    def parse_message(self, message: str) -> Optional[ChatCommand]:
        """Parse a chat message and turn it into a command.
        
        We look at the first word to see what the user wants. If it is "list",
        we return a list command. If it is "info", we expect a script name
        next. If it is "run", we expect a script name and optional arguments.
        
        Returns a ChatCommand if the message looks right, or None if we
        do not understand it.
        """
        if not message or not message.strip():
            return None
        
        parts = message.strip().split()
        command = parts[0].lower()
        
        if command == "list":
            return ChatCommand(command="list")
        
        elif command == "info":
            if len(parts) < 2:
                return None
            script_name = parts[1]
            return ChatCommand(command="info", script_name=script_name)
        
        elif command == "run":
            if len(parts) < 2:
                return None
            script_name = parts[1]
            args = parts[2:] if len(parts) > 2 else None
            return ChatCommand(command="run", script_name=script_name, args=args)
        
        return None
    
    def handle_command(self, command: ChatCommand) -> str:
        """Run a command and return the result as a message.
        
        We take a parsed command and actually do what it asks. If the user
        wants to list scripts, we list them. If they want details about one,
        we show the details. If they want to run one, we run it and show
        what happened.
        
        Returns a string message that is ready to send back to the chat.
        """
        if command.command == "list":
            return self._handle_list()
        elif command.command == "info":
            return self._handle_info(command.script_name)
        elif command.command == "run":
            return self._handle_run(command.script_name, command.args)
        else:
            return "I do not understand that command. Try: list, info <script>, or run <script>"
    
    def handle_message(self, message: str) -> str:
        """Handle a chat message end-to-end.
        
        Parse the message into a command, run the command, and return a
        result message. If we cannot understand the message, we return a
        help message.
        
        This is the main entry point that the Crew chat integration calls.
        """
        command = self.parse_message(message)
        
        if command is None:
            return self._format_help()
        
        return self.handle_command(command)
    
    # --- Internal Handlers ---------------------------------------------------
    
    def _handle_list(self) -> str:
        """Handle a 'list' command and return the scripts."""
        scripts = self.manager.available_scripts
        
        if not scripts:
            self.manager.refresh_scripts()
            scripts = self.manager.available_scripts
        
        if not scripts:
            return "No scripts found in the repository."
        
        lines = ["Available scripts:\n"]
        for i, script in enumerate(scripts, 1):
            desc = script.description or "(no description)"
            lines.append(f"{i}. **{script.name}** - {desc}")
        
        lines.append("")
        lines.append("Run a script with: `run Script_Name`")
        lines.append("Get details with: `info Script_Name`")
        
        return "\n".join(lines)
    
    def _handle_info(self, script_name: Optional[str]) -> str:
        """Handle an 'info' command and return details about one script."""
        if not script_name:
            return "You need to tell me which script you want to know about. Try: `info Script_Name`"
        
        script = self.manager.get_script_info(script_name)
        
        if not script:
            return f"Script `{script_name}` not found. Try `list` to see what is available."
        
        lines = [f"**{script.name}**\n"]
        lines.append(f"Description: {script.description or '(no description)'}")
        lines.append(f"Path: `{script.path}`")
        lines.append(f"Size: {script.size_bytes:,} bytes")
        lines.append(f"Modified: {script.modified_at}")
        lines.append("")
        lines.append(f"To run this script: `run {script.name}`")
        
        return "\n".join(lines)
    
    def _handle_run(
        self,
        script_name: Optional[str],
        args: Optional[List[str]]
    ) -> str:
        """Handle a 'run' command and run the script."""
        if not script_name:
            return "You need to tell me which script to run. Try: `run Script_Name`"
        
        # Check that the script exists before running.
        script = self.manager.get_script_info(script_name)
        if not script:
            return f"Script `{script_name}` not found. Try `list` to see what is available."
        
        # Run the script.
        result = self.manager.run_script(script_name, args=args)
        
        # Format the result for the chat.
        return self._format_execution_result(result)
    
    def _format_execution_result(self, result: ExecutionResult) -> str:
        """Turn an execution result into a readable chat message."""
        lines = []
        
        # Status header.
        status_emoji = "✅" if result.success else "❌"
        lines.append(f"{status_emoji} **{result.script_name}**\n")
        
        # Basic info.
        lines.append(f"Status: {'Success' if result.success else 'Failed'}")
        lines.append(f"Exit code: {result.return_code}")
        lines.append(f"Time: {result.elapsed_seconds:.2f}s")
        lines.append("")
        
        # Output.
        if result.stdout:
            lines.append("**Output:**")
            lines.append("```")
            lines.append(result.stdout[:1000])  # Limit to 1000 chars.
            if len(result.stdout) > 1000:
                lines.append("... (output truncated)")
            lines.append("```")
            lines.append("")
        
        # Errors.
        if result.stderr:
            lines.append("**Errors:**")
            lines.append("```")
            lines.append(result.stderr[:1000])
            if len(result.stderr) > 1000:
                lines.append("... (errors truncated)")
            lines.append("```")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_help(self) -> str:
        """Return a help message explaining what the bot understands."""
        lines = [
            "I help you run scripts from the Script Development repository.\n",
            "**Commands:**",
            "• `list` - Show all available scripts",
            "• `info <script>` - Show details about a script",
            "• `run <script> [args...]` - Run a script with optional arguments",
            "",
            "**Examples:**",
            "```",
            "list",
            "info Add_Permissions_to_Roles",
            "run Add_Permissions_to_Roles",
            "```"
        ]
        return "\n".join(lines)
