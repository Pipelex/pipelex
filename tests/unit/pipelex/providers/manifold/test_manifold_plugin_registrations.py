"""What the manifold plugin claims, stated in one place.

These sdk names are a contract with a file in another repository: the catalog's `sdk` column
(`manifold_models.toml`) has to name exactly these strings, and a mismatch is not a startup error —
it is an `InferenceBackendNotFoundError` at the first request against that model, which is to say in
production, for one model, on whatever day someone first uses it. The claim is cheap to pin and
expensive to discover.

Two of the entries are worth reading rather than skimming. `(IMG_GEN, manifold_completions)` is the
same sdk name registered under a second family, because some image models answer on the Chat
Completions shape rather than on the Images API and the catalog says which by giving them
`model_type = "img_gen"` while leaving them on the default completions sdk. And Claude has a token of
its own, `manifold_anthropic`, rather than the plain `anthropic` the open Anthropic plugin owns: it is
the same worker built with the package's extras factory, which is what adds the metadata header.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from anthropic import AsyncAnthropic

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.model_handle import ModelHandle
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS
from pipelex.providers.manifold.manifold_anthropic_extras import ManifoldAnthropicExtrasFactory
from pipelex.providers.manifold.manifold_plugin import ManifoldPlugin

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

_EXPECTED_KEYS = {
    (InferenceFamily.LLM, "manifold_anthropic"),
    (InferenceFamily.LLM, "manifold_completions"),
    (InferenceFamily.LLM, "manifold_responses"),
    (InferenceFamily.IMG_GEN, "manifold_img_gen"),
    (InferenceFamily.IMG_GEN, "manifold_completions"),
    (InferenceFamily.EXTRACT, "manifold_extract"),
    (InferenceFamily.SEARCH, "manifold_search"),
}


def _build_now(*, handle: object, build: Callable[[], object]) -> object:
    del handle
    return build()


def _registrar(mocker: MockerFixture) -> PluginRegistrar:
    return PluginRegistrar(config=mocker.MagicMock())


class TestManifoldPluginRegistrations:
    def test_the_plugin_claims_exactly_the_manifold_sdk_set(self, mocker: MockerFixture) -> None:
        registrar = _registrar(mocker)

        ManifoldPlugin().register(registrar)

        assert set(registrar.inference_backends) == _EXPECTED_KEYS

    def test_the_plain_anthropic_sdk_is_not_claimed(self, mocker: MockerFixture) -> None:
        """The open Anthropic plugin owns `anthropic`; claiming it here would fail the boot on a duplicate."""
        registrar = _registrar(mocker)

        ManifoldPlugin().register(registrar)

        assert all(sdk.startswith("manifold_") for _, sdk in registrar.inference_backends)

    def test_claude_is_built_with_the_metadata_extras_factory(self, mocker: MockerFixture) -> None:
        registrar = _registrar(mocker)
        ManifoldPlugin().register(registrar)
        make_worker = registrar.inference_backends[InferenceFamily.LLM, "manifold_anthropic"]
        model = mocker.MagicMock()
        model.sdk = "manifold_anthropic"
        model.max_tokens = 4096
        model.get_instructor_mode.return_value = None
        backend = InferenceBackend(name="pipelex_manifold", endpoint="https://manifold.example.com", api_key="token")
        sdk_clients = mocker.MagicMock()
        sdk_clients.get_or_create.side_effect = _build_now
        mocker.patch.object(ModelHandle, "make_for_inference_model", return_value=mocker.MagicMock(sdk="manifold_anthropic"))

        worker = make_worker(inference_model=model, backend=backend, sdk_clients=sdk_clients, reporting_delegate=None)

        assert isinstance(worker, AnthropicLLMWorker)
        assert isinstance(worker.extras_factory, ManifoldAnthropicExtrasFactory)
        assert isinstance(worker.anthropic_async_client, AsyncAnthropic)

    def test_the_plugin_is_a_kernel_builtin(self) -> None:
        """Registered beside the gateway plugin, so a manifold-declared backend needs no plugin install."""
        assert any(isinstance(plugin, ManifoldPlugin) for plugin in KERNEL_BUILTIN_PLUGINS)
