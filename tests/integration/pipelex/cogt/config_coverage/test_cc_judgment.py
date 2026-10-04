import pytest

from pipelex import log, pretty_print
from pipelex.cogt.judgment.judgment_job_factory import JudgmentJobFactory
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.judgment.judgment_worker_factory import JudgmentWorkerFactory
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.runtime_hub import get_model_deck
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import JudgmentTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.judgment
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestConfigCoverageJudgment:
    async def test_judgment(self, judgment_combo: ModelCombo, job_metadata: JobMetadata) -> None:
        """Verify that a judgment answers for this model and backend."""
        log.info(f"Config coverage: testing judgment '{judgment_combo.handle}'")
        inference_model = get_model_deck().get_required_inference_model(model_handle=judgment_combo.handle, model_type=ModelType.JUDGMENT)
        worker = JudgmentWorkerFactory.make_judgment_worker(inference_model)
        judgment_job = JudgmentJobFactory.make_judgment_job(
            state=JudgmentTestCases.STATE,
            questions={"is_urgent": JudgmentTestCases.IS_URGENT},
            judgment_setting=JudgmentSetting(model=judgment_combo.handle),
            job_metadata=job_metadata,
        )
        answers = await worker.judge(judgment_job)
        assert set(answers) == {"is_urgent"}
        pretty_print(answers, title=f"Judgment answer for '{judgment_combo.handle}'")
