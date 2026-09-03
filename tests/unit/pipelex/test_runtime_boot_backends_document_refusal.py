"""A backends document that does not parse is a setup error naming the file, even when the gate reads it before the library does.

`RuntimeBoot` asks `enabled_managed_gateway_sections` which managed gateway backends to fetch specs for before
the backend library loads, so a `backends_override.toml` with a stray quote used to surface there as a raw
`TomlError` — outside every clause the boot has for an unloadable library. The gate now raises the library's own
refusal class, and this pins that the boot turns it into the setup error the library's refusal gets.

The gate is read exactly once. The telemetry decision further down needs the narrower "is the legacy gateway
enabled" answer, and it reads it off the mapping this gate returned rather than asking the document again — a
second read would be a second way past the clause.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexSetupError
from pipelex.cogt.exceptions import InferenceBackendLibraryValidationError
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestRuntimeBootBackendsDocumentRefusal:
    def test_a_backends_document_that_does_not_parse_is_a_setup_error_that_names_the_file(self, mocker: MockerFixture) -> None:
        refusal = InferenceBackendLibraryValidationError(
            "Invalid inference backend library 'base' with overrides 'home/backends_override.toml': "
            "TOML parsing error in file 'home/backends_override.toml'"
        )
        mocker.patch("pipelex.runtime_boot.enabled_managed_gateway_sections", side_effect=refusal)

        Pipelex.teardown_if_needed()
        try:
            with pytest.raises(PipelexSetupError) as raised:
                Pipelex.make(integration_mode=_test_integration_mode(), needs_inference=False)

            assert "home/backends_override.toml" in str(raised.value)
            assert raised.value.__cause__ is refusal
        finally:
            mocker.stopall()  # the re-boot below must read the real gate
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())
