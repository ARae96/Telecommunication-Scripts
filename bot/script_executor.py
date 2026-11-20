# =============================================================================
# Script Execution - Run scripts safely with logging and error handling
# =============================================================================
# This module runs Python scripts that are part of the team's script library.
# It starts each script in its own process, captures everything the script
# prints to the screen, logs any errors that happen, and returns the results
# to the bot. This keeps a broken script from breaking the bot itself.
#
# Output (to logs and memory):
#   Execution logs with what the script printed, how long it took, and
#   any errors that came up.
# =============================================================================

import subprocess
import sys
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


# --- Logging Setup -----------------------------------------------------------

def setup_logging(script_name: str) -> logging.Logger:
    """Set up logging for a script run so we can see what happened.
    
    Each script run gets its own log so we can look back and see what went
    wrong if something breaks. The log shows the time, the level (info, error,
    etc.), and the message.
    """
    logger = logging.getLogger(script_name)
    logger.setLevel(logging.DEBUG)
    
    # Add a file handler that writes to bot/logs/<script_name>.log
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    handler = logging.FileHandler(log_dir / f"{script_name}.log")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    )
    logger.addHandler(handler)
    
    return logger


# --- Execution Result --------------------------------------------------------

@dataclass
class ExecutionResult:
    """What came back from running a script."""
    script_name: str
    success: bool
    return_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    started_at: str
    
    def to_dict(self) -> Dict:
        """Turn the result into a dictionary for logging or sending."""
        return {
            "script_name": self.script_name,
            "success": self.success,
            "return_code": self.return_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "elapsed_seconds": self.elapsed_seconds,
            "started_at": self.started_at
        }


# --- Script Executor ---------------------------------------------------------

class ScriptExecutor:
    """Runs scripts safely and captures what they output."""
    
    def __init__(self, repo_path: str, timeout_seconds: int = 300):
        """Set up the executor for a repository.
        
        We remember the path to the repository and how long we will wait for
        a script to finish (the timeout). If a script takes longer than the
        timeout, we kill it and return an error instead of waiting forever.
        The default timeout is 5 minutes (300 seconds).
        """
        self.repo_path = Path(repo_path)
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger("ScriptExecutor")
    
    def execute(self, script_name: str, args: Optional[list] = None) -> ExecutionResult:
        """Run a script and return what happened.
        
        We take the script name (like "Add_Permissions_to_Roles"), find it in
        the src directory, and run it as a Python process. We capture
        everything it prints to standard output (stdout) and standard error
        (stderr), measure how long it takes, and return all that information.
        
        If the script takes longer than the timeout, we kill it and return an
        error. If the script file does not exist, we return an error right away.
        
        Args:
            script_name: The name of the script to run (without the .py).
            args: Command-line arguments to pass to the script (optional).
        
        Returns:
            An ExecutionResult with success flag, output, and timing info.
        """
        script_path = self.repo_path / "src" / f"{script_name}.py"
        
        if not script_path.exists():
            return ExecutionResult(
                script_name=script_name,
                success=False,
                return_code=-1,
                stdout="",
                stderr=f"Script not found: {script_path}",
                elapsed_seconds=0.0,
                started_at=datetime.now().isoformat()
            )
        
        logger = setup_logging(script_name)
        started_at = datetime.now()
        
        try:
            # Build the command to run the script. We use the same Python
            # interpreter that is running the bot, and pass any arguments
            # the caller gave us.
            cmd = [sys.executable, str(script_path)]
            if args:
                cmd.extend(args)
            
            logger.info(f"Starting script: {script_name}")
            logger.info(f"Command: {' '.join(cmd)}")
            
            # Run the script and wait for it to finish (or timeout).
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=str(self.repo_path)
            )
            
            elapsed = (datetime.now() - started_at).total_seconds()
            success = process.returncode == 0
            
            logger.info(f"Script finished with code {process.returncode}")
            logger.info(f"Elapsed time: {elapsed:.2f} seconds")
            
            if process.stdout:
                logger.debug(f"STDOUT:\n{process.stdout}")
            
            if process.stderr:
                logger.warning(f"STDERR:\n{process.stderr}")
            
            return ExecutionResult(
                script_name=script_name,
                success=success,
                return_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                elapsed_seconds=elapsed,
                started_at=started_at.isoformat()
            )
        
        except subprocess.TimeoutExpired:
            # The script took too long. We killed it and return an error.
            elapsed = (datetime.now() - started_at).total_seconds()
            error_msg = (
                f"Script timed out after {self.timeout_seconds} seconds. "
                f"Check if the script is waiting for input or stuck in a loop."
            )
            logger.error(error_msg)
            
            return ExecutionResult(
                script_name=script_name,
                success=False,
                return_code=-2,
                stdout="",
                stderr=error_msg,
                elapsed_seconds=elapsed,
                started_at=started_at.isoformat()
            )
        
        except Exception as e:
            # Something went wrong that we did not expect. Log it and return.
            elapsed = (datetime.now() - started_at).total_seconds()
            error_msg = f"Error running script: {str(e)}"
            logger.exception(error_msg)
            
            return ExecutionResult(
                script_name=script_name,
                success=False,
                return_code=-3,
                stdout="",
                stderr=error_msg,
                elapsed_seconds=elapsed,
                started_at=started_at.isoformat()
            )
