"""Integration tests for the ``run_mode == DRY`` object mocks at the cogt leaf.

The dry object mock is built from the **schema-reconstructed** class — the single schema-based
mock site shared by both backends (pre-flight decision 2), exercising real datamodel-code-generator
codegen. Contracts pinned here:

- a representative ``StructuredContent`` mocks into a valid instance of the original class
  (the object-mock fidelity pin mandated by pre-flight decision 2);
- ``nb_items`` carried on ``ObjectAssignment`` controls the dry list length, falling back to
  ``dry_run_config.nb_list_items`` (eng review D11) — same for the ``--mock-inference`` arm;
- a hidden invariant the schema round-trip drops surfaces as ``MockInferenceObjectFidelityError``
  on the DRY arm too (eng review D6);
- the structured-search dry leaf returns a dict that validates against the original class.

No provider is ever called (the leaves short-circuit before any worker), so no inference marker.
"""

import pytest

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment, SearchAssignment, SearchObjectAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.dry_mock import dry_llm_gen_object, dry_llm_gen_object_list
from pipelex.cogt.content_generation.exceptions import MockInferenceObjectFidelityError
from pipelex.cogt.content_generation.search_generate import search_gen_structured
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.config import get_config
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.content_generation.test_data import ConstrainedName


class RepresentativeInvoiceLine(StructuredContent):
    """Representative structured output: mixed primitive types and an optional field."""

    label: str
    quantity: int
    unit_price: float
    discounted: bool
    note: str | None = None


class StructuredAnswer(StructuredContent):
    """Output structure for the structured-search dry arm."""

    answer: str
    confidence: float


def _dry_object_assignment(object_class: type[StructuredContent], nb_items: int | None = None) -> ObjectAssignment:
    llm_assignment = LLMAssignment(
        job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_dry_objects"),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
        llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
        llm_prompt=LLMPrompt(user_text="make objects"),
    )
    return ObjectAssignment.make_for_class(object_class=object_class, llm_assignment=llm_assignment, nb_items=nb_items)


@pytest.mark.asyncio(loop_scope="class")
class TestLeafDryObjectMocks:
    async def test_dry_object_mock_fidelity_on_representative_structured_content(self) -> None:
        """The schema-built mock validates back into the original representative class — the fidelity pin."""
        raw_mock = dry_llm_gen_object(_dry_object_assignment(RepresentativeInvoiceLine))

        revalidated = RepresentativeInvoiceLine.model_validate(raw_mock.model_dump(serialize_as_any=True))
        assert isinstance(revalidated.label, str)
        assert isinstance(revalidated.quantity, int)
        assert isinstance(revalidated.unit_price, float)
        assert isinstance(revalidated.discounted, bool)

    async def test_dry_object_list_honors_fixed_nb_items(self) -> None:
        """A fixed nb_items on the assignment controls the dry list length (D11)."""
        mocks = dry_llm_gen_object_list(_dry_object_assignment(RepresentativeInvoiceLine, nb_items=4))

        assert len(mocks) == 4

    async def test_dry_object_list_defaults_to_config_length(self) -> None:
        """Without nb_items the dry list falls back to dry_run_config.nb_list_items."""
        mocks = dry_llm_gen_object_list(_dry_object_assignment(RepresentativeInvoiceLine))

        assert len(mocks) == get_config().pipelex.dry_run_config.nb_list_items

    async def test_generator_dry_object_list_keeps_fixed_length(self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol) -> None:
        """End-to-end through ContentGenerator: a fixed nb_items survives down to the dry leaf (D11 regression)."""
        result = await content_generator.make_object_list(
            job_metadata=job_metadata,
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            object_class=RepresentativeInvoiceLine,
            llm_setting_for_object_list=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt_for_object_list=LLMPrompt(user_text="make invoice lines"),
            nb_items=3,
        )

        assert len(result) == 3
        assert all(isinstance(item, RepresentativeInvoiceLine) for item in result)

    async def test_generator_dry_arm_raises_typed_fidelity_error(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """The DRY arm of the fidelity wrapper fires (D6): a dropped invariant surfaces as the typed error."""
        with pytest.raises(MockInferenceObjectFidelityError) as exc_info:
            await content_generator.make_object(
                job_metadata=job_metadata,
                cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
                object_class=ConstrainedName,
                llm_setting_for_object=LLMSetting(model="gpt-4o", temperature=0.5),
                llm_prompt_for_object=LLMPrompt(user_text="make a prefixed name"),
            )
        assert ConstrainedName.__name__ in str(exc_info.value)

    async def test_dry_search_structured_dict_validates_against_original_class(self) -> None:
        """The structured-search dry leaf returns a dict the original output class accepts."""
        search_assignment = SearchAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_dry_search_structured"),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            query="what is pipelex?",
            search_setting=SearchSetting(model="mock-search-handle"),
        )
        search_object_assignment = SearchObjectAssignment.make_for_class(
            output_class=StructuredAnswer,
            search_assignment=search_assignment,
        )

        result_dict = await search_gen_structured(search_object_assignment=search_object_assignment)

        validated = StructuredAnswer.model_validate(result_dict)
        assert isinstance(validated.answer, str)
        assert isinstance(validated.confidence, float)
