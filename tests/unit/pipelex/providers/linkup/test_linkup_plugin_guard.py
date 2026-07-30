from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.providers.linkup.linkup_plugin import LinkupPlugin
from pipelex.system.exceptions import MissingDependencyError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.sdk_client_registry import SdkClientRegistry
    from pipelex.system.configuration.configs import PipelexConfig

REGISTRY_MODULE = "pipelex.plugins.inference_backend_registry"


class TestLinkupSearchWorkerGuard:
    def test_missing_linkup_sdk_raises_missing_dependency(self, mocker: MockerFixture) -> None:
        """The registered Linkup *search* backend must guard the optional linkup SDK with require_sdk *before*
        importing its top-level-`linkup`-importing worker, so an absent extra surfaces as MissingDependencyError
        (with the pipelex[linkup] hint), not a raw ModuleNotFoundError — matching the extract backend's behavior.
        """
        mocker.patch(f"{REGISTRY_MODULE}.importlib.util.find_spec", return_value=None)

        registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace()))
        LinkupPlugin().register(registrar)
        make_search_worker = registrar.inference_backends[InferenceFamily.SEARCH, "linkup"]

        with pytest.raises(MissingDependencyError) as exc_info:
            make_search_worker(
                inference_model=cast("InferenceModelSpec", None),
                backend=cast("InferenceBackend", None),
                sdk_clients=cast("SdkClientRegistry", None),
                reporting_delegate=None,
            )
        assert "pipelex[linkup]" in str(exc_info.value)
