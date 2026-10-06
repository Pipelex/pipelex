from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.inference_backend_registry import InferenceFamily, MakeWorkerFn
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.providers.linkup.linkup_exceptions import LinkupError
from pipelex.providers.linkup.linkup_plugin import LinkupPlugin

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.plugins.sdk_client_registry import SdkClientRegistry
    from pipelex.system.configuration.configs import PipelexConfig

# Each family's registered SDK key, and the module whose `LinkupClient` its worker builds.
LINKUP_FAMILIES = [
    pytest.param(InferenceFamily.SEARCH, "linkup", "pipelex.providers.linkup.linkup_search_worker", id="search"),
    pytest.param(InferenceFamily.EXTRACT, "linkup_fetch", "pipelex.providers.linkup.linkup_extract_worker", id="extract"),
]


def _registered_make_worker(*, family: InferenceFamily, sdk: str) -> MakeWorkerFn:
    registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace()))
    LinkupPlugin().register(registrar)
    return registrar.inference_backends[family, sdk]


class TestLinkupWorkersTakeTheBackendKey:
    """Linkup reads its key from its backend, like every other provider.

    Its workers used to read `LINKUP_API_KEY` from the secrets provider themselves, so the key the boot
    substituted into the backend was discarded and a configuration naming another variable was
    silently ignored. Through the backend, the one guard on `get_required_inference_backend` covers it.
    """

    @pytest.mark.parametrize(("family", "sdk", "worker_module"), LINKUP_FAMILIES)
    def test_the_worker_calls_linkup_with_the_backends_own_key(
        self, mocker: MockerFixture, family: InferenceFamily, sdk: str, worker_module: str
    ) -> None:
        linkup_client = mocker.patch(f"{worker_module}.LinkupClient")
        make_worker = _registered_make_worker(family=family, sdk=sdk)

        make_worker(
            inference_model=mocker.MagicMock(),
            backend=InferenceBackend(name="linkup", api_key="key-from-another-variable"),
            sdk_clients=cast("SdkClientRegistry", None),
            reporting_delegate=None,
        )

        linkup_client.assert_called_once_with(api_key="key-from-another-variable")

    @pytest.mark.parametrize(("family", "sdk", "worker_module"), LINKUP_FAMILIES)
    def test_a_backend_with_no_key_is_refused_before_any_client_is_built(
        self, mocker: MockerFixture, family: InferenceFamily, sdk: str, worker_module: str
    ) -> None:
        linkup_client = mocker.patch(f"{worker_module}.LinkupClient")
        make_worker = _registered_make_worker(family=family, sdk=sdk)

        with pytest.raises(LinkupError, match="'linkup' has no API key configured"):
            make_worker(
                inference_model=mocker.MagicMock(),
                backend=InferenceBackend(name="linkup"),
                sdk_clients=cast("SdkClientRegistry", None),
                reporting_delegate=None,
            )

        linkup_client.assert_not_called()
