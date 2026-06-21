"""MissingBundleValidatorError carries each mode's exact install hint (the /validate counterpart of C7).

The API raises this when a requested execution mode has no registered bundle validator. Like
MissingOrchestratorError, its message is derived from the mode so each surfaces its actionable
install hint; DIRECT instead reports a boot/discovery problem (the core validator is always present).
"""

import pytest

from pipelex.runtime_bridge.exceptions import MissingBundleValidatorError
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode


class TestMissingBundleValidatorError:
    @pytest.mark.parametrize(
        ("mode", "hint_fragment"),
        [
            (PipelexExecutionMode.TEMPORAL_BLOCKING, "pip install pipelex-temporal"),
            (PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET, "pip install pipelex-temporal"),
            (PipelexExecutionMode.MISTRAL_NATIVE, "pip install pipelex-mistralai-workflows"),
        ],
    )
    def test_external_mode_carries_its_install_hint(self, mode: PipelexExecutionMode, hint_fragment: str) -> None:
        error = MissingBundleValidatorError(mode=mode)

        assert error.mode is mode
        assert hint_fragment in str(error)

    def test_direct_mode_reports_a_boot_or_discovery_problem(self) -> None:
        """DIRECT has no install hint — its core validator is always available, so a miss is a boot fault."""
        error = MissingBundleValidatorError(mode=PipelexExecutionMode.DIRECT)

        assert error.mode is PipelexExecutionMode.DIRECT
        assert "boot or plugin-discovery problem" in str(error)
