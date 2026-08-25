"""The deck-integrity check for managed gateways, once there can be more than one of them.

The check answers "does the service this handle is routed to actually carry it?", and with two
services live that question only makes sense per service. Two failure shapes are what this module
pins down, because the single-gateway implementation had no way to tell them apart:

- a **union** across the sections would accept a handle routed to the manifold service purely
  because the Portkey-cloud section happens to serve it — a boot that then fails at the first call;
- the same check run twice, once per section, over the *whole* deck would demand that every deck
  handle appear in **both** sections, which no mixed routing profile can satisfy.

The routing profile is what separates them: each per-service pass looks only at the handles the
active profile sends to that service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.exceptions import GatewayUnknownModelError
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice, ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_backends.gateway_config import GatewayConfig
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.cogt.search.search_setting import SearchModelChoice, SearchSetting
from pipelex.system.pipelex_service.types import RemoteConfigSource
from pipelex.system.runtime import ProblemReaction

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs

BYOK_BACKEND = "xai"
ENABLED_BACKENDS = [PipelexBackend.GATEWAY, PipelexBackend.MANIFOLD, BYOK_BACKEND, PipelexBackend.INTERNAL]

# The handles the fixture deck advertises. Everything not matched by a route lands on the profile's
# default backend, which is the Portkey-cloud service here.
GATEWAY_HANDLE = "gpt-5"
MANIFOLD_HANDLE = "claude-4-sonnet"
BYOK_HANDLE = "grok-3"
EXTRACT_HANDLE = "doc-extract"
IMG_GEN_HANDLE = "img-1"
SEARCH_HANDLE = "web-search"


def _specs(*model_names: str) -> BackendModelSpecs:
    """A spec map carrying exactly these model names, plus the `defaults` table the check ignores."""
    specs: dict[str, object] = {"defaults": {"model_type": "llm", "sdk": "gateway_completions"}}
    for model_name in model_names:
        specs[model_name] = {"model_id": model_name}
    return specs  # pyright: ignore[reportReturnType]


def _make_deck(*, llm_presets: dict[str, LLMSetting]) -> ModelDeck:
    """A minimal real deck whose only variable part is the LLM presets, mirroring the sibling tests."""
    llm_for_text: LLMModelChoice = GATEWAY_HANDLE
    llm_for_object: LLMModelChoice = GATEWAY_HANDLE
    extract_choice_default: ExtractModelChoice = EXTRACT_HANDLE
    img_gen_choice_default: ImgGenModelChoice = IMG_GEN_HANDLE
    search_choice_default: SearchModelChoice = SEARCH_HANDLE
    return ModelDeck(
        inference_models={},
        # LLM
        llm_default_temperature=0.7,
        llm_aliases={},
        llm_waterfalls={},
        llm_presets=llm_presets,
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=llm_for_text,
            for_object=llm_for_object,
        ),
        # Extract
        extract_aliases={},
        extract_waterfalls={},
        extract_presets={"default": ExtractSetting(model=EXTRACT_HANDLE)},
        extract_choice_default=extract_choice_default,
        # ImgGen
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_aliases={},
        img_gen_waterfalls={},
        img_gen_presets={"default": ImgGenSetting(model=IMG_GEN_HANDLE)},
        img_gen_choice_default=img_gen_choice_default,
        # Search
        search_aliases={},
        search_waterfalls={},
        search_presets={"default": SearchSetting(model=SEARCH_HANDLE)},
        search_choice_default=search_choice_default,
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


def _make_manager(*, llm_presets: dict[str, LLMSetting] | None = None) -> ModelManager:
    """A manager holding the fixture deck and the mixed routing profile, with no boot behind it."""
    manager = ModelManager()
    manager.model_deck = _make_deck(llm_presets=llm_presets if llm_presets is not None else {})
    manager._routing_profile = RoutingProfile(  # pyright: ignore[reportPrivateUsage]  # ruff: ignore[private-member-access]
        name="mixed",
        description="Portkey's cloud by default, Claude through the manifold service, grok direct",
        default=PipelexBackend.GATEWAY,
        routes={"claude-*": PipelexBackend.MANIFOLD, "grok-*": BYOK_BACKEND},
    )
    return manager


def _enforce(
    manager: ModelManager,
    *,
    gateway_specs: BackendModelSpecs,
    manifold_specs: BackendModelSpecs,
    source: RemoteConfigSource | None = RemoteConfigSource.FRESH,
) -> None:
    manager._enforce_gateway_model_membership(  # pyright: ignore[reportPrivateUsage]  # ruff: ignore[private-member-access]
        managed_gateway_configs={
            PipelexBackend.GATEWAY: GatewayConfig(model_specs=gateway_specs, aws_region="eu-west-3"),
            PipelexBackend.MANIFOLD: GatewayConfig(model_specs=manifold_specs),
        },
        gateway_config_source=source,
        enabled_backends=ENABLED_BACKENDS,
    )


EVERY_DEFAULT_ROUTED_HANDLE = (GATEWAY_HANDLE, EXTRACT_HANDLE, IMG_GEN_HANDLE, SEARCH_HANDLE)


class TestEnforceGatewayModelMembership:
    def test_each_service_carrying_what_it_is_routed_is_silent(self) -> None:
        """The control: a mixed profile where both sections carry their own share raises nothing."""
        manager = _make_manager(llm_presets={"cheap": LLMSetting(model=MANIFOLD_HANDLE, temperature=0.5)})

        _enforce(
            manager,
            gateway_specs=_specs(*EVERY_DEFAULT_ROUTED_HANDLE),
            manifold_specs=_specs(MANIFOLD_HANDLE),
        )

    def test_a_handle_absent_from_the_service_it_is_routed_to_raises_naming_that_service(self) -> None:
        """The case that must still fail loudly — and the one a union across the sections would miss.

        `claude-4-sonnet` is served by the Portkey-cloud section here, and the profile routes it to
        the manifold service, which does not carry it. Every call would fail; the boot says so.
        """
        manager = _make_manager(llm_presets={"cheap": LLMSetting(model=MANIFOLD_HANDLE, temperature=0.5)})

        with pytest.raises(GatewayUnknownModelError) as refused:
            _enforce(
                manager,
                gateway_specs=_specs(*EVERY_DEFAULT_ROUTED_HANDLE, MANIFOLD_HANDLE),
                manifold_specs=_specs(),
            )

        assert refused.value.model_name == MANIFOLD_HANDLE
        assert refused.value.backend_name == PipelexBackend.MANIFOLD
        assert PipelexBackend.MANIFOLD in str(refused.value), "with two services live, the message has to answer 'which one'"

    def test_a_handle_absent_from_the_other_service_is_not_an_error(self) -> None:
        """A handle legitimately absent from one section is normal, not a contradiction.

        This is what a per-service check run over the whole deck would break: nothing routed to the
        manifold service here, so its empty section is simply never consulted.
        """
        manager = _make_manager()

        _enforce(
            manager,
            gateway_specs=_specs(*EVERY_DEFAULT_ROUTED_HANDLE),
            manifold_specs=_specs(),
        )

    def test_a_handle_routed_to_a_byok_backend_is_not_this_checks_business(self) -> None:
        """Neither managed section carries `grok-3`, and neither is asked to: the profile sends it elsewhere.

        A handle that backend cannot serve either is the generic missing-handle path's problem, and
        it reports it against the backend that was actually asked.
        """
        manager = _make_manager(llm_presets={"fast": LLMSetting(model=BYOK_HANDLE, temperature=0.5)})

        _enforce(
            manager,
            gateway_specs=_specs(*EVERY_DEFAULT_ROUTED_HANDLE),
            manifold_specs=_specs(),
        )

    def test_no_live_source_skips_the_check_entirely(self) -> None:
        """The dummy-specs path: no provenance means there is nothing to validate against."""
        manager = _make_manager(llm_presets={"cheap": LLMSetting(model=MANIFOLD_HANDLE, temperature=0.5)})

        _enforce(manager, gateway_specs=_specs(), manifold_specs=_specs(), source=None)

    @pytest.mark.parametrize("managed_gateway_configs", [None, {}])
    def test_no_managed_config_skips_the_check_entirely(self, managed_gateway_configs: dict[str, GatewayConfig] | None) -> None:
        """A BYOK-only installation reaches this with nothing managed, and must pass straight through."""
        manager = _make_manager(llm_presets={"cheap": LLMSetting(model=MANIFOLD_HANDLE, temperature=0.5)})

        manager._enforce_gateway_model_membership(  # pyright: ignore[reportPrivateUsage]  # ruff: ignore[private-member-access]
            managed_gateway_configs=managed_gateway_configs,
            gateway_config_source=RemoteConfigSource.FRESH,
            enabled_backends=ENABLED_BACKENDS,
        )
