"""E2E test for the pipelex validate command."""

import subprocess
from pathlib import Path


class TestValidateCommand:
    """Test the pipelex validate CLI command."""

    def test_validate_all(self):
        """Test that 'pipelex validate all' runs without errors."""
        result = subprocess.run(
            ["pipelex", "validate", "all"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, (
            f"pipelex validate all failed\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

