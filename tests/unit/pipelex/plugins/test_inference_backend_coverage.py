"""Registry round-trip coverage for the built-in inference backends: every (family, sdk)
that the old per-family worker-factory ``match`` statements handled must resolve through the
registry built from ``BUILTIN_PLUGINS``, and the cross-family vendors must register into every
family they serve from their single ``register`` call.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.interpreter_plugins.builtins import BUILTIN_PLUGINS
from pipelex.plugins.inference_backend_registry import InferenceBackendRegistry, InferenceFamily
from pipelex.plugins.registrar import PluginRegistrar

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


def _build_registry() -> InferenceBackendRegistry:
    # No builtin's register() reads config: Temporal — the only plugin that did, via
    # ``temporal.is_enabled`` — now ships as the external pipelex-temporal dist. A bare
    # stub config suffices.
    stub_config = cast("PipelexConfig", SimpleNamespace())
    registrar = PluginRegistrar(config=stub_config)
    for plugin in BUILTIN_PLUGINS:
        plugin.register(registrar)
    return InferenceBackendRegistry(registrar.inference_backends)


# Every (family, sdk) the migrated worker factories used to dispatch on via a `match`.
EXPECTED_BACKENDS: list[tuple[InferenceFamily, str]] = [
    # LLM
    (InferenceFamily.LLM, "openai"),
    (InferenceFamily.LLM, "azure_openai"),
    (InferenceFamily.LLM, "openai_responses"),
    (InferenceFamily.LLM, "azure_openai_responses"),
    (InferenceFamily.LLM, "gateway_completions"),
    (InferenceFamily.LLM, "gateway_responses"),
    (InferenceFamily.LLM, "portkey_completions"),
    (InferenceFamily.LLM, "portkey_responses"),
    (InferenceFamily.LLM, "anthropic"),
    (InferenceFamily.LLM, "bedrock_anthropic"),
    (InferenceFamily.LLM, "mistral"),
    (InferenceFamily.LLM, "bedrock_boto3"),
    (InferenceFamily.LLM, "bedrock_aioboto3"),
    (InferenceFamily.LLM, "google"),
    # IMG_GEN
    (InferenceFamily.IMG_GEN, "gateway_img_gen"),
    (InferenceFamily.IMG_GEN, "gateway_completions"),
    (InferenceFamily.IMG_GEN, "openai_img_gen"),
    (InferenceFamily.IMG_GEN, "blackboxai_img_gen"),
    (InferenceFamily.IMG_GEN, "openrouter_img_gen"),
    (InferenceFamily.IMG_GEN, "fal"),
    (InferenceFamily.IMG_GEN, "huggingface_img_gen"),
    (InferenceFamily.IMG_GEN, "azure_rest_img_gen"),
    (InferenceFamily.IMG_GEN, "google"),
    # EXTRACT
    (InferenceFamily.EXTRACT, "gateway_extract"),
    (InferenceFamily.EXTRACT, "mistral"),
    (InferenceFamily.EXTRACT, "pypdfium2"),
    (InferenceFamily.EXTRACT, "docling_sdk"),
    (InferenceFamily.EXTRACT, "linkup_fetch"),
    # SEARCH
    (InferenceFamily.SEARCH, "linkup"),
    (InferenceFamily.SEARCH, "gateway_search"),
]


class TestInferenceBackendCoverage:
    @pytest.mark.parametrize(("family", "sdk"), EXPECTED_BACKENDS, ids=[f"{family}:{sdk}" for family, sdk in EXPECTED_BACKENDS])
    def test_backend_is_registered(self, family: InferenceFamily, sdk: str) -> None:
        """Each migrated (family, sdk) resolves to a make_worker via the built-in registry."""
        registry = _build_registry()
        assert registry.has(family=family, sdk=sdk), f"missing backend {family}:{sdk}"
        assert registry.lookup(family=family, sdk=sdk) is not None

    @pytest.mark.parametrize(
        ("vendor_families", "vendor"),
        [
            pytest.param([(InferenceFamily.LLM, "mistral"), (InferenceFamily.EXTRACT, "mistral")], "mistral", id="mistral"),
            pytest.param([(InferenceFamily.LLM, "google"), (InferenceFamily.IMG_GEN, "google")], "google", id="google"),
            pytest.param([(InferenceFamily.LLM, "openai"), (InferenceFamily.IMG_GEN, "openai_img_gen")], "openai", id="openai"),
            pytest.param([(InferenceFamily.EXTRACT, "linkup_fetch"), (InferenceFamily.SEARCH, "linkup")], "linkup", id="linkup"),
            pytest.param(
                [
                    (InferenceFamily.LLM, "gateway_completions"),
                    (InferenceFamily.IMG_GEN, "gateway_img_gen"),
                    (InferenceFamily.EXTRACT, "gateway_extract"),
                    (InferenceFamily.SEARCH, "gateway_search"),
                ],
                "gateway",
                id="gateway",
            ),
        ],
    )
    def test_cross_family_vendor_registers_into_all_its_families(self, vendor_families: list[tuple[InferenceFamily, str]], vendor: str) -> None:
        """A single vendor plugin's register() contributes backends across every family it serves."""
        registry = _build_registry()
        for family, sdk in vendor_families:
            assert registry.has(family=family, sdk=sdk), f"{vendor} did not register {family}:{sdk}"
