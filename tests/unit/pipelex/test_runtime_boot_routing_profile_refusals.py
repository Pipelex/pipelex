"""The boot turns every refusal of the routing profile library into a setup error — with the class the loader raises.

Two `except` clauses in `RuntimeBoot` named `RoutingProfileLibraryNotFoundError` and
`RoutingProfileDisabledBackendError` while the loader raised `ModelManagerError` and
`RoutingProfileLibraryError`, so both were dead: a routing profile naming a disabled backend — the
half-written personal override, `active` flipped and the backend still off — reached the user as a
raw internal error instead of the setup error that says what to enable. The loader's own tests pin
what it raises; this module pins that the boot names those same classes. Rename one and both go red.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexSetupError
from pipelex.cogt.exceptions import RoutingProfileDisabledBackendError, RoutingProfileLibraryError, RoutingProfileLibraryNotFoundError
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager


def _test_integration_mode() -> IntegrationMode:
    """The boot mode the session conftest uses, so a re-boot here matches the one it replaces."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestRuntimeBootRoutingProfileRefusals:
    @pytest.mark.parametrize(
        ("refusal", "expected_in_message"),
        [
            (
                RoutingProfileLibraryNotFoundError("Could not find routing profile library at 'x'"),
                "Config files are missing for the routing profile library",
            ),
            (
                RoutingProfileDisabledBackendError("Backend 'other', required for profile 'on_other' is not enabled"),
                "required for profile 'on_other' is not enabled",
            ),
            (RoutingProfileLibraryError("Active profile 'on_typo' not found in the routing profile library"), "Active profile 'on_typo' not found"),
        ],
    )
    def test_a_routing_profile_refusal_is_a_setup_error_that_keeps_the_loaders_account(
        self,
        mocker: MockerFixture,
        refusal: Exception,
        expected_in_message: str,
    ) -> None:
        """Injected at the seam the real loader fails through, `models_manager.setup`, one class per clause."""
        refusing_models_manager = mocker.Mock()
        refusing_models_manager.setup.side_effect = refusal

        Pipelex.teardown_if_needed()
        try:
            with pytest.raises(PipelexSetupError) as raised:
                Pipelex.make(
                    integration_mode=_test_integration_mode(),
                    needs_inference=False,
                    models_manager=refusing_models_manager,
                )

            assert expected_in_message in str(raised.value)
            assert raised.value.__cause__ is refusal
        finally:
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())
