"""MissingBundleValidatorError is generic and plugin-decoupled (the /validate counterpart of D-F).

The API raises this when a requested orchestration mode has no registered bundle validator. Like
MissingOrchestratorError, its message names the token but no orchestrator — *is its plugin installed?* —
so core never names temporal/mistral. The one special case is the core ``"direct"`` token: its validator
is always present, so a miss there is a boot/discovery fault.
"""

import pytest

from pipelex.runtime_bridge.exceptions import MissingBundleValidatorError
from pipelex.runtime_bridge.orchestration_mode import DIRECT_ORCHESTRATION_MODE


class TestMissingBundleValidatorError:
    @pytest.mark.parametrize("mode", ["temporal", "mistral-workflows", "acme"])
    def test_unregistered_mode_carries_generic_plugin_hint(self, mode: str) -> None:
        error = MissingBundleValidatorError(mode=mode)

        assert error.mode == mode
        assert mode in str(error)
        assert "is its plugin installed?" in str(error)

    def test_direct_mode_reports_a_boot_or_discovery_problem(self) -> None:
        """The core "direct" token has no install hint — its validator is always available, so a miss is a boot fault."""
        error = MissingBundleValidatorError(mode=DIRECT_ORCHESTRATION_MODE)

        assert error.mode == DIRECT_ORCHESTRATION_MODE
        assert "boot or plugin-discovery problem" in str(error)
