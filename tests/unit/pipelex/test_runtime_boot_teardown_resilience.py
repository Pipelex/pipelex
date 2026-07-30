"""A teardown that fails partway must still leave the process re-bootable.

The releases at the end of ``RuntimeBoot._teardown_runtime`` — the hub config, the class-registry
scoping, and the ``MetaSingleton`` de-registration — are what a *later* boot in the same process
depends on. If a raising step above them skipped them, the process would be wedged **permanently**:
the next ``make()`` dies on "already initialized", and ``teardown_if_needed`` cannot rescue it,
because it resolves the very same instance and re-enters the very same raiser.

Reachable through injection rather than through a built-in defect, which is the point: the built-in
``TelemetryManager`` and ``PipelineManager`` are written not to raise, but both are public ``make()``
injection points typed as abstracts, so that guarantee belongs to the concrete classes and not to the
calls made here. Both tests therefore inject, and both assert on the de-registration — the *last*
statement of the release block — because its absence is exactly the wedge.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager


def _test_integration_mode() -> IntegrationMode:
    """The boot mode the session conftest uses, so a re-boot here matches the one it replaces."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestAFailingTeardownLeavesTheProcessRebootable:
    def test_a_raising_telemetry_teardown_still_releases_the_boot_singleton(self, mocker: MockerFixture) -> None:
        """The first step of ``_teardown_runtime`` raises; the releases at its end must still run.

        The factory is patched rather than the parameter passed, because an injected manager is only
        adopted in some telemetry modes and this test is about the resulting state, not how it arises.
        """
        exploding_telemetry = mocker.Mock()
        exploding_telemetry.teardown.side_effect = RuntimeError("telemetry teardown exploded")
        mocker.patch("pipelex.runtime_boot.TelemetryFactory.make_telemetry_manager", return_value=exploding_telemetry)

        Pipelex.teardown_if_needed()
        try:
            Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False)

            # The teardown failure surfaces rather than being swallowed: a half-failed teardown must
            # not look successful.
            with pytest.raises(RuntimeError, match="telemetry teardown exploded"):
                Pipelex.teardown_if_needed()

            assert Pipelex.get_optional_instance() is None, (
                "the raising telemetry teardown skipped the release block — this instance is still "
                "registered, so the next make() in this process dies on 'already initialized' and "
                "teardown_if_needed re-enters the same raiser: the process is wedged for good"
            )
        finally:
            # Stop the patched factory before re-booting, or the restore adopts the exploding mock.
            mocker.stopall()
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())

    def test_a_raising_pipeline_manager_teardown_still_runs_the_runtime_teardown(self, mocker: MockerFixture) -> None:
        """``Pipelex.teardown`` sequences three phases, so the interpreter one must not skip the last.

        This is the same wedge reached one level up: the runtime teardown owns the release block, and
        an unguarded ``pipeline_manager.teardown()`` between the two would skip the whole method.
        """
        exploding_pipeline_manager = mocker.Mock()
        exploding_pipeline_manager.teardown.side_effect = RuntimeError("pipeline manager teardown exploded")

        Pipelex.teardown_if_needed()
        try:
            Pipelex.make(
                integration_mode=_test_integration_mode(),
                needs_inference=False,
                pipeline_manager=exploding_pipeline_manager,
            )

            with pytest.raises(RuntimeError, match="pipeline manager teardown exploded"):
                Pipelex.teardown_if_needed()

            assert Pipelex.get_optional_instance() is None, (
                "the raising pipeline-manager teardown skipped _teardown_runtime entirely, leaving the "
                "process wedged: no later boot can succeed and no teardown can undo it"
            )
        finally:
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())
