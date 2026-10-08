"""One handle, one model per model type: a method naming a model the deck serves only as another type is refused when it loads."""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.models.model_deck import (
    ModelDeck,
)
from pipelex.cogt.models.model_deck_check import check_judgment_choice_with_deck, check_llm_choice_with_deck
from tests.unit.pipelex.cogt.models.model_deck_per_pair_utils import GET_MODEL_DECK_TARGET, TWIN_HANDLE, build_deck_manager, make_backend


class TestLoadTimeChecksPerPair:
    @staticmethod
    def _deck() -> ModelDeck:
        return build_deck_manager(
            make_backend(
                "openai",
                ("llm-only", ModelType.LLM),
                ("verdict", ModelType.JUDGMENT),
                ("verdicts", ModelType.JUDGMENT),
                (TWIN_HANDLE, ModelType.LLM),
                (TWIN_HANDLE, ModelType.JUDGMENT),
            ),
            routing_profile=RoutingProfile(name="profile", default="openai"),
        ).get_model_deck()

    def test_a_judgment_naming_an_llm_only_handle_is_refused_at_load(self, mocker: MockerFixture) -> None:
        model_deck = self._deck()
        mocker.patch(GET_MODEL_DECK_TARGET, return_value=model_deck)

        with pytest.raises(ModelChoiceNotFoundError) as exc_info:
            check_judgment_choice_with_deck("llm-only")

        error = exc_info.value
        assert error.model_type == ModelType.JUDGMENT
        assert sorted(error.available_options) == [TWIN_HANDLE, "verdict", "verdicts"]
        assert "llm-only" not in error.available_options
        assert all(suggestion in {TWIN_HANDLE, "verdict", "verdicts"} for suggestion in error.suggestions)

    def test_the_deck_refuses_a_judgment_handle_served_only_as_an_llm(self) -> None:
        model_deck = self._deck()

        assert model_deck.is_model_handle_defined(model_handle="llm-only", model_type=ModelType.LLM)
        assert not model_deck.is_model_handle_defined(model_handle="llm-only", model_type=ModelType.JUDGMENT)
        with pytest.raises(ModelChoiceNotFoundError) as exc_info:
            model_deck.get_judgment_setting("llm-only")
        assert sorted(exc_info.value.available_options) == [TWIN_HANDLE, "verdict", "verdicts"]

    def test_both_families_accept_a_twin(self, mocker: MockerFixture) -> None:
        mocker.patch(GET_MODEL_DECK_TARGET, return_value=self._deck())

        check_llm_choice_with_deck(TWIN_HANDLE)
        check_judgment_choice_with_deck(TWIN_HANDLE)
