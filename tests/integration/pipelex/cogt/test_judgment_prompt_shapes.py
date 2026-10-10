"""Each way an evidence prompt renders an input, proven live against the judging model.

A PipeJudge's evidence is its rendered prompt, so the judging model reads each input as the template
renders it: a text block under its name, a number, a yes/no or a date inline, a structure or a list as
a block. Each case is a pair of memories that differ only in the value under test, rendered by the same
user-prompt assembly the operator calls, so the evidence sent is the evidence a run sends. The verdict
must land clearly on the yes side for one and clearly on the no side for the other: a model that
ignored or misread the rendering could not flip with the value.
"""

import pytest

from pipelex.cogt.judgment.judgment_job_factory import JudgmentJobFactory
from pipelex.cogt.judgment.judgment_models import JudgmentPrompt, YesNoAnswer, YesNoQuestion
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.judgment.judgment_worker_factory import JudgmentWorkerFactory
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.kernel.prompt_assembly import UserPromptContent, assemble_user_prompt
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.runtime_hub import get_model_deck
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory
from tests.integration.pipelex.cogt.test_data import JudgmentPromptShapeCase, JudgmentPromptShapeCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


async def _evidence(*, prompt: str, inputs: dict[str, StuffContent]) -> JudgmentPrompt:
    """The evidence a PipeJudge with this prompt would send over these inputs, assembled by the operator's own assembly."""
    anything = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
    stuffs = [StuffFactory.make_stuff(concept=anything, content=content, name=name) for name, content in inputs.items()]
    memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=stuffs)
    assembled = await assemble_user_prompt(
        prompt_content=UserPromptContent(template=TemplateBlueprint(template=prompt, category=TemplateCategory.LLM_PROMPT)),
        context_provider=memory,
        templating_style=resolve_templating_style(authored=None),
    )
    assert not assembled.images
    assert not assembled.documents
    return JudgmentPrompt(text=assembled.text)


async def _probability_of_yes(*, judgment_combo: ModelCombo, job_metadata: JobMetadata, evidence: JudgmentPrompt, question: YesNoQuestion) -> float:
    inference_model = get_model_deck().get_required_inference_model(model_handle=judgment_combo.handle, model_type=ModelType.JUDGMENT)
    worker = JudgmentWorkerFactory.make_judgment_worker(inference_model)
    job = JudgmentJobFactory.make_judgment_job(
        prompt=evidence,
        questions={"question": question},
        judgment_setting=JudgmentSetting(model=judgment_combo.handle),
        job_metadata=job_metadata,
    )
    answer = (await worker.judge(job))["question"]
    assert isinstance(answer, YesNoAnswer)
    assert answer.probability is not None
    return answer.probability


@pytest.mark.judgment
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestJudgmentPromptShapes:
    @pytest.mark.parametrize(("topic", "case"), JudgmentPromptShapeCases.SHAPE_CASES)
    async def test_the_verdict_follows_the_value_the_prompt_renders(
        self,
        judgment_combo: ModelCombo,
        job_metadata: JobMetadata,
        topic: str,
        case: JudgmentPromptShapeCase,
    ) -> None:
        """Both renderings differ only in the value under test, and the verdict flips with it."""
        yes_evidence = await _evidence(prompt=case.prompt, inputs=case.yes_inputs)
        no_evidence = await _evidence(prompt=case.prompt, inputs=case.no_inputs)
        assert yes_evidence.text != no_evidence.text

        yes_probability = await _probability_of_yes(
            judgment_combo=judgment_combo, job_metadata=job_metadata, evidence=yes_evidence, question=case.question
        )
        no_probability = await _probability_of_yes(
            judgment_combo=judgment_combo, job_metadata=job_metadata, evidence=no_evidence, question=case.question
        )
        print(f"{topic}: yes side {yes_probability:.3f} over {yes_evidence.text!r}, no side {no_probability:.3f} over {no_evidence.text!r}")

        assert yes_probability >= JudgmentPromptShapeCases.CLEAR_YES, f"The yes-side evidence was not read as yes: {yes_probability:.3f}"
        assert no_probability <= JudgmentPromptShapeCases.CLEAR_NO, f"The no-side evidence was not read as no: {no_probability:.3f}"
