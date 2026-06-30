"""Boot-time validation of an explicitly requested orchestrator (``--orchestrator`` /
``Pipelex.make(boot_orchestrator=...)``).

``boot_orchestrator`` names the *plugin* this process boots under; a boot-orchestrator plugin
claims the process-global hub slots iff ``boot_orchestrator == its own name``. When the named plugin
is not registered (not installed, disabled, or a typo) nothing claims the slots — without the boot
guard the run would silently fall back to in-process core defaults instead of failing. These boot
with the real builtins (no Temporal plugin is installed in this repo), so ``"temporal"`` exercises
the not-installed case and a typo exercises the misspelling case; ``"direct"`` is a registered
builtin and must be accepted.
"""

from collections.abc import Generator

import pytest

from pipelex.pipelex import Pipelex
from pipelex.plugins.exceptions import UnknownBootOrchestratorError
from pipelex.system.runtime import IntegrationMode, runtime_manager


@pytest.fixture(autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module boots per test and tears down."""
    Pipelex.teardown_if_needed()
    yield
    Pipelex.teardown_if_needed()


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestBootOrchestratorValidation:
    @pytest.mark.parametrize("requested", ["temporal", "temproal", "not-a-plugin"])
    def test_unknown_boot_orchestrator_is_rejected(self, requested: str) -> None:
        with pytest.raises(UnknownBootOrchestratorError) as exc_info:
            Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False, boot_orchestrator=requested)
        assert exc_info.value.requested == requested
        assert not Pipelex.is_fully_booted()

    def test_registered_plugin_name_is_accepted(self) -> None:
        # "direct" is a core builtin (the in-process orchestrator) and claims no hub slots,
        # so booting under it is the in-process default — and must not be rejected.
        Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False, boot_orchestrator="direct")
        assert Pipelex.is_fully_booted()
