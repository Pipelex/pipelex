import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexSetupError
from pipelex.cogt.exceptions import InferenceBackendCredentialsError, InferenceBackendCredentialsErrorType
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager


def _test_integration_mode() -> IntegrationMode:
    """The boot mode the session conftest uses, so a re-boot here matches the one it replaces."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestRuntimeBootCredentialRefusals:
    @pytest.mark.parametrize(
        ("credentials_error_type", "expected_code"),
        [
            (InferenceBackendCredentialsErrorType.VAR_NOT_FOUND, PipelexErrorCode.CONFIG_CREDENTIAL_MISSING),
            (InferenceBackendCredentialsErrorType.VAR_FALLBACK_PATTERN, PipelexErrorCode.CONFIG_CREDENTIAL_MISSING),
            (InferenceBackendCredentialsErrorType.UNKNOWN_VAR_PREFIX, PipelexErrorCode.CONFIG_INVALID),
            (InferenceBackendCredentialsErrorType.NOT_RESOLVED_ON_KEYLESS_BOOT, CoreCode.RUNTIME_MISCONFIGURED),
        ],
    )
    def test_a_credential_refusal_keeps_its_own_code_through_the_boot(
        self,
        mocker: MockerFixture,
        credentials_error_type: InferenceBackendCredentialsErrorType,
        expected_code: ErrorCode,
    ) -> None:
        """The boot's setup error adds its message and keeps why the credential failed, never forcing a missing variable."""
        refusal = InferenceBackendCredentialsError(
            credentials_error_type=credentials_error_type,
            backend_name="lighthouse_backend",
            message="The lighthouse backend's credential cannot be resolved",
            key_name="LIGHTHOUSE_API_KEY",
        )
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

            assert raised.value.__cause__ is refusal
            assert "LIGHTHOUSE_API_KEY" in str(raised.value)
            assert raised.value.to_error_report().code == expected_code
        finally:
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())
