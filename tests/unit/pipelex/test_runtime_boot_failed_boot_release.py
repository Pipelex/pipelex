"""A failed boot must not leave a process-global singleton behind for the next one to adopt.

`_release_after_failed_boot` releases the process globals a partial boot acquired. The telemetry
manager is the subtle member of that set: it is an `ABCSingletonMeta` singleton, not just an attribute
on the boot instance, so discarding the instance does **not** release it. Because `MetaSingleton`
short-circuits on an already-registered class, the next boot in the process gets the *same object* and
its `__init__` never re-runs — so `TelemetryManagerAbstract.get_instance()` keeps resolving to a
manager whose tracer provider has been shut down.

That is reachable in production rather than theoretical: `ensure_pipelex_booted` is a per-call lazy
boot on the runtime-bridge hot path, and the commonest boot failure — `models_manager.setup()` raising
on a missing model deck or missing credentials — fires *after* the telemetry factory has already
constructed and set up the manager.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.pipelex import Pipelex
from pipelex.runtime_boot import RuntimeBoot
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract


def _test_integration_mode() -> IntegrationMode:
    """The boot mode the session conftest uses, so a re-boot here matches the one it replaces."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestFailedBootReleasesTheTelemetrySingleton:
    def test_a_boot_failing_after_telemetry_setup_leaves_no_telemetry_singleton(
        self,
        mocker: MockerFixture,
    ) -> None:
        # An injected models manager whose setup raises reproduces the real shape: telemetry is already
        # live by then, since the factory runs earlier in the runtime half.
        exploding_models_manager = mocker.Mock()
        exploding_models_manager.setup.side_effect = RuntimeError("model deck missing")

        Pipelex.teardown_if_needed()
        try:
            assert TelemetryManagerAbstract.get_instance() is None, "the released boot left a telemetry singleton"

            with pytest.raises(RuntimeError, match="model deck missing"):
                Pipelex.make(
                    integration_mode=_test_integration_mode(),
                    needs_inference=False,
                    models_manager=exploding_models_manager,
                )

            # The whole point: the failed boot got as far as standing telemetry up, and released it.
            # Without that release the next boot adopts this object instead of building a fresh one.
            assert TelemetryManagerAbstract.get_instance() is None, (
                "a failed boot left the telemetry singleton registered — the next boot in this process "
                "would adopt the dead manager, since MetaSingleton never re-runs __init__ for an "
                "already-registered class"
            )
        finally:
            # Restore what the module fixture set up, so its teardown is sane.
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())

    def test_an_injected_telemetry_manager_that_raises_does_not_abort_the_other_releases(
        self,
        mocker: MockerFixture,
    ) -> None:
        """The releases after the telemetry call must still run, and the boot error must still surface.

        `self.telemetry_manager` is whatever the telemetry factory produced, and that includes a
        caller-supplied implementation: `telemetry_manager` is a public `make()` injection point typed
        only as `TelemetryManagerAbstract`, adopted whenever the integration mode and PostHog mode allow
        custom telemetry. The *built-in* manager is written never to raise, so reasoning from the
        concrete class would say this call is safe — and that reasoning does not survive an injected
        implementation. If a raising teardown aborted the release suite, `log.configure` and the
        `KajsonManager` registry would survive and every later boot in the process would die on
        "LogConfig is already set".

        The proof that the suite completed is the singleton de-registration, which is its **last**
        statement — so its absence means every release before it ran too. Asserting that rather than
        re-booting keeps the patched factory from leaking into a second boot.

        The factory is patched rather than the parameter passed, because the injection is only adopted
        in some telemetry modes and this test is about the state that results, not about how it arises.
        """
        exploding_telemetry = mocker.Mock()
        exploding_telemetry.teardown.side_effect = RuntimeError("telemetry teardown exploded")
        mocker.patch(
            "pipelex.runtime_boot.TelemetryFactory.make_telemetry_manager",
            return_value=exploding_telemetry,
        )
        exploding_models_manager = mocker.Mock()
        exploding_models_manager.setup.side_effect = RuntimeError("model deck missing")

        Pipelex.teardown_if_needed()
        try:
            # The *boot* error surfaces, not the teardown error that happened while handling it.
            with pytest.raises(RuntimeError, match="model deck missing"):
                Pipelex.make(
                    integration_mode=_test_integration_mode(),
                    needs_inference=False,
                    models_manager=exploding_models_manager,
                )

            exploding_telemetry.teardown.assert_called_once()
            assert RuntimeBoot.get_optional_instance() is None, (
                "the raising telemetry teardown aborted the release suite — the boot is still registered, "
                "so log.configure and the KajsonManager registry survived and the next boot in this "
                'process would die on "LogConfig is already set"'
            )
        finally:
            # Stop the patched factory before re-booting, or the restore below adopts the exploding
            # mock and its (unguarded, normal-path) teardown raises out of the fixture.
            mocker.stopall()
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())
