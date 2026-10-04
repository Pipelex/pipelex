"""A plugin contributes the error codes its service emits; the registrar refuses a code claimed twice or one the runtime reads itself."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import MODEL_NOT_ALLOWED_ERROR_CODE, UserActionKind
from pipelex.cogt.inference.service_error_vocabulary import ServiceErrorCode
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.plugins.exceptions import DuplicateServiceErrorCodeError, ReservedServiceErrorCodeError
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.runtime_hub import get_optional_service_error_vocabulary

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


def _make_registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))))


def _entry(code: str) -> ServiceErrorCode:
    return ServiceErrorCode(
        code=code,
        category=InferenceErrorCategory.CONTENT,
        user_action_kind=UserActionKind.CHANGE_INPUT,
        detail=f"advice for {code}",
    )


class TestServiceErrorCodesSeam:
    def test_contributed_codes_are_stored_and_attributed(self) -> None:
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        registrar.add_service_error_codes(codes=[_entry("svc-01"), _entry("svc-02")])

        assert set(registrar.service_error_codes) == {"svc-01", "svc-02"}
        assert registrar.service_error_codes["svc-01"].detail == "advice for svc-01"
        assert discovery.contributions == ["service error codes svc-01, svc-02"]

    def test_a_code_two_plugins_contribute_fails_naming_both(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_service_error_codes(codes=[_entry("svc-01")])
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        with pytest.raises(DuplicateServiceErrorCodeError) as exc_info:
            registrar.add_service_error_codes(codes=[_entry("svc-02"), _entry("svc-01")])

        assert exc_info.value.code == "svc-01"
        assert (exc_info.value.first_plugin, exc_info.value.second_plugin) == ("alpha", "beta")

    def test_a_code_the_runtime_classifies_itself_is_refused(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        with pytest.raises(ReservedServiceErrorCodeError) as exc_info:
            registrar.add_service_error_codes(codes=[_entry(MODEL_NOT_ALLOWED_ERROR_CODE)])

        assert exc_info.value.plugin == "alpha"
        assert not registrar.service_error_codes

    def test_a_kernel_group_plugin_may_contribute(self) -> None:
        """The vocabulary is a kernel-layer contribution: classification runs in a kernel-only boot too."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)

        registrar.add_service_error_codes(codes=[_entry("svc-01")])

        assert "svc-01" in registrar.service_error_codes

    def test_boot_installs_the_contributions_on_the_hub(self) -> None:
        """The session's boot ran every builtin; the vocabulary it froze is the one classification reads."""
        vocabulary = get_optional_service_error_vocabulary()

        assert vocabulary is not None
        assert MODEL_NOT_ALLOWED_ERROR_CODE not in vocabulary.codes
