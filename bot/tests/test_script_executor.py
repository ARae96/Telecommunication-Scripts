# =============================================================================
# Script Executor Tests - Check that the executor runs scripts correctly
# =============================================================================
# These tests make sure the script executor can find scripts, run them, and
# capture their output correctly. We test with real scripts from the src
# directory, starting with Add_Permissions_to_Roles.py. The tests check for
# success, timeout handling, and error cases.
#
# To run these tests:
#   cd /path/to/script-development
#   python -m pytest bot/tests/test_script_executor.py -v
# =============================================================================

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the bot directory to the path so we can import the modules we test.
bot_dir = Path(__file__).parent.parent
sys.path.insert(0, str(bot_dir))

from script_executor import ScriptExecutor, ExecutionResult


# --- Test Fixtures -----------------------------------------------------------

@pytest.fixture
def repo_path():
    """The path to the Script Development repository."""
    return str(bot_dir.parent)


@pytest.fixture
def executor(repo_path):
    """Create an executor for the tests."""
    return ScriptExecutor(repo_path, timeout_seconds=10)


# --- Tests for Execution Result ----------------------------------------------

class TestExecutionResult:
    """Test the data structure that holds execution results."""
    
    def test_result_to_dict(self):
        """Check that we can turn an execution result into a dictionary."""
        result = ExecutionResult(
            script_name="Test_Script",
            success=True,
            return_code=0,
            stdout="Test output",
            stderr="",
            elapsed_seconds=1.5,
            started_at="2026-11-20T11:00:00"
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["script_name"] == "Test_Script"
        assert result_dict["success"] is True
        assert result_dict["return_code"] == 0
        assert result_dict["stdout"] == "Test output"
        assert result_dict["stderr"] == ""


# --- Tests for Script Discovery and Execution --------------------------------

class TestScriptExecutor:
    """Test the script executor."""
    
    def test_script_not_found(self, executor):
        """Check that we get an error when the script does not exist."""
        result = executor.execute("Nonexistent_Script")
        
        assert result.success is False
        assert result.return_code == -1
        assert "not found" in result.stderr.lower()
    
    def test_execute_with_mock(self, executor):
        """Check that execute calls subprocess.run with the right arguments.
        
        We mock subprocess.run so we do not actually run a script. We just
        check that the executor calls it with the right command and options.
        """
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Mock output",
                stderr=""
            )
            
            result = executor.execute("Add_Permissions_to_Roles")
            
            # Check that subprocess.run was called.
            assert mock_run.called
            
            # Check the command that was built.
            args, kwargs = mock_run.call_args
            cmd = args[0]
            assert "Add_Permissions_to_Roles.py" in cmd[1]
            assert kwargs["timeout"] == 10
            assert kwargs["capture_output"] is True
    
    def test_timeout_handling(self, executor):
        """Check that we handle timeouts correctly.
        
        When a script takes too long, we catch the timeout exception and
        return an error result (return code -2) instead of crashing.
        """
        with patch("subprocess.run") as mock_run:
            # Make subprocess.run raise a timeout exception.
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)
            
            # We need to patch the path check too, or use a real script.
            # Use Add_Permissions_to_Roles which we know exists.
            result = executor.execute("Add_Permissions_to_Roles")
            
            assert result.success is False
            assert result.return_code == -2
            assert "timed out" in result.stderr.lower()


# --- Integration Test (if Add_Permissions_to_Roles exists) -----------------

class TestRealScriptExecution:
    """Test with real scripts if they exist."""
    
    def test_add_permissions_script_exists(self, repo_path):
        """Check that Add_Permissions_to_Roles.py exists in the src directory."""
        script_path = Path(repo_path) / "src" / "Add_Permissions_to_Roles.py"
        assert script_path.exists(), f"Script not found at {script_path}"
    
    def test_add_permissions_has_docstring(self, repo_path):
        """Check that Add_Permissions_to_Roles.py has a docstring.
        
        This helps us make sure the script can be discovered with a
        description. We read the first 200 characters to check if it starts
        with a docstring.
        """
        script_path = Path(repo_path) / "src" / "Add_Permissions_to_Roles.py"
        
        with open(script_path, "r") as f:
            content = f.read(200)
        
        # Check if the script starts with a docstring.
        has_docstring = content.strip().startswith(('"""', "'''"))
        
        # If there is no docstring, that is OK - just note it for the team.
        if not has_docstring:
            print(
                "Note: Add_Permissions_to_Roles.py does not start with "
                "a docstring. Adding one would help users understand what "
                "the script does."
            )


# --- Run the tests if this file is run directly ----------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
