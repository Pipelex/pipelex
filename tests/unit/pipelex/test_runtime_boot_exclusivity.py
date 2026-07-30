"""A runtime boot and a full boot own the same process globals, so they cannot coexist.

`set_runtime_hub` and `KajsonManager` overwrite unconditionally — only `log.configure` refuses a second
call — so a second boot on top of the first would silently replace them and serve a half-populated
class registry, which is the failure mode the "already initialized" guard exists to prevent. The guard resolves the singleton *by subclass*, so it
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

    def test_a_second_make_of_the_already_booted_class_refuses_too(self) -> None:
        """The same-class case, which the ``__init__`` guard alone cannot see.

        ``MetaSingleton.__call__`` hands back the registered instance without re-running ``__init__``,
        so a guard living only there is unreachable on a second ``make()`` for the *same* class — and
        ``make()`` would then re-run the whole ``setup()`` on the live boot, silently, returning the
        same object. The two cross-class tests above pass either way (a subclass is a different
        registry key, so ``__init__`` does run), which is exactly why this one is needed: it is the
        case both of them miss.
        """
        Pipelex.teardown_if_needed()
        try:
            runtime_boot = RuntimeBoot.make(integration_mode=_test_integration_mode(), needs_inference=False)
            try:
                with pytest.raises(PipelexSetupError, match="RuntimeBoot is already initialized"):
                    RuntimeBoot.make(integration_mode=_test_integration_mode(), needs_inference=False)
            finally:
                runtime_boot.teardown()

            # And the subclass, which has its own guard for the same reason: the two must not drift,
            # and "``__init__`` already covers it" is exactly the reasoning that left the base class
            # unguarded.
            Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False)
            with pytest.raises(PipelexSetupError, match="Pipelex is already initialized"):
                Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False)
        finally:
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())

    def test_teardown_if_needed_releases_a_bare_runtime_boot_through_the_subclass(self) -> None:
        """``Pipelex.teardown_if_needed()`` must release a live bare ``RuntimeBoot``, not no-op on it.

        The one asymmetry with no way out. ``teardown_if_needed`` resolves at the *base* class; asking
        ``cls`` instead would make this call silently no-op (``get_subclass_instance(Pipelex)`` cannot
        see a ``RuntimeBoot``) while every ``Pipelex(...)`` kept refusing because one exists. Nothing
        else in the suite exercises the classmethod against a bare runtime boot — the other tests
        release theirs through the instance — so that "tidy-up" would stay green.
        """
        Pipelex.teardown_if_needed()
        try:
            RuntimeBoot.make(integration_mode=_test_integration_mode(), needs_inference=False)

            Pipelex.teardown_if_needed()

            assert RuntimeBoot.get_optional_instance() is None, (
                "Pipelex.teardown_if_needed() no-oped on a live bare RuntimeBoot — the process is now unbootable and no teardown call can release it"
            )
        finally:
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())

    def test_a_runtime_boot_is_visible_through_the_subclass_resolved_accessors(self) -> None:
        """`RuntimeBoot.is_fully_booted()` must answer for a `Pipelex` too — it is one."""
        assert Pipelex.is_fully_booted()
        assert RuntimeBoot.is_fully_booted()
        assert RuntimeBoot.get_optional_instance() is Pipelex.get_instance()
