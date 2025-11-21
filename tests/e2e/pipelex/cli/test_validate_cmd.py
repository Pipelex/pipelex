"""E2E test for the pipelex validate command."""

import shutil
import subprocess


class TestValidateCommand:
    """Test the pipelex validate CLI command."""

    def test_validate_all(self):
        """Test that 'pipelex validate all' runs without errors."""
        pipelex_path = shutil.which("pipelex")
        assert pipelex_path is not None, "pipelex executable not found in PATH"

        result = subprocess.run(
            [pipelex_path, "validate", "all"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"pipelex validate all failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
