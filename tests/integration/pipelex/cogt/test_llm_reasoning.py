import pytest

from pipelex import pretty_print
from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, ReasoningEffort
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.runtime_hub import get_llm_worker
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import LLMReasoningTestCases, ReasonedAnswer
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


def _skip_unless_the_model_reasons(llm_worker: LLMWorkerAbstract) -> None:
    """Skip a model whose spec declares no reasoning, read from the spec before any call.

    The structured tests never skip on a caught LLMCapabilityError, so a worker that regresses to refusing
    a reasoning setting on a structured output fails them instead of skipping.
    """
    if llm_worker.inference_model.thinking_mode == ThinkingMode.NONE:
        pytest.skip(f"'{llm_worker.inference_model.name}' declares thinking_mode=none")


def _skip_unless_the_model_structures(llm_worker: LLMWorkerAbstract) -> None:
    """Skip a model whose spec declares no structured output, such as the text-only Magistral models."""
    if not llm_worker.is_gen_object_supported:
        pytest.skip(f"'{llm_worker.inference_model.name}' does not support object generation")


def _skip_unless_the_model_takes_a_budget(llm_worker: LLMWorkerAbstract) -> None:
    """Skip a model that takes no explicit reasoning budget: only manual thinking on a budget-mapped worker does."""
    _skip_unless_the_model_reasons(llm_worker)
    if llm_worker.inference_model.thinking_mode != ThinkingMode.MANUAL or getattr(llm_worker, "reasoning_budget_family", None) is None:
        pytest.skip(f"'{llm_worker.inference_model.name}' takes a reasoning effort, not a budget")


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

    @pytest.mark.parametrize(
        ("topic", "reasoning_effort"),
        [
            ("Low effort", ReasoningEffort.LOW),
            ("High effort", ReasoningEffort.HIGH),
        ],
    )
    async def test_gen_object_with_reasoning_effort(
        self,
        job_metadata: JobMetadata,
        llm_combo: ModelCombo,
        topic: str,
        reasoning_effort: ReasoningEffort,
    ):
        """A reasoning effort on a structured output reaches the provider and the object validates."""
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        _skip_unless_the_model_structures(llm_worker)
        _skip_unless_the_model_reasons(llm_worker)
        pretty_print(LLMReasoningTestCases.STRUCTURED_PROMPT, title=f"[{topic}] structured using '{llm_combo.handle}'")
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(user_text=LLMReasoningTestCases.STRUCTURED_PROMPT),
            job_metadata=job_metadata,
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=None, reasoning_effort=reasoning_effort),
            llm_job_config=LLMJobConfig(schema_reask_max_attempts=3),
        )
        reasoned_answer = await llm_worker.gen_object(llm_job=llm_job, schema=ReasonedAnswer)
        assert isinstance(reasoned_answer, ReasonedAnswer)
        assert reasoned_answer.steps
        pretty_print(reasoned_answer, title=f"Result ({topic}, structured)")

    @pytest.mark.parametrize("budget", [1024, 4096])
    async def test_gen_object_with_reasoning_budget(
        self,
        job_metadata: JobMetadata,
        llm_combo: ModelCombo,
        budget: int,
    ):
        """An explicit reasoning budget on a structured output reaches the provider and the object validates."""
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        _skip_unless_the_model_structures(llm_worker)
        _skip_unless_the_model_takes_a_budget(llm_worker)
        pretty_print(LLMReasoningTestCases.STRUCTURED_PROMPT, title=f"[budget={budget}] structured using '{llm_combo.handle}'")
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(user_text=LLMReasoningTestCases.STRUCTURED_PROMPT),
            job_metadata=job_metadata,
            llm_job_params=LLMJobParams(temperature=0.5, max_tokens=None, reasoning_budget=budget),
            llm_job_config=LLMJobConfig(schema_reask_max_attempts=3),
        )
        reasoned_answer = await llm_worker.gen_object(llm_job=llm_job, schema=ReasonedAnswer)
        assert isinstance(reasoned_answer, ReasonedAnswer)
        assert reasoned_answer.steps
        pretty_print(reasoned_answer, title=f"Result (budget={budget}, structured)")
