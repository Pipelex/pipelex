"""One handle, one model per model type: the deck build routes each pair of a name, by the rule its route matched.

The backends are built in memory, so these tests say nothing of how a backend file declares a twin.
"""

import pytest

from pipelex.cogt.exceptions import ModelManagerError
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from tests.unit.pipelex.cogt.models.model_deck_per_pair_utils import TWIN_HANDLE, build_deck_manager, make_backend


class TestDeckBuildPerPair:
    def test_a_twin_in_one_backend_is_served_whole(self) -> None:
        manager = build_deck_manager(
            make_backend("openai", (TWIN_HANDLE, ModelType.LLM), (TWIN_HANDLE, ModelType.JUDGMENT)),
            routing_profile=RoutingProfile(name="profile", default="openai"),
        )

        llm_spec = manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.LLM)
        judgment_spec = manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.JUDGMENT)
        assert llm_spec.model_type == ModelType.LLM
        assert judgment_spec.model_type == ModelType.JUDGMENT
        assert llm_spec is not judgment_spec

    def test_a_twin_split_across_backends_is_served_whole_under_a_default_match_with_a_fallback_order(self) -> None:
        """The primary backend lacks the judgment kind, so the pair is looked for along the fallback order."""
        manager = build_deck_manager(
            make_backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            make_backend("openai_decisions", (TWIN_HANDLE, ModelType.JUDGMENT)),
            routing_profile=RoutingProfile(name="profile", default="openai", fallback_order=["openai", "openai_decisions"]),
        )

        assert manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.LLM).backend_name == "openai"
        assert manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.JUDGMENT).backend_name == "openai_decisions"

    def test_a_default_match_without_a_fallback_order_looks_in_the_internal_backend_per_pair(self) -> None:
        manager = build_deck_manager(
            make_backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            make_backend(PipelexBackend.INTERNAL, (TWIN_HANDLE, ModelType.DOC_GEN)),
            make_backend("elsewhere", (TWIN_HANDLE, ModelType.JUDGMENT)),
            routing_profile=RoutingProfile(name="profile", default="openai"),
        )
        model_deck = manager.get_model_deck()

        assert model_deck.inference_models.types_serving(handle=TWIN_HANDLE) == [ModelType.LLM, ModelType.DOC_GEN]
        assert manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.DOC_GEN).backend_name == PipelexBackend.INTERNAL

    def test_a_pattern_match_skips_the_pair_its_backend_lacks(self) -> None:
        manager = build_deck_manager(
            make_backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            make_backend("openai_decisions", (TWIN_HANDLE, ModelType.JUDGMENT)),
            routing_profile=RoutingProfile(name="profile", routes={"gpt-*": "openai"}, fallback_order=["openai", "openai_decisions"]),
        )
        model_deck = manager.get_model_deck()

        assert model_deck.inference_models.types_serving(handle=TWIN_HANDLE) == [ModelType.LLM]

    def test_an_exact_route_to_a_backend_serving_the_name_as_another_type_only_boots_and_leaves_the_pair_unserved(self) -> None:
        """A route pins a name to a backend, so a call for that name never goes elsewhere."""
        manager = build_deck_manager(
            make_backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            make_backend("openai_decisions", (TWIN_HANDLE, ModelType.JUDGMENT)),
            routing_profile=RoutingProfile(name="profile", routes={TWIN_HANDLE: "openai"}, fallback_order=["openai", "openai_decisions"]),
        )
        model_deck = manager.get_model_deck()

        assert model_deck.inference_models.types_serving(handle=TWIN_HANDLE) == [ModelType.LLM]
        assert manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.LLM).backend_name == "openai"

    def test_an_exact_route_to_a_backend_not_declaring_the_name_at_all_fails_the_boot(self) -> None:
        with pytest.raises(ModelManagerError) as exc_info:
            build_deck_manager(
                make_backend("openai", (TWIN_HANDLE, ModelType.LLM)),
                make_backend("anthropic", ("claude", ModelType.LLM)),
                routing_profile=RoutingProfile(name="profile", routes={TWIN_HANDLE: "anthropic"}, default="openai"),
            )

        assert f"'{TWIN_HANDLE}'" in str(exc_info.value)
        assert "'anthropic'" in str(exc_info.value)
