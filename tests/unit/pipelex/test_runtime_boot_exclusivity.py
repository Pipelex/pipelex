"""A runtime boot and a full boot own the same process globals, so they cannot coexist.

`set_runtime_hub`, `KajsonManager` and `log.configure` are all once-per-process, so a second boot on
top of the first would silently serve a half-populated class registry — the failure mode the
"already initialized" guard exists to prevent. The guard resolves the singleton *by subclass*, so it
sees a bare `RuntimeBoot` too; keyed on the exact class instead, `Pipelex.make()` would happily boot
on top of one, because `get_subclass_instance(Pipelex)` cannot see a `RuntimeBoot`.
"""

import pytest

from pipelex.base_exceptions import PipelexSetupError
from pipelex.pipelex import Pipelex
from pipelex.runtime_boot import RuntimeBoot
from pipelex.system.runtime import IntegrationMode, runtime_manager


def _test_integration_mode() -> IntegrationMode:
    """The boot mode the session conftest uses, so a re-boot here matches the one it replaces."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestRuntimeBootAndPipelexAreOneProcessGlobal:
    def test_a_full_boot_refuses_on_top_of_a_runtime_boot_and_succeeds_once_it_is_torn_down(self) -> None:
        # The module-scoped conftest fixture booted a Pipelex; release it so this test owns the process.
        Pipelex.teardown_if_needed()
        try:
            runtime_boot = RuntimeBoot.make(integration_mode=_test_integration_mode(), needs_inference=False)
            try:
                # The message must name what actually holds the globals. "Pipelex is already
                # initialized" would be a lie here, and an embedder that never touched Pipelex
                # deserves to be told what did — so the wording is asserted, not just the type.
                with pytest.raises(PipelexSetupError, match="RuntimeBoot is already initialized"):
                    Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False)
            finally:
                runtime_boot.teardown()

            # Same call, now that the runtime boot has released the globals.
            Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False).teardown()
        finally:
            # Restore what the fixture set up, so the rest of this module (and its teardown) is sane.
            Pipelex.make(integration_mode=_test_integration_mode())

    def test_a_runtime_boot_refuses_on_top_of_a_full_boot(self) -> None:
        """The exclusion runs both ways, and here the booted class is the *sub*class."""
        with pytest.raises(PipelexSetupError, match="Pipelex is already initialized"):
            RuntimeBoot.make(integration_mode=_test_integration_mode(), needs_inference=False)

    def test_a_runtime_boot_is_visible_through_the_subclass_resolved_accessors(self) -> None:
        """`RuntimeBoot.is_fully_booted()` must answer for a `Pipelex` too — it is one."""
        assert Pipelex.is_fully_booted()
        assert RuntimeBoot.is_fully_booted()
        assert RuntimeBoot.get_optional_instance() is Pipelex.get_instance()
