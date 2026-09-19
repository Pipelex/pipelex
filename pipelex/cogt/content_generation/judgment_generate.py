"""Framework-agnostic judgment leaf, sibling of ``search_generate``.

This coroutine is the single place a judgment's provider spend happens. It takes a serializable
``JudgmentAssignment``, rebuilds the ``JudgmentJob``, resolves the worker from the model handle, and
runs it. The direct ``ContentGenerator`` calls it inline; a distributed orchestrator calls it inside
an activity so the result is recorded in the run's history and any failure is converted to a
terminal error.

There is only one entry point here, where the search leaf has three. A judgment's answers are plain
models of this package's own — no caller class travels down and no schema has to be shipped — so the
in-process arm and the boundary arm would be the same function, and there is nothing to split.
"""

from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.content_generation.dry_mock import dry_judgment_gen_answers
from pipelex.cogt.judgment.judgment_job import JudgmentJob
from pipelex.cogt.judgment.judgment_job_factory import JudgmentJobFactory
from pipelex.cogt.judgment.judgment_models import JudgmentAnswer
from pipelex.cogt.judgment.judgment_worker_abstract import JudgmentWorkerAbstract
from pipelex.cogt.judgment.judgment_worker_factory import JudgmentWorkerFactory
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.runtime_hub import get_model_deck, get_report_delegate


def _make_judgment_worker(judgment_assignment: JudgmentAssignment) -> JudgmentWorkerAbstract:
    model_deck = get_model_deck()
    inference_model = model_deck.get_required_inference_model(
        model_handle=judgment_assignment.judgment_setting.model,
        model_type=ModelType.JUDGMENT,
    )
    return JudgmentWorkerFactory.make_judgment_worker(inference_model, reporting_delegate=get_report_delegate())


def _make_judgment_job(judgment_assignment: JudgmentAssignment) -> JudgmentJob:
    return JudgmentJobFactory.make_judgment_job(
        state=judgment_assignment.state,
        questions=judgment_assignment.questions,
        judgment_setting=judgment_assignment.judgment_setting,
        job_metadata=judgment_assignment.job_metadata,
    )


async def judgment_gen_answers(judgment_assignment: JudgmentAssignment) -> dict[str, JudgmentAnswer]:
    if judgment_assignment.cogt_run_params.run_mode.is_dry:
        return dry_judgment_gen_answers(judgment_assignment)
    worker = _make_judgment_worker(judgment_assignment)
    judgment_job = _make_judgment_job(judgment_assignment)
    return await worker.judge(judgment_job)
