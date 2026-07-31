"""The caller's live class must reach the provider unchanged when there is one.

Structured generation used to hand the provider a class rebuilt from the caller's JSON schema even
when the caller's real class was still on the stack. The rebuild is lossy — custom validators and
``json_schema_extra`` hints do not survive the round trip — so the provider was constrained by a
weaker contract than the one the author wrote.

These tests pin both arms, on the object leaves and on the structured-search leaf:

- in-process (a class is in hand): the provider receives *the same class object*, so every invariant
  is intact. Asserted with ``is``: a structural-equality assertion would pass against the bug, since
  structural equality is exactly what the round trip already preserved.
- at the boundary (only the serialized assignment): the class is still rebuilt from the schema, and
  the loss is still real — which is what makes the first arm worth having.

The workers are mocked, so no inference marker.
"""

from typing import Any, get_args

import pytest
from pydantic import BaseModel, Field, ValidationError, create_model, field_validator
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment, SearchAssignment, SearchObjectAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.dry_mock import dry_llm_gen_object
from pipelex.cogt.content_generation.llm_generate import llm_gen_object, llm_gen_object_list
from pipelex.cogt.content_generation.object_revalidation import revalidate_leaf_object
from pipelex.cogt.content_generation.search_generate import search_gen_structured, search_gen_structured_object
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


class HintedName(StructuredContent):
    """Carries both kinds of invariant the JSON-schema round trip drops."""

    name: str = Field(json_schema_extra={"mock_format": "name"})

    @field_validator("name")
    @classmethod
    def _require_prefix(cls, value: str) -> str:
        if not value.startswith("PFX_"):
            msg = "name must start with 'PFX_'"
            raise ValueError(msg)
        return value


class SimpleName(StructuredContent):
    """No invariant the round trip drops, so its mock builds under either class resolution."""

    name: str


class NormalizedReference(StructuredContent):
    """A validator that *transforms* rather than rejects — the shape that exposes double validation.

    A rejecting validator is idempotent and cannot tell one execution from two, which is why the
    identity assertions above are not enough on their own.
    """

    reference: str

    @field_validator("reference")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return f"INV-{value}"


class _StubListResponse(BaseModel):
    """Stand-in for the list wrapper the live leaf builds, so the mocked worker can return something."""

    items: list[HintedName]


def _live_object_assignment() -> ObjectAssignment:
    llm_assignment = LLMAssignment(
        job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_object_class_passthrough"),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        llm_setting=LLMSetting(model="test-model", temperature=0.5),
        llm_prompt=LLMPrompt(user_text="make a name"),
    )
    return ObjectAssignment.make_for_class(object_class=HintedName, llm_assignment=llm_assignment)


def _dry_object_assignment() -> ObjectAssignment:
    llm_assignment = LLMAssignment(
        job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_object_class_passthrough_dry"),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
        llm_setting=LLMSetting(model="test-model", temperature=0.5),
        llm_prompt=LLMPrompt(user_text="make a name"),
    )
    return ObjectAssignment.make_for_class(object_class=SimpleName, llm_assignment=llm_assignment)


def _live_search_object_assignment() -> SearchObjectAssignment:
    return SearchObjectAssignment.make_for_class(
        output_class=HintedName,
        search_assignment=SearchAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_search_class_passthrough"),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
            query="make a name",
            search_setting=SearchSetting(model="mock-search-handle"),
        ),
    )


def _patch_worker(mocker: MockerFixture, *, gen_object_result: BaseModel) -> Any:
    mock_worker = mocker.MagicMock()
    mock_worker.gen_object = mocker.AsyncMock(return_value=gen_object_result)
    mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", return_value=mock_worker)
    return mock_worker


