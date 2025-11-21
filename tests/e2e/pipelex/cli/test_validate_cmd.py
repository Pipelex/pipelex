import shutil
import subprocess


class TestValidateCommand:
    def test_validate_all(self):
        make_path = shutil.which("make")
        assert make_path is not None, "make executable not found in PATH"

        result = subprocess.run(  # noqa: S603
            [make_path, "test-validate-cmd"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"make test-validate-cmd failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
