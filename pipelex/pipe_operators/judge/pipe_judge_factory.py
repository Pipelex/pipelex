from typing import Any

from typing_extensions import override

from pipelex.cogt.judgment.judgment_models import RatingLevel, YesNoCriteria
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.kernel.prompt_assembly import UserPromptContent
from pipelex.pipe_machinery.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge, PipeJudgeQuestion, make_judgment_question
from pipelex.pipe_operators.judge.pipe_judge_blueprint import JudgeYesNoCriteria, PipeJudgeBlueprint
from pipelex.pipe_operators.shared.template_file_references import analyze_template_file_references
from pipelex.tools.jinja2.template_category import TemplateCategory


class PipeJudgeFactory(PipeFactoryProtocol[PipeJudgeBlueprint, PipeJudge]):
    @classmethod
    @override
    def make(
        cls,
        *,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeJudgeBlueprint,
    ) -> PipeJudge:
        # Template analyzers read the slot grammar only, so they get the concept-spec projection.
        input_specs = blueprint.inputs_concept_specs or {}
        # The evidence is built exactly as a PipeLLM's prompt is: its template and the files it references.
        prompt_files = analyze_template_file_references(template_source=blueprint.prompt, input_specs=input_specs, domain_code=domain_code)
        prompt_content = UserPromptContent(
            template=TemplateBlueprint(template=blueprint.prompt, category=TemplateCategory.LLM_PROMPT),
            image_references=prompt_files.image_references or None,
            document_references=prompt_files.document_references or None,
        )
        question: PipeJudgeQuestion | None = None
        if blueprint.question is not None:
            question = _make_pipe_judge_question(
                question_template=blueprint.question,
                options=blueprint.options,
                levels=blueprint.rating_levels,
                criteria=blueprint.criteria,
                threshold=blueprint.threshold,
                input_specs=input_specs,
                domain_code=domain_code,
            )
        questions: dict[str, PipeJudgeQuestion] | None = None
        if blueprint.questions is not None:
            questions = {
                question_name: _make_pipe_judge_question(
                    question_template=question_blueprint.question,
                    options=question_blueprint.options,
                    levels=question_blueprint.rating_levels,
                    criteria=question_blueprint.criteria,
                    threshold=question_blueprint.threshold,
                    input_specs=input_specs,
                    domain_code=domain_code,
                )
                for question_name, question_blueprint in blueprint.questions.items()
            }
        return PipeJudge(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            output=output,
            inputs=inputs,
            judgment_choice=blueprint.model,
            prompt_content=prompt_content,
            question=question,
            questions=questions,
        )


def _make_pipe_judge_question(
    *,
    question_template: str,
    options: dict[str, str] | None,
    levels: list[RatingLevel] | None,
    criteria: JudgeYesNoCriteria | None,
    threshold: float | None,
    input_specs: dict[str, str],
    domain_code: str,
) -> PipeJudgeQuestion:
    """One question as the operator holds it, built alike whether the step asks it alone or among several.

    The question presents no file: whatever image or document it reads is held for the load to refuse.
    """
    question_files = analyze_template_file_references(
        template_source=question_template, input_specs=input_specs, domain_code=domain_code, template_category=TemplateCategory.BASIC
    )
    judgment_question = make_judgment_question(
        question_template=question_template,
        options=options,
        levels=levels,
        criteria=YesNoCriteria(yes=criteria.yes, no=criteria.no) if criteria is not None else None,
    )
    return PipeJudgeQuestion(
        judgment_question=judgment_question,
        threshold=threshold,
        image_references=question_files.image_references or None,
        document_references=question_files.document_references or None,
    )
