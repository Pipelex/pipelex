"""A real text job for driving an LLM worker's text generation into its stop check.

The stop check names the job's pipe and the output tokens the worker read into the job's usage, so the job is a
real `LLMJob` whose usage is seeded empty, as `llm_job_before_start` seeds it, rather than a mock whose every
attribute answers.
"""

from __future__ import annotations

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.job_metadata import JobMetadata, RunMetadata

STOP_TEST_PIPE_CODE = "summarize_contract"
STOP_TEST_PARTIAL_TEXT = "The contract binds the parties to deliver the goods by the end of"


def make_text_llm_job(*, pipe_code: str | None = STOP_TEST_PIPE_CODE, max_tokens: int | None = None) -> LLMJob:
    """A text job for the given pipe, its token usage seeded empty and its max_tokens as given."""
    job_metadata = JobMetadata(
        run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="test-user", pipeline_run_id="test-run"),
        pipe_code=pipe_code,
    )
    tokens_usage = LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="test-model",
        inference_model_id="test-model-id",
        unit_costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 1.0},
        nb_tokens_by_category={},
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(system_text="You are a careful summarizer.", user_text="Summarize the contract."),
        job_params=LLMJobParams(temperature=0.5, max_tokens=max_tokens),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(llm_tokens_usage=tokens_usage),
    )
