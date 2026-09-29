"""The runtime hub's import closure never loads the fetch helper, which reads the config back."""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys

#: Wall-clock bound on the import-closure subprocess, so a deadlock fails instead of hanging the suite.
SUBPROCESS_TIMEOUT_SECONDS = 300


class TestTheKernelClosureHoldsNoFetch:
    def test_importing_the_runtime_hub_does_not_load_the_fetch_helper(self) -> None:
        """The helper reads the config, which imports the runtime hub: the hub must not import the helper back.

        Run in a subprocess so the closure is exactly what the import pulls in.
        """
        script = (
            "import sys\n"
            "import pipelex.runtime_hub\n"
            "loaded = [name for name in ('pipelex.tools.misc.file_fetch_utils', 'pipelex.tools.uri.uri_base64') if name in sys.modules]\n"
            "print(','.join(loaded))\n"
        )
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )

        assert completed.stdout.strip() == ""
