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
