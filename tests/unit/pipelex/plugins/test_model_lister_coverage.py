"""Registry round-trip coverage for the built-in model listers: every ``sdk`` that the old
``ModelLister.list_models`` ``match`` statement dispatched on must resolve to a lister through
the registry built from ``BUILTIN_PLUGINS``, and an SDK with no lister must yield a soft miss
(``get_optional`` returns ``None``) so the ``list-models`` loop reports it as unsupported.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.interpreter_plugins.builtins import BUILTIN_PLUGINS
from pipelex.plugins.model_lister_registry import ModelListerRegistry
from pipelex.plugins.registrar import PluginRegistrar

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


def _build_registry() -> ModelListerRegistry:
    # No builtin's register() reads config: Temporal — the only plugin that did, via
    # ``temporal.is_enabled`` — now ships as the external pipelex-temporal dist. A bare
    # stub config suffices.
    stub_config = cast("PipelexConfig", SimpleNamespace())
    registrar = PluginRegistrar(config=stub_config)
    for plugin in BUILTIN_PLUGINS:
        plugin.register(registrar)
    return ModelListerRegistry(registrar.model_listers)


# Every ``sdk`` the old ``model_lists.py`` ``match`` statement handled with a real lister arm.
EXPECTED_LISTER_SDKS: list[str] = [
    "openai",
    "azure_openai",
    "openai_responses",
    "azure_openai_responses",
    "anthropic",
    "mistral",
    "google",
    "bedrock",
    "bedrock_aioboto3",
]


class TestModelListerCoverage:
    @pytest.mark.parametrize("sdk", EXPECTED_LISTER_SDKS)
    def test_registered_sdk_resolves_to_a_lister(self, sdk: str) -> None:
        registry = _build_registry()
        lister = registry.get_optional(sdk=sdk)
        assert lister is not None, f"expected a model lister registered for sdk '{sdk}'"
        assert callable(lister)
        assert registry.has(sdk=sdk)

    def test_registry_exposes_exactly_the_expected_sdks(self) -> None:
        registry = _build_registry()
        assert sorted(registry.sdks) == sorted(EXPECTED_LISTER_SDKS)

    @pytest.mark.parametrize(
        "sdk",
        [
            "gateway_completions",  # an LLM/img-gen SDK that never supported remote listing
            "fal",  # an image-gen-only SDK with no lister
            "linkup",  # a search/extract SDK with no lister
            "totally_unknown_sdk",
        ],
    )
    def test_sdk_without_a_lister_is_a_soft_miss(self, sdk: str) -> None:
        registry = _build_registry()
        assert registry.get_optional(sdk=sdk) is None
        assert not registry.has(sdk=sdk)
