from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.providers.typesafe.typesafe_plugin import TypesafePlugin
from pipelex.system.exceptions import MissingDependencyError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.sdk_client_registry import SdkClientRegistry
    from pipelex.system.configuration.configs import PipelexConfig

REGISTRY_MODULE = "pipelex.plugins.inference_backend_registry"


class TestTypesafeJudgmentWorkerGuard:
    def test_missing_typesafe_sdk_raises_missing_dependency(self, mocker: MockerFixture) -> None:
        """The judgment backend guards the optional SDK before importing a worker that imports it at the top.

        An absent extra must surface as a MissingDependencyError naming ``pipelex[typesafe]``, not
        as a raw ModuleNotFoundError from deep inside the worker module.
        """
        mocker.patch(f"{REGISTRY_MODULE}.importlib.util.find_spec", return_value=None)

        registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace()))
        TypesafePlugin().register(registrar)
        make_judgment_worker = registrar.inference_backends[InferenceFamily.JUDGMENT, "typesafe"]

        with pytest.raises(MissingDependencyError) as exc_info:
            make_judgment_worker(
                inference_model=cast("InferenceModelSpec", None),
                backend=cast("InferenceBackend", None),
                sdk_clients=cast("SdkClientRegistry", None),
                reporting_delegate=None,
            )
        assert "pipelex[typesafe]" in str(exc_info.value)
