import pytest

from pipelex import pretty_print
from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.runtime_hub import get_llm_worker
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import LLMReasoningTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestLLMReasoning:
    """Integration tests for reasoning/thinking controls in LLM text generation."""

    @pytest.mark.parametrize(
        ("topic", "reasoning_effort"),
        [
            ("Low effort", ReasoningEffort.LOW),
            ("Medium effort", ReasoningEffort.MEDIUM),
            ("High effort", ReasoningEffort.HIGH),
            ("Max effort", ReasoningEffort.MAX),
        ],
    )
    @pytest.mark.parametrize(("prompt_topic", "prompt_text"), LLMReasoningTestCases.PROMPTS)
    async def test_gen_text_with_reasoning_effort(
        self,
        job_metadata: JobMetadata,
        llm_combo: ModelCombo,
        topic: str,
        reasoning_effort: ReasoningEffort,
        prompt_topic: str,
        prompt_text: str,
    ):
        """Test text generation with reasoning_effort parameter."""
        pretty_print(prompt_text, title=f"[{topic}] '{prompt_topic}' using '{llm_combo.handle}'")
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        llm_job_params = LLMJobParams(
            temperature=0.5,
            max_tokens=None,
            reasoning_effort=reasoning_effort,
        )
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(user_text=prompt_text),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
            llm_job_config=LLMJobConfig(schema_reask_max_attempts=3),
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
        except LLMCapabilityError as exc:
            pytest.skip(f"Reasoning not supported for {llm_combo.handle}: {exc}")
        assert generated_text
        pretty_print(generated_text, title=f"Result ({topic}, {prompt_topic})")

    @pytest.mark.parametrize(
        "budget",
        [
            1024,
            4096,
            16384,
        ],
    )
    @pytest.mark.parametrize(("topic", "prompt_text"), LLMReasoningTestCases.PROMPTS)
    async def test_gen_text_with_reasoning_budget(
        self,
        job_metadata: JobMetadata,
        llm_combo: ModelCombo,
        budget: int,
        topic: str,
        prompt_text: str,
    ):
        """Test text generation with explicit reasoning_budget parameter."""
        pretty_print(prompt_text, title=f"[budget={budget}] '{topic}' using '{llm_combo.handle}'")
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        llm_job_params = LLMJobParams(
            temperature=0.5,
            max_tokens=None,
            reasoning_budget=budget,
        )
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(user_text=prompt_text),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
            llm_job_config=LLMJobConfig(schema_reask_max_attempts=3),
        )
        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
        except LLMCapabilityError as exc:
            pytest.skip(f"Reasoning not supported for {llm_combo.handle}: {exc}")
        assert generated_text
        pretty_print(generated_text, title=f"Result (budget={budget}, {topic})")

    @pytest.mark.parametrize(("topic", "prompt_text"), LLMReasoningTestCases.PROMPTS)
    async def test_gen_text_without_reasoning(
        self,
        job_metadata: JobMetadata,
        llm_combo: ModelCombo,
        topic: str,
        prompt_text: str,
    ):
        """Test text generation without reasoning params (baseline)."""
        pretty_print(prompt_text, title=f"[baseline] '{topic}' using '{llm_combo.handle}'")
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        llm_job_params = LLMJobParams(
            temperature=0.5,
            max_tokens=None,
        )
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(user_text=prompt_text),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
            llm_job_config=LLMJobConfig(schema_reask_max_attempts=3),
        )
        generated_text = await llm_worker.gen_text(llm_job=llm_job)
        assert generated_text
        pretty_print(generated_text, title=f"Result (baseline, {topic})")
