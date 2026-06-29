"""Core seam for routing usage emissions out of an isolated sub-execution.

Replaces the former ``_is_in_temporal_activity`` ``sys.modules`` sniff: detecting an isolated
sub-execution (a Temporal activity) is an orchestrator concern, not core's. A boot-orchestrator
plugin claims ``HubSlot.ISOLATED_EXECUTION_PROBE`` with an ambient predicate; core consults it
through ``PipelexHub.is_in_isolated_execution`` and names no orchestrator. The boot-cost guard the
old sniff protected still holds — core imports no temporalio — and is now trivially true.
"""

import subprocess  # noqa: S404
import sys

from pipelex.hub import PipelexHub


class TestIsolatedExecutionProbe:
    def test_default_is_never_isolated(self) -> None:
        """A fresh hub (no boot-orchestrator claim) reports the in-process default: never isolated."""
        hub = PipelexHub()
        assert hub.is_in_isolated_execution() is False

    def test_claimed_probe_is_honored_and_consulted_each_call(self) -> None:
        """A claimed probe replaces the default and is ambient — consulted on every call, not cached."""
        hub = PipelexHub()
        flag = {"isolated": True}
        hub.set_isolated_execution_probe(lambda: flag["isolated"])
        assert hub.is_in_isolated_execution() is True
        flag["isolated"] = False
        assert hub.is_in_isolated_execution() is False

    def test_core_import_does_not_import_temporalio(self) -> None:
        """Boot-cost guard: importing the reporting + hub modules must not pull temporalio into sys.modules.

        Subprocess check so the assertion sees a pristine interpreter (the test process itself may
        have temporalio loaded via the integration fixtures).
        """
        probe = (
            "import sys; import pipelex.reporting.reporting_manager; import pipelex.hub; raise SystemExit(2 if 'temporalio' in sys.modules else 0)"
        )
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"importing core reporting/hub pulled temporalio into sys.modules (exit {result.returncode}); stderr: {result.stderr}"
        )
