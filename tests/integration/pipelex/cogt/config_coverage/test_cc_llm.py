import pytest

from pipelex import log, pretty_print
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.service_hub import get_inference_manager
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestConfigCoverageLLM:
    async def test_gen_text(self, job_metadata: JobMetadata, llm_job_params: LLMJobParams, llm_combo: ModelCombo) -> None:
        """Verify that text generation works for this Portkey config."""
        log.info(f"Config coverage: testing LLM '{llm_combo.handle}'")
        llm_worker = get_inference_manager().get_llm_worker(llm_handle=llm_combo.handle)
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                system_text=None,
                user_text="In one short sentence (< 5 words), who is Bill Gates?",
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text)