def _patch_search_worker(mocker: MockerFixture, *, search_structured_result: dict[str, Any]) -> Any:
    mock_worker = mocker.MagicMock()
    mock_worker.search_structured = mocker.AsyncMock(return_value=search_structured_result)
    mocker.patch("pipelex.cogt.content_generation.search_generate._make_search_worker", return_value=mock_worker)
    mocker.patch("pipelex.cogt.content_generation.search_generate._make_search_job", return_value=mocker.MagicMock())
    return mock_worker


@pytest.mark.asyncio(loop_scope="class")
class TestObjectClassPassthrough:
    async def test_live_leaf_hands_the_provider_the_caller_class_itself(self, mocker: MockerFixture) -> None:
        """Identity, not equality: the provider gets the very class object the caller passed."""
        mock_worker = _patch_worker(mocker, gen_object_result=HintedName(name="PFX_ok"))

        await llm_gen_object(_live_object_assignment(), object_class=HintedName)

        assert mock_worker.gen_object.await_args.kwargs["schema"] is HintedName

    async def test_live_leaf_preserves_validator_and_schema_hints(self, mocker: MockerFixture) -> None:
        """The class the provider receives still enforces the custom validator and carries its hints."""
        mock_worker = _patch_worker(mocker, gen_object_result=HintedName(name="PFX_ok"))

        await llm_gen_object(_live_object_assignment(), object_class=HintedName)

        received_class = mock_worker.gen_object.await_args.kwargs["schema"]
        with pytest.raises(ValidationError):
            received_class.model_validate({"name": "no_prefix"})
        assert received_class.model_json_schema()["properties"]["name"]["mock_format"] == "name"

    async def test_boundary_leaf_still_rebuilds_from_the_schema_and_loses_the_invariants(self, mocker: MockerFixture) -> None:
        """Without a class in hand the leaf rebuilds — unchanged behavior, and the loss is real.

        This is the control for the two tests above: it shows the reconstructed class accepts data the
        author's class rejects, which is exactly what passing the live class stops.
        """
        mock_worker = _patch_worker(mocker, gen_object_result=HintedName(name="PFX_ok"))

        await llm_gen_object(_live_object_assignment())

        rebuilt_class = mock_worker.gen_object.await_args.kwargs["schema"]
        assert rebuilt_class is not HintedName
        assert rebuilt_class.__name__ == HintedName.__name__
        # The custom validator did not survive the round trip.
        assert rebuilt_class.model_validate({"name": "no_prefix"}).name == "no_prefix"

    async def test_live_list_leaf_wraps_the_caller_class_itself(self, mocker: MockerFixture) -> None:
        """The list wrapper's item type is the caller's class, not a rebuild of it."""
        mock_worker = _patch_worker(mocker, gen_object_result=_StubListResponse(items=[HintedName(name="PFX_ok")]))

        await llm_gen_object_list(_live_object_assignment(), object_class=HintedName)

        list_schema = mock_worker.gen_object.await_args.kwargs["schema"]
        item_annotation = list_schema.model_fields["items"].annotation
        assert get_args(item_annotation)[0] is HintedName

    async def test_boundary_list_leaf_still_wraps_a_rebuilt_class(self, mocker: MockerFixture) -> None:
        """List counterpart of the boundary control: no class in hand still means a rebuilt item class."""
        mock_worker = _patch_worker(mocker, gen_object_result=_StubListResponse(items=[HintedName(name="PFX_ok")]))

        await llm_gen_object_list(_live_object_assignment())

        list_schema = mock_worker.gen_object.await_args.kwargs["schema"]
        item_annotation = list_schema.model_fields["items"].annotation
        assert get_args(item_annotation)[0] is not HintedName

    async def test_caller_validators_run_exactly_once(self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol) -> None:
        """Handing the live class down must make the caller's validator constrain the result once, not twice.

        The leaf now builds from the caller's class, so its validators already ran there. Re-validating
        the result against the same class would run them again on data they had already normalized —
        ``INV-INV-…`` — which is the opposite of honoring the invariant this change exists to preserve.
        """
        result = await content_generator.make_object(
            job_metadata=job_metadata,
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            object_class=NormalizedReference,
            llm_prompt_for_object=LLMPrompt(user_text="make a reference"),
            llm_setting_for_object=LLMSetting(model="test-model", temperature=0.5),
        )

        assert result.reference.startswith("INV-")
        assert not result.reference.startswith("INV-INV-")

    async def test_caller_validators_run_exactly_once_per_list_item(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """The list path revalidates per item, so it carries the same once-only contract."""
        results = await content_generator.make_object_list(
            job_metadata=job_metadata,
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            object_class=NormalizedReference,
            llm_prompt_for_object_list=LLMPrompt(user_text="make references"),
            llm_setting_for_object_list=LLMSetting(model="test-model", temperature=0.5),
            nb_items=3,
        )

        assert len(results) == 3
        # Both directions: `not INV-INV-` alone would also pass if the validator never ran at all.
        assert all(item.reference.startswith("INV-") for item in results)
        assert all(not item.reference.startswith("INV-INV-") for item in results)

    async def test_instructor_style_subclass_is_returned_without_revalidation(self, mocker: MockerFixture) -> None:
        """Instructor returns a *subclass* of the response model, not the class itself.

        `create_model(cls.__name__, __base__=(cls, OpenAISchema))` is what actually comes back, which is
        why the conversion short-circuits on `isinstance` and not `type(...) is`. A `type(...) is` check
        would miss it and reinstate the double validation on every real provider call.
        """
        wrapped_class = create_model("NormalizedReference", __base__=NormalizedReference)
        _patch_worker(mocker, gen_object_result=wrapped_class(reference="123"))

        raw_obj = await llm_gen_object(
            ObjectAssignment.make_for_class(
                object_class=NormalizedReference,
                llm_assignment=LLMAssignment(
                    job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_wrapped"),
                    cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
                    llm_setting=LLMSetting(model="test-model", temperature=0.5),
                    llm_prompt=LLMPrompt(user_text="make a reference"),
                ),
            ),
            object_class=NormalizedReference,
        )

        assert type(raw_obj) is not NormalizedReference
        assert isinstance(raw_obj, NormalizedReference)
        result = revalidate_leaf_object(raw_obj, object_class=NormalizedReference, is_mock_built=False)
        assert result.reference == "INV-123"

    async def test_live_search_leaf_hands_the_provider_the_caller_class_itself(self, mocker: MockerFixture) -> None:
        """The structured-search leaf carries the same contract as the object leaf, asserted the same way."""
        mock_worker = _patch_search_worker(mocker, search_structured_result={"name": "PFX_ok"})

        await search_gen_structured_object(_live_search_object_assignment(), output_class=HintedName)

        assert mock_worker.search_structured.await_args.kwargs["schema"] is HintedName

    async def test_boundary_search_leaf_still_rebuilds_from_the_schema(self, mocker: MockerFixture) -> None:
        """Control for the search arm: no class in hand still means a rebuilt class and a raw dict out."""
        mock_worker = _patch_search_worker(mocker, search_structured_result={"name": "no_prefix"})

        result = await search_gen_structured(search_object_assignment=_live_search_object_assignment())

        rebuilt_class = mock_worker.search_structured.await_args.kwargs["schema"]
        assert rebuilt_class is not HintedName
        assert rebuilt_class.__name__ == HintedName.__name__
        assert result == {"name": "no_prefix"}

    async def test_dry_leaf_resolves_the_class_the_same_way_as_the_live_leaf(self) -> None:
        """Both run modes take the same path — asserted directly, not inferred from two passing tests.

        If only the live leaf took the fast path, the dry mock would be built from a *weaker* class than
        the one the provider is constrained by, making the mock less faithful than the thing it mocks.
        """
        with_class = dry_llm_gen_object(_dry_object_assignment(), object_class=SimpleName)
        assert isinstance(with_class, SimpleName)

        without_class = dry_llm_gen_object(_dry_object_assignment())
        assert not isinstance(without_class, SimpleName)
