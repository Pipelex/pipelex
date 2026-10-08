"""One handle, one model per model type: every lookup of the deck goes by the pair, so each pipe family reaches its own spec."""

import pytest

from pipelex.cogt.exceptions import ModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.models.model_manager import ModelManager
from tests.unit.pipelex.cogt.models.model_deck_per_pair_utils import TWIN_HANDLE, build_deck_manager, make_backend


class TestLookupsPerPair:
    @staticmethod
    def _twin_manager() -> ModelManager:
        return build_deck_manager(
            make_backend(
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
