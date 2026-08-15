"""Boot-scoped hub state must not outlive the boot that set it.

`is_dry_run_forced` and `boot_orchestrator` are boot *arguments* parked on the hub, not configuration:
nothing reloads them, and `setup()` writes both unconditionally on the way up. So the only thing that
can clear them is teardown — and teardown does not discard the hub itself (`set_runtime_hub` overwrites
a `ClassVar` with no reset counterpart, so `get_runtime_hub()` keeps handing out the torn-down hub).
Without an explicit release, a process that has torn down still answers `is_dry_run_forced()` with the
previous boot's keyless verdict and `get_boot_orchestrator()` with the previous boot's orchestrator,
while no boot is active at all.
"""

from pipelex.pipelex import Pipelex
from pipelex.runtime_hub import get_boot_orchestrator, get_runtime_hub, is_dry_run_forced
from pipelex.system.runtime import IntegrationMode, runtime_manager


class TestTeardownReleasesBootScopedHubState:
    def test_teardown_clears_the_flags_a_boot_set(self) -> None:
        Pipelex.teardown_if_needed()
        try:
            Pipelex.make(
                integration_mode=IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST,
                needs_inference=False,
            )
            # A keyless boot is what sets `is_dry_run_forced`. The orchestrator is set by hand rather
            # than through `make(boot_orchestrator=...)`, which would need that plugin installed to get
            # past the unknown-name guard; what is under test is the release, not the guard.
            get_runtime_hub().set_boot_orchestrator(boot_orchestrator="temporal")
            assert is_dry_run_forced() is True, "the keyless boot did not force dry run — the premise is gone"

            Pipelex.teardown_if_needed()

            assert is_dry_run_forced() is False, (
                "teardown left `is_dry_run_forced` set — anything asking before the next boot re-establishes "
                "it is told every run is forced to DRY by a boot that no longer exists"
            )
            assert get_boot_orchestrator() is None, (
                "teardown left the orchestrator name on the hub — run-time code asking whether it owns the process would be answered by a dead boot"
            )
        finally:
            Pipelex.teardown_if_needed()
