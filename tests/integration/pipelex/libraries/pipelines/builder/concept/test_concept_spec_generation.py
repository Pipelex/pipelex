import pytest

from pipelex import log, pretty_print
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.hub import get_llm_worker
from pipelex.libraries.pipelines.builder.concept.concept_spec import ConceptSpec
from tests.integration.pipelex.libraries.pipelines.builder.concept.integration_test_data import ConceptSpecGenerationTestCases


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestConceptSpecGeneration:
    """Integration tests for generating ConceptSpec objects using LLM.

    These tests verify that LLMs can generate valid ConceptSpec objects
    from natural language prompts describing various concept shapes.
    """

    @pytest.mark.parametrize(("topic", "user_prompt"), ConceptSpecGenerationTestCases.TEST_CASES)
    async def test_generate_concept_spec(
        self,
        llm_job_params: LLMJobParams,
        llm_handle: str,
        topic: str,
        user_prompt: str,
    ):
        log.info(f"Testing {topic} with llm_handle '{llm_handle}'")

        # Get the LLM worker
        llm_worker = get_llm_worker(llm_handle=llm_handle)

        # Skip if object generation is not supported
        if not llm_worker.is_gen_object_supported:
            pytest.skip(f"LLM worker '{llm_worker.desc}' does not support object generation")

        log.info(f"Using llm_worker: {llm_worker.desc}")

        # Create the LLM job with the prompt
        llm_job = LLMJobFactory.make_llm_job_from_prompt_contents(
            system_text="You are an expert at generating concept specifications for a data modeling system.",
            user_text=user_prompt,
            llm_job_params=llm_job_params,
        )

        # Generate the ConceptSpec object
        generated_concept_spec = await llm_worker.gen_object(llm_job=llm_job, schema=ConceptSpec)

        # Display the result
        pretty_print(generated_concept_spec, title=f"Generated ConceptSpec for '{topic}' using {llm_handle}")

        # Basic validation: if we got here without exceptions, the ConceptSpec was created successfully
        # The Pydantic validation and field validators have already run
        assert generated_concept_spec is not None
        assert isinstance(generated_concept_spec, ConceptSpec)
        assert generated_concept_spec.the_concept_code
        assert generated_concept_spec.description

        log.info(f"✓ Successfully generated ConceptSpec for '{topic}': {generated_concept_spec.the_concept_code}")
