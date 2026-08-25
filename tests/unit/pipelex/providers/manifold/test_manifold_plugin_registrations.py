"""What the manifold plugin claims, stated in one place.

These sdk names are a contract with a file in another repository: the catalog's `sdk` column
(`manifold_models.toml`) has to name exactly these strings, and a mismatch is not a startup error —
it is an `InferenceBackendNotFoundError` at the first request against that model, which is to say in
production, for one model, on whatever day someone first uses it. The claim is cheap to pin and
expensive to discover.

Two of the entries are worth reading rather than skimming. `(IMG_GEN, manifold_completions)` is the
same sdk name registered under a second family, because some image models answer on the Chat
Completions shape rather than on the Images API and the catalog says which by giving them
`model_type = "img_gen"` while leaving them on the default completions sdk. And `anthropic` is
**absent on purpose**: Claude reaches the manifold service over the shared Anthropic driver, which
authenticates on whichever header the backend names, so registering a manifold-specific Anthropic
sdk would be a second way to do one thing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS
from pipelex.providers.manifold.manifold_plugin import ManifoldPlugin

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_EXPECTED_KEYS = {
    (InferenceFamily.LLM, "manifold_completions"),
    (InferenceFamily.LLM, "manifold_responses"),
    (InferenceFamily.IMG_GEN, "manifold_img_gen"),
    (InferenceFamily.IMG_GEN, "manifold_completions"),
    (InferenceFamily.EXTRACT, "manifold_extract"),
    (InferenceFamily.SEARCH, "manifold_search"),
}


def _registrar(mocker: MockerFixture) -> PluginRegistrar:
    return PluginRegistrar(config=mocker.MagicMock())


class TestManifoldPluginRegistrations:
    def test_the_plugin_claims_exactly_the_manifold_sdk_set(self, mocker: MockerFixture) -> None:
        registrar = _registrar(mocker)

        ManifoldPlugin().register(registrar)

        assert set(registrar.inference_backends) == _EXPECTED_KEYS

    def test_no_anthropic_sdk_is_claimed_under_a_manifold_name(self, mocker: MockerFixture) -> None:
        """Claude travels on the shared driver; a manifold-specific one would be a second path."""
        registrar = _registrar(mocker)

        ManifoldPlugin().register(registrar)

        assert not any("anthropic" in sdk for _, sdk in registrar.inference_backends)

    def test_the_plugin_is_a_kernel_builtin(self) -> None:
        """Registered beside the gateway plugin, so a manifold-declared backend needs no plugin install."""
        assert any(isinstance(plugin, ManifoldPlugin) for plugin in KERNEL_BUILTIN_PLUGINS)
