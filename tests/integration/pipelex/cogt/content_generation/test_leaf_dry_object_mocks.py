"""Integration tests for the ``run_mode == DRY`` object mocks at the cogt leaf.

These call the leaves with no live class in hand, so the mock is built from the **schema-reconstructed**
class (pre-flight decision 2), exercising real datamodel-code-generator codegen. Contracts pinned here:

- a representative ``StructuredContent`` mocks into a valid instance of the original class
  (the object-mock fidelity pin mandated by pre-flight decision 2);
- ``nb_items`` carried on ``ObjectAssignment`` controls the dry list length, falling back to
  ``dry_run_config.nb_list_items`` (eng review D11);
- the structured-search dry leaf splits the same way the object leaf does: at the boundary it returns a
  dict built from the schema rebuild, where a dropped invariant surfaces as ``DryRunObjectFidelityError``
  (eng review D6); in-process it mocks the caller's real class, where that invariant is present at build
  time and an unsatisfiable one fails as ``DryRunMockBuildError`` instead.

The object leaf's own fidelity arms live in ``test_dry_run_object_fidelity.py``, which separates the
boundary case (still schema-rebuilt, still the fidelity error) from the in-process case (built from the
caller's real class).

No provider is ever called (the leaves short-circuit before any worker), so no inference marker.
"""

import pytest
from pydantic import field_validator

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment, SearchAssignment, SearchObjectAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.dry_mock import dry_llm_gen_object, dry_llm_gen_object_list
from pipelex.cogt.content_generation.exceptions import DryRunMockBuildError, DryRunObjectFidelityError
from pipelex.cogt.content_generation.object_revalidation import revalidate_leaf_data
from pipelex.cogt.content_generation.search_generate import search_gen_structured
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.config import get_config
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
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


class NormalizedAnswer(StructuredContent):
    """Output structure whose validator *transforms* — the shape that exposes a double validation."""

    answer: str

    @field_validator("answer")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return f"INV-{value}"


class SpecWithPipeCode(StructuredContent):
    """Pipe-spec-shaped item: carries the ``pipe_code`` field the mock_main coordination targets."""

    pipe_code: str
    description: str


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

    @pytest.mark.parametrize("nb_items", [4, 0])
    async def test_dry_object_list_honors_fixed_nb_items(self, nb_items: int) -> None:
        """A fixed nb_items on the assignment controls the dry list length (D11) — including an explicit 0."""
        mocks = dry_llm_gen_object_list(_dry_object_assignment(RepresentativeInvoiceLine, nb_items=nb_items))

        assert len(mocks) == nb_items

    async def test_dry_object_list_stamps_mock_main_coordination(self) -> None:
        """The dry leaf stamps the first pipe-spec-shaped item with pipe_code='mock_main' (D3).

        This is what keeps builder-bundle dry-validation working through the leaf mock: the mocked
        ``BundleHeaderSpec.main_pipe`` (``examples=["mock_main"]``) must name an existing pipe.
        """
        mocks = dry_llm_gen_object_list(_dry_object_assignment(SpecWithPipeCode, nb_items=3))

        first_item_pipe_code = getattr(mocks[0], "pipe_code", None)
        assert first_item_pipe_code == "mock_main"

    async def test_dry_object_list_stamps_regardless_of_mock_usage(self) -> None:
        """The stamp is unconditional on the is_mock_usage sub-flag — it only changes reporting (D3)."""
        llm_assignment = LLMAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_mock_usage_stamp"),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY, is_mock_usage=True),
            llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt=LLMPrompt(user_text="make specs"),
        )
        object_assignment = ObjectAssignment.make_for_class(object_class=SpecWithPipeCode, llm_assignment=llm_assignment, nb_items=3)

        mocks = dry_llm_gen_object_list(object_assignment)

        first_item_pipe_code = getattr(mocks[0], "pipe_code", None)
        assert first_item_pipe_code == "mock_main"

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

    async def test_boundary_dry_search_structured_fidelity_gap_raises_typed_error(self, job_metadata: JobMetadata) -> None:
        """The structured-search *boundary* carries the same D6 fidelity guard as the object paths.

        Scoped to the boundary composition — the leaf that holds only the serialized assignment, plus the
        submitter that re-validates its dict — exactly as the object path's fidelity test is. In-process
        the mock is built from the caller's real class, so this gap cannot occur there; the constrained
        class fails earlier and louder instead (see the test below).
        """
        search_object_assignment = SearchObjectAssignment.make_for_class(
            output_class=ConstrainedName,
            search_assignment=self._dry_search_assignment(job_metadata),
        )

        result_dict = await search_gen_structured(search_object_assignment=search_object_assignment)

        with pytest.raises(DryRunObjectFidelityError) as exc_info:
            revalidate_leaf_data(result_dict, object_class=ConstrainedName, is_mock_built=True)
        assert ConstrainedName.__name__ in str(exc_info.value)

    async def test_in_process_dry_search_structured_builds_the_mock_from_the_caller_class(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """In-process the invariant is present at build time, so the failure is a build error, not a fidelity gap."""
        with pytest.raises(DryRunMockBuildError) as exc_info:
            await content_generator.make_search_structured(
                output_structure_class=ConstrainedName,
                search_assignment=self._dry_search_assignment(job_metadata),
            )
        assert ConstrainedName.__name__ in str(exc_info.value)
        assert "mock_format" in str(exc_info.value)

    async def test_in_process_dry_search_structured_runs_the_caller_validators_exactly_once(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """The mock is built from the caller's class, so its validators must not run again on a dump of it.

        The search leaf is dict-out at the boundary, and dumping the in-process mock for the submitter to
        re-validate is exactly how a transforming validator would produce ``INV-INV-…`` here.
        """
        result = await content_generator.make_search_structured(
            output_structure_class=NormalizedAnswer,
            search_assignment=self._dry_search_assignment(job_metadata),
        )

        assert isinstance(result, NormalizedAnswer)
        assert result.answer.startswith("INV-")
        assert not result.answer.startswith("INV-INV-")

    async def test_boundary_dry_search_structured_dict_validates_against_original_class(self) -> None:
        """The structured-search dry boundary leaf returns a dict the original output class accepts."""
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

    def _dry_search_assignment(self, job_metadata: JobMetadata) -> SearchAssignment:
        return SearchAssignment(
            job_metadata=job_metadata,
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            query="what is pipelex?",
            search_setting=SearchSetting(model="mock-search-handle"),
        )
