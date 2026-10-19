import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from pytest_mock import MockerFixture

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.exceptions import ModelChoiceNotFoundError, ModelDeckChoiceUnresolvedError
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.judgment.judgment_models import YesNoQuestion
from pipelex.cogt.llm.llm_setting import LLMSettingChoices, LLMSettingChoicesDefaults
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.kernel.prompt_assembly import UserPromptContent
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge, PipeJudgeQuestion
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error
from pipelex.system.runtime import ProblemReaction
from pipelex.tools.jinja2.template_category import TemplateCategory

_MISSING_JUDGMENT_PRESET = "$missing-judgment-preset"


def _deck_whose_judgment_default_is_undefined() -> ModelDeck:
    """A deck serving no model, whose judgment default names a preset it does not define."""
    return ModelDeck(
        inference_models=ModelSpecIndex.make_from_specs(model_specs=[]),
        llm_default_temperature=0.7,
        llm_aliases={},
        llm_waterfalls={},
        llm_presets={},
        llm_choice_defaults=LLMSettingChoicesDefaults(default_temperature=0.7, for_text="no-text-model", for_object="no-object-model"),
        llm_choice_overrides=LLMSettingChoices(for_text=None, for_object=None),
        extract_aliases={},
        extract_waterfalls={},
        extract_presets={},
        extract_choice_default="no-extract-model",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_aliases={},
        img_gen_waterfalls={},
        img_gen_presets={},
        img_gen_choice_default="no-img-gen-model",
        search_aliases={},
        search_waterfalls={},
        search_presets={},
        search_choice_default="no-search-model",
        doc_gen_choice_defaults={},
        judgment_choice_default=_MISSING_JUDGMENT_PRESET,
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


def _pipe_judge_naming_no_model() -> PipeJudge:
    return PipeJudge(
        code="judge_urgency",
        domain_code="deck_default",
        description="Judge whether the message is urgent",
        output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.YES_NO)),
        judgment_choice=None,
        prompt_content=UserPromptContent(template=TemplateBlueprint(template="$message", category=TemplateCategory.LLM_PROMPT)),
        question=PipeJudgeQuestion(judgment_question=YesNoQuestion(instructions="Is it urgent?")),
    )


class TestPipeJudgeDeckDefault:
    def test_an_undefined_deck_default_leaves_as_the_deck_s_fault(self, mocker: MockerFixture) -> None:
        """The step names no model, so the deck's miss is no unknown model of the method's, and no verdict item."""
        mocker.patch("pipelex.kernel.judgment_ops.get_model_deck", return_value=_deck_whose_judgment_default_is_undefined())
        pipe_judge = _pipe_judge_naming_no_model()

        with pytest.raises(ModelDeckChoiceUnresolvedError) as exc_info, translate_to_validate_bundle_error():
            pipe_judge.validate_inputs_with_library()

        deck_fault = exc_info.value
        assert deck_fault.deck_setting == "judgment.choice_default"
        assert deck_fault.resolve_error_code() == PipelexErrorCode.CONFIG_INVALID

        caller = deck_fault.to_problem(view=ProblemView.CALLER)
        assert caller.code == PipelexErrorCode.CONFIG_INVALID
        assert caller.domain == ProblemDomain.OPERATOR
        assert caller.errors is None
        # The deck's setting is the operator's to fix and to read: the caller reads neither it nor the message.
        caller_wire = str(caller.to_wire())
        assert deck_fault.message not in caller_wire
        assert "choice_default" not in caller_wire
        operator = deck_fault.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "ModelDeckChoiceUnresolvedError"
        assert operator.diagnostics.message == deck_fault.message

    def test_a_model_the_step_names_is_still_located_on_the_pipe(self) -> None:
        """Only the deck's own miss passes through: a reference the method wrote is the caller's unknown model."""
        pipe_judge = _pipe_judge_naming_no_model()
        not_found = ModelChoiceNotFoundError(
            message="The judgment model '$unknown-method-preset' is not defined",
            model_type=ModelType.JUDGMENT,
            model_choice="$unknown-method-preset",
        )

        with pytest.raises(PipeOperatorModelChoiceError) as exc_info, pipe_judge.locating_model_choice(field_name="model"):
            raise not_found

        located = exc_info.value
        assert located.__cause__ is not_found
        assert located.field_name == "model"
        assert located.to_problem(view=ProblemView.CALLER).code == CoreCode.MODEL_UNKNOWN
