"""The internal backend as the last resort of the deck build: a name the profile sends to no enabled backend.

The backends are built in memory, so these tests say nothing of how a backend file declares a model.
"""

import pytest

from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from tests.unit.pipelex.cogt.models.model_deck_per_pair_utils import TWIN_HANDLE, build_deck_manager, make_backend

INTERNAL_HANDLE = "reportlab-pdf"


class TestDeckBuildInternalBackendUnderNoMatch:
    """A name the profile sends to no enabled backend is served by the internal backend, for each type it declares there."""

    def test_a_fallback_order_reaching_no_enabled_backend_serves_the_internal_pairs_from_the_internal_backend(self) -> None:
        manager = build_deck_manager(
            make_backend(PipelexBackend.INTERNAL, (INTERNAL_HANDLE, ModelType.DOC_GEN), (TWIN_HANDLE, ModelType.DOC_GEN)),
            make_backend("elsewhere", (TWIN_HANDLE, ModelType.LLM), ("claude", ModelType.LLM)),
            routing_profile=RoutingProfile(name="profile", fallback_order=["openai", "anthropic"]),
        )
        model_deck = manager.get_model_deck()

        assert manager.get_inference_model(INTERNAL_HANDLE, model_type=ModelType.DOC_GEN).backend_name == PipelexBackend.INTERNAL
        # The internal backend serves the types it declares, and a type another backend declares under the name stays unserved.
        assert model_deck.inference_models.types_serving(handle=TWIN_HANDLE) == [ModelType.DOC_GEN]
        assert not model_deck.inference_models.types_serving(handle="claude")

    def test_a_profile_made_only_of_routes_serves_an_internal_name_its_routes_do_not_mention(self) -> None:
        manager = build_deck_manager(
            make_backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            make_backend("anthropic", ("claude", ModelType.LLM)),
            make_backend(PipelexBackend.INTERNAL, (INTERNAL_HANDLE, ModelType.DOC_GEN)),
            routing_profile=RoutingProfile(name="profile", routes={TWIN_HANDLE: "openai"}),
        )
        model_deck = manager.get_model_deck()

        assert manager.get_inference_model(INTERNAL_HANDLE, model_type=ModelType.DOC_GEN).backend_name == PipelexBackend.INTERNAL
        assert manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.LLM).backend_name == "openai"
        # Only the internal backend is a last resort: another backend's unrouted name stays unserved.
        assert not model_deck.inference_models.types_serving(handle="claude")

    @pytest.mark.parametrize(
        "routing_profile",
        [
            RoutingProfile(name="unreachable_fallback", fallback_order=["openai", "anthropic"]),
            RoutingProfile(name="routes_only", routes={TWIN_HANDLE: "elsewhere"}),
        ],
    )
    def test_with_the_internal_backend_not_enabled_its_models_stay_unserved_and_the_deck_builds(self, routing_profile: RoutingProfile) -> None:
        """A disabled internal backend withholds its models, whatever the profile; the internal backend is here but not enabled."""
        manager = build_deck_manager(
            make_backend(PipelexBackend.INTERNAL, (INTERNAL_HANDLE, ModelType.DOC_GEN)),
            make_backend("elsewhere", (TWIN_HANDLE, ModelType.LLM)),
            routing_profile=routing_profile,
            enabled_backends=["elsewhere"],
        )
        model_deck = manager.get_model_deck()

        assert not model_deck.inference_models.types_serving(handle=INTERNAL_HANDLE)

    def test_a_pattern_route_catching_an_internal_name_to_a_backend_lacking_the_pair_leaves_it_out(self) -> None:
        """A wildcard is a routing statement: the internal backend rescues only a name the profile sends nowhere."""
        manager = build_deck_manager(
            make_backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            make_backend(PipelexBackend.INTERNAL, (INTERNAL_HANDLE, ModelType.DOC_GEN)),
            routing_profile=RoutingProfile(name="profile", routes={"reportlab-*": "openai"}),
        )
        model_deck = manager.get_model_deck()

        assert not model_deck.inference_models.types_serving(handle=INTERNAL_HANDLE)

    def test_an_exact_route_of_an_internal_name_to_another_backend_still_pins_it(self) -> None:
        """The route says where the name goes, so the internal backend's type of it is not served."""
        manager = build_deck_manager(
            make_backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            make_backend(PipelexBackend.INTERNAL, (TWIN_HANDLE, ModelType.DOC_GEN)),
            routing_profile=RoutingProfile(name="profile", routes={TWIN_HANDLE: "openai"}),
        )
        model_deck = manager.get_model_deck()

        assert model_deck.inference_models.types_serving(handle=TWIN_HANDLE) == [ModelType.LLM]
