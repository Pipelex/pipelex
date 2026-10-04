from typing import Any

from typing_extensions import override

from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_machinery.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge, make_judgment_question
from pipelex.pipe_operators.judge.pipe_judge_blueprint import PipeJudgeBlueprint


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
        criteria = blueprint.criteria
        judgment_question = make_judgment_question(
            question_template=blueprint.question,
            options=blueprint.options,
            levels=blueprint.levels,
            yes_criterion=criteria.yes if criteria is not None else None,
            no_criterion=criteria.no if criteria is not None else None,
        )
        return PipeJudge(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            output=output,
            inputs=inputs,
            judgment_choice=blueprint.model,
            judgment_question=judgment_question,
            threshold=blueprint.threshold,
        )
