"""One handle, one model per model type: the deck build routes each pair, and every lookup goes by the pair.

The backends are built in memory, so these tests say nothing of how a backend file declares a twin:
they prove that the deck can hold one and that each pipe family reaches its own spec.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ModelChoiceNotFoundError, ModelManagerError, ModelNotFoundError
from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.backend import InferenceBackend, PipelexBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.models.model_deck import (
    ExtractDeckBlueprint,
    ImgGenDeckBlueprint,
    JudgmentDeckBlueprint,
    LLMDeckBlueprint,
    ModelDeck,
    ModelDeckBlueprint,
    SearchDeckBlueprint,
)
from pipelex.cogt.models.model_deck_check import check_judgment_choice_with_deck, check_llm_choice_with_deck
from pipelex.cogt.models.model_manager import ModelManager

TWIN_HANDLE = "gpt-6-luna"
GET_MODEL_DECK_TARGET = "pipelex.cogt.models.model_deck_check.get_model_deck"


def _spec(*, name: str, model_type: ModelType, backend_name: str) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name=backend_name,
        name=name,
        sdk=f"{backend_name}_sdk",
        model_type=model_type,
        model_id=name,
        costs={},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


def _backend(name: str, *served: tuple[str, ModelType]) -> InferenceBackend:
    return InferenceBackend(
        name=name,
        model_specs=ModelSpecIndex.make_from_specs(
            model_specs=[_spec(name=handle, model_type=model_type, backend_name=name) for handle, model_type in served]
        ),
    )


def _deck_blueprint(*, extract_choice_default: ExtractModelChoice = "extractor") -> ModelDeckBlueprint:
    return ModelDeckBlueprint(
        llm=LLMDeckBlueprint(
            choice_defaults=LLMSettingChoicesDefaults(
                default_temperature=0.7,
                for_text=LLMSetting(model=TWIN_HANDLE, temperature=0.7),
                for_object=LLMSetting(model=TWIN_HANDLE, temperature=0.1),
            ),
        ),
        extract=ExtractDeckBlueprint(choice_default=extract_choice_default),
        img_gen=ImgGenDeckBlueprint(default_quality=Quality.MEDIUM, choice_default="painter"),
        search=SearchDeckBlueprint(choice_default="searcher"),
        judgment=JudgmentDeckBlueprint(aliases={"fast": "verdict"}),
    )


def _build_deck(*backends: InferenceBackend, routing_profile: RoutingProfile) -> ModelManager:
    manager = ModelManager()
    manager.inference_backend_library.root = {backend.name: backend for backend in backends}
    manager._routing_profile = routing_profile  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    manager.model_deck = manager.build_deck(
        model_deck_blueprint=_deck_blueprint(),
        enabled_backends=[backend.name for backend in backends],
    )
    return manager


class TestDeckBuildPerPair:
    def test_a_twin_in_one_backend_is_served_whole(self) -> None:
        manager = _build_deck(
            _backend("openai", (TWIN_HANDLE, ModelType.LLM), (TWIN_HANDLE, ModelType.JUDGMENT)),
            routing_profile=RoutingProfile(name="profile", default="openai"),
        )

        llm_spec = manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.LLM)
        judgment_spec = manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.JUDGMENT)
        assert llm_spec.model_type == ModelType.LLM
        assert judgment_spec.model_type == ModelType.JUDGMENT
        assert llm_spec is not judgment_spec

    def test_a_twin_split_across_backends_is_served_whole_under_a_default_match_with_a_fallback_order(self) -> None:
        """The primary backend lacks the judgment kind, so the pair is looked for along the fallback order."""
        manager = _build_deck(
            _backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            _backend("openai_decisions", (TWIN_HANDLE, ModelType.JUDGMENT)),
            routing_profile=RoutingProfile(name="profile", default="openai", fallback_order=["openai", "openai_decisions"]),
        )

        assert manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.LLM).backend_name == "openai"
        assert manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.JUDGMENT).backend_name == "openai_decisions"

    def test_a_default_match_without_a_fallback_order_looks_in_the_internal_backend_per_pair(self) -> None:
        manager = _build_deck(
            _backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            _backend(PipelexBackend.INTERNAL, (TWIN_HANDLE, ModelType.DOC_GEN)),
            _backend("elsewhere", (TWIN_HANDLE, ModelType.JUDGMENT)),
            routing_profile=RoutingProfile(name="profile", default="openai"),
        )
        model_deck = manager.get_model_deck()

        assert model_deck.inference_models.types_serving(handle=TWIN_HANDLE) == [ModelType.LLM, ModelType.DOC_GEN]
        assert manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.DOC_GEN).backend_name == PipelexBackend.INTERNAL

    def test_a_pattern_match_skips_the_pair_its_backend_lacks(self) -> None:
        manager = _build_deck(
            _backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            _backend("openai_decisions", (TWIN_HANDLE, ModelType.JUDGMENT)),
            routing_profile=RoutingProfile(name="profile", routes={"gpt-*": "openai"}, fallback_order=["openai", "openai_decisions"]),
        )
        model_deck = manager.get_model_deck()

        assert model_deck.inference_models.types_serving(handle=TWIN_HANDLE) == [ModelType.LLM]

    def test_an_exact_route_to_a_backend_serving_the_name_as_another_type_only_boots_and_leaves_the_pair_unserved(self) -> None:
        """A route pins a name to a backend, so a call for that name never goes elsewhere."""
        manager = _build_deck(
            _backend("openai", (TWIN_HANDLE, ModelType.LLM)),
            _backend("openai_decisions", (TWIN_HANDLE, ModelType.JUDGMENT)),
            routing_profile=RoutingProfile(name="profile", routes={TWIN_HANDLE: "openai"}, fallback_order=["openai", "openai_decisions"]),
        )
        model_deck = manager.get_model_deck()

        assert model_deck.inference_models.types_serving(handle=TWIN_HANDLE) == [ModelType.LLM]
        assert manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.LLM).backend_name == "openai"

    def test_an_exact_route_to_a_backend_not_declaring_the_name_at_all_fails_the_boot(self) -> None:
        with pytest.raises(ModelManagerError) as exc_info:
            _build_deck(
                _backend("openai", (TWIN_HANDLE, ModelType.LLM)),
                _backend("anthropic", ("claude", ModelType.LLM)),
                routing_profile=RoutingProfile(name="profile", routes={TWIN_HANDLE: "anthropic"}, default="openai"),
            )

        assert f"'{TWIN_HANDLE}'" in str(exc_info.value)
        assert "'anthropic'" in str(exc_info.value)


class TestLookupsPerPair:
    @staticmethod
    def _twin_manager() -> ModelManager:
        return _build_deck(
            _backend(
                "openai",
                (TWIN_HANDLE, ModelType.LLM),
                (TWIN_HANDLE, ModelType.JUDGMENT),
                ("verdict", ModelType.JUDGMENT),
                ("fast", ModelType.LLM),
            ),
            routing_profile=RoutingProfile(name="profile", default="openai"),
        )

    def test_each_family_reaches_its_own_spec_through_the_model_manager(self) -> None:
        manager = self._twin_manager()

        llm_spec = manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.LLM)
        judgment_spec = manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.JUDGMENT)

        assert (llm_spec.model_type, llm_spec.name) == (ModelType.LLM, TWIN_HANDLE)
        assert (judgment_spec.model_type, judgment_spec.name) == (ModelType.JUDGMENT, TWIN_HANDLE)

    def test_an_alias_resolves_when_another_type_serves_a_handle_of_the_same_name(self) -> None:
        """`fast` is an LLM handle and a judgment alias: the judgment lookup reaches the alias's target."""
        manager = self._twin_manager()

        assert manager.get_inference_model("fast", model_type=ModelType.JUDGMENT).name == "verdict"
        assert manager.get_inference_model("fast", model_type=ModelType.LLM).model_type == ModelType.LLM

    def test_an_inline_setting_naming_a_handle_served_as_another_type_only_is_the_callers_fault(self) -> None:
        """The load-time check does not look into an inline setting, so the run-time lookup is what reports it.

        `verdict` is served as a judgment model only, and nothing of the deck's LLM half names it.
        The report names the type the pipe asked for, never the type the deck serves the handle as.
        """
        inline_setting = LLMSetting(model="verdict", temperature=0.5)

        with pytest.raises(ModelNotFoundError) as exc_info:
            self._twin_manager().get_inference_model(inline_setting.model, model_type=ModelType.LLM)

        report = exc_info.value.to_error_report()
        assert report.user_action is not None
        assert report.user_action.kind is UserActionKind.CHANGE_MODEL
        assert "an LLM" in report.user_action.detail
        assert "judgment" not in report.user_action.detail


class TestLoadTimeChecksPerPair:
    @staticmethod
    def _deck() -> ModelDeck:
        return _build_deck(
            _backend(
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
