# =============================================================================
# Script Discovery - Find all scripts in the repository
# =============================================================================
# This module finds all Python scripts in the src directory and gathers
# information about them. It reads each script's name, size, when it was last
# changed, and the description from the top of the file. The bot uses this to
# show the team what scripts are available and to run them on request.
#
# Output (to memory, not a file):
#   A list of scripts with their names, paths, sizes, and descriptions.
# =============================================================================

import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


# --- Data Structure ----------------------------------------------------------

@dataclass
class ScriptFile:
    """Information we keep about each discovered script."""
    name: str
    path: str
    size_bytes: int
    created_at: str
    modified_at: str
    description: str = ""
    
    def to_dict(self) -> Dict:
        """Turn this script info into a dictionary for saving or sending."""
        return asdict(self)


# --- Script Discovery --------------------------------------------------------

class GitHubScriptDiscovery:
    """Finds all Python scripts in the repository and reads their metadata."""
    
    def __init__(self, repo_path: str, scripts_dir: str = "src"):
        """Set up the discovery tool for a repository.
        
        We start by remembering where the repository lives and which folder
        holds the scripts. We do not read anything yet - that happens when
        you call discover_scripts().
        """
        self.repo_path = Path(repo_path)
        self.scripts_dir = self.repo_path / scripts_dir
        self.scripts: List[ScriptFile] = []
    
    def discover_scripts(self) -> List[ScriptFile]:
        """Find all Python scripts in the scripts directory and return them.
        
        We look for every .py file in the src folder. We skip any file that
        starts with an underscore (those are usually helpers, not runnable
        scripts). For each script we find, we read its size, the date it was
        last changed, and the first line of the docstring at the top of the
        file (if there is one).
        
        Returns the scripts sorted by name, so the list is always the same.
        """
        self.scripts = []
        
        if not self.scripts_dir.exists():
            return self.scripts
        
        for script_file in self.scripts_dir.glob("*.py"):
            # Skip helper files that start with an underscore.
            if script_file.name.startswith("_"):
                continue
            
            stat = script_file.stat()
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
            created = datetime.fromtimestamp(stat.st_ctime).isoformat()
            
            # Read the first line of the docstring to use as a description.
            description = self._extract_description(script_file)
            
            script = ScriptFile(
                name=script_file.stem,
                path=str(script_file.relative_to(self.repo_path)),
                size_bytes=stat.st_size,
                created_at=created,
                modified_at=modified,
                description=description
            )
            self.scripts.append(script)
        
        return sorted(self.scripts, key=lambda s: s.name)
    
    def _extract_description(self, script_path: Path) -> str:
        """Read the first line of a script's docstring as its description.
        
        If the file starts with a triple-quoted string, we grab
        everything until the closing quotes and return just the first line.
        If there is no docstring, we return an empty string and keep going.
        """
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read()
                
                # Look for module docstring at the top of the file.
                if content.startswith('"""'):
                    end = content.find('"""', 3)
                    if end > 0:
                        return content[3:end].strip().split("\n")[0]
                elif content.startswith("'''"):
                    end = content.find("'''", 3)
                    if end > 0:
                        return content[3:end].strip().split("\n")[0]
        except Exception:
            # If we cannot read the file for any reason, just skip it.
            pass
        
        return ""
    
    def get_script_by_name(self, name: str) -> Optional[ScriptFile]:
        """Look up a script by its name and return its information.
        
        If we have not discovered scripts yet, we do that first. Then we
        search the list for a script with the name you asked for and return
        it, or return None if we cannot find it.
        """
        if not self.scripts:
            self.discover_scripts()
        
        for script in self.scripts:
            if script.name == name:
                return script
        
        return None
    
    def list_scripts_json(self) -> str:
        """Return all discovered scripts as JSON text.
        
        This is useful for sending the list to other parts of the bot that
        need to show the scripts or log what is available.
        """
        self.discover_scripts()
        return json.dumps(
            [script.to_dict() for script in self.scripts],
            indent=2
        )
