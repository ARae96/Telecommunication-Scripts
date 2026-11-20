# =============================================================================
# Script Bot Manager - Central hub for script discovery and execution
# =============================================================================
# This is the main piece of the script bot. It brings together script discovery
# and execution, and keeps a list of what scripts are available and what the
# bot has run. This is where the team would talk to the bot to ask for help
# with scripts.
#
# Output (to memory):
#   A list of available scripts and a history of recent runs.
# =============================================================================

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from .github_integration import GitHubScriptDiscovery, ScriptFile
from .script_executor import ScriptExecutor, ExecutionResult


# --- Bot Manager -------------------------------------------------------------

class ScriptBotManager:
    """The central hub for managing scripts and running them."""
    
    def __init__(self, repo_path: str, timeout_seconds: int = 300):
        """Set up the bot manager for a repository.
        
        We create a discovery tool to find scripts and an executor to run
        them. We start with empty lists of scripts and execution history,
        which we fill in as the bot runs.
        """
        self.repo_path = Path(repo_path)
        self.discovery = GitHubScriptDiscovery(str(self.repo_path))
        self.executor = ScriptExecutor(str(self.repo_path), timeout_seconds)
        self.available_scripts: List[ScriptFile] = []
        self.execution_history: List[Dict] = []
    
    def refresh_scripts(self) -> List[ScriptFile]:
        """Find all scripts in the repository and update our list.
        
        We run the discovery again to see what scripts are available. This
        picks up any new scripts the team has added since the bot started.
        We keep the list sorted by name so the team always sees it the same
        way.
        """
        self.available_scripts = self.discovery.discover_scripts()
        return self.available_scripts
    
    def list_available_scripts(self, as_json: bool = False) -> str:
        """Return the list of available scripts to the team.
        
        If as_json is False, we return a readable list where each script shows
        its name and description. If as_json is True, we return the full
        metadata as JSON so other tools can use it.
        """
        if not self.available_scripts:
            self.refresh_scripts()
        
        if as_json:
            return self.discovery.list_scripts_json()
        
        # Build a readable list with names and descriptions.
        lines = ["Available scripts:", ""]
        for script in self.available_scripts:
            desc = script.description or "(no description)"
            lines.append(f"  - {script.name}: {desc}")
        
        return "\n".join(lines)
    
    def get_script_info(self, script_name: str) -> Optional[ScriptFile]:
        """Get detailed information about a specific script.
        
        If the script exists, we return its metadata (name, path, size, when
        it was last changed, and its description). If it does not exist,
        we return None.
        """
        if not self.available_scripts:
            self.refresh_scripts()
        
        return self.discovery.get_script_by_name(script_name)
    
    def run_script(
        self,
        script_name: str,
        args: Optional[List[str]] = None,
        log_result: bool = True
    ) -> ExecutionResult:
        """Run a script and return the result.
        
        We execute the script with any arguments the team passed. We capture
        everything it prints, measure how long it takes, and record the result
        in our execution history (if log_result is True).
        
        Returns an ExecutionResult that tells us if it succeeded, what it
        printed, and how long it took.
        """
        result = self.executor.execute(script_name, args)
        
        if log_result:
            self.execution_history.append({
                "script_name": script_name,
                "args": args or [],
                "result": result.to_dict(),
                "timestamp": datetime.now().isoformat()
            })
        
        return result
    
    def get_execution_history(
        self,
        script_name: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Return the history of recent script runs.
        
        If script_name is given, we return only runs of that script. We return
        up to limit runs (the default is the most recent 10).
        """
        history = self.execution_history
        
        if script_name:
            history = [
                h for h in history
                if h["script_name"] == script_name
            ]
        
        return history[-limit:]
    
    def get_status(self) -> Dict:
        """Return a quick status of the bot.
        
        This tells the team how many scripts the bot knows about, when it
        last looked for scripts, and how many times it has run a script.
        """
        return {
            "repository": str(self.repo_path),
            "scripts_available": len(self.available_scripts),
            "runs_recorded": len(self.execution_history),
            "status": "ready" if self.available_scripts else "needs refresh",
            "last_refresh": (
                self.execution_history[-1]["timestamp"]
                if self.execution_history
                else None
            )
        }


# --- Example Usage -----------------------------------------------------------

if __name__ == "__main__":
    # Find the repo root (one level up from this script).
    bot_dir = Path(__file__).parent
    repo_root = bot_dir.parent
    
    # Set up the bot manager.
    manager = ScriptBotManager(str(repo_root))
    
    # Refresh the list of scripts and show what is available.
    print("Refreshing script list...")
    manager.refresh_scripts()
    print(manager.list_available_scripts())
    print()
    
    # Show the bot's status.
    print("Bot status:")
    print(json.dumps(manager.get_status(), indent=2))
