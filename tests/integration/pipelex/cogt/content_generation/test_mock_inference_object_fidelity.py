"""Regression test for the ``--mock-inference`` object-mock fidelity gap (review F2).

A ``--mock-inference`` object mock is built from the schema-reconstructed class, then re-validated by
``ContentGenerator.make_object`` against the **original** class. An invariant the JSON-schema round-trip
cannot capture — here a custom ``@field_validator`` — is absent from the reconstructed class, so the mock
carries a value the original class rejects. The contract under test: that failure surfaces as a clear typed
``MockInferenceObjectFidelityError`` (naming the class, pointing at ``--dry-run``), NOT an opaque
``pydantic.ValidationError`` mid-run. A class without such a hidden invariant round-trips fine and the mock
validates — proving the guard is scoped to genuine fidelity failures, not every mock object.

No provider is ever called (the leaf mock short-circuits before ``get_llm_worker``), so this needs no
inference marker.
"""

import pytest
from pydantic import field_validator

from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.exceptions import MockInferenceObjectFidelityError
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipeline.job_metadata import JobMetadata


class ConstrainedName(StructuredContent):
    """Original class with an invariant the JSON-schema round-trip cannot capture."""

    name: str

    @field_validator("name")
    @classmethod
    def _require_prefix(cls, value: str) -> str:
        if not value.startswith("PFX_"):
            msg = "name must start with 'PFX_'"
            raise ValueError(msg)
        return value


class PlainName(StructuredContent):
    """Control class whose only constraint (a plain string field) survives the round-trip."""

    name: str


@pytest.mark.asyncio(loop_scope="class")
class TestMockInferenceObjectFidelity:
    def _mock_job_metadata(self, job_metadata: JobMetadata) -> JobMetadata:
        return job_metadata.model_copy(update={"is_mock_inference": True})

    async def test_make_object_raises_typed_error_on_fidelity_gap(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """make_object re-raises the dropped-invariant ValidationError as MockInferenceObjectFidelityError."""
        with pytest.raises(MockInferenceObjectFidelityError) as exc_info:
            await content_generator.make_object(
                job_metadata=self._mock_job_metadata(job_metadata),
                object_class=ConstrainedName,
                llm_prompt_for_object=LLMPrompt(user_text="make a prefixed name"),
                llm_setting_for_object=LLMSetting(model="gpt-4o", temperature=0.5),
            )
        assert ConstrainedName.__name__ in str(exc_info.value)
        assert "--dry-run" in str(exc_info.value)

    async def test_make_object_list_raises_typed_error_on_fidelity_gap(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """make_object_list re-raises the per-item fidelity failure as the same typed error."""
        with pytest.raises(MockInferenceObjectFidelityError):
            await content_generator.make_object_list(
                job_metadata=self._mock_job_metadata(job_metadata),
                object_class=ConstrainedName,
                llm_prompt_for_object_list=LLMPrompt(user_text="make prefixed names"),
                llm_setting_for_object_list=LLMSetting(model="gpt-4o", temperature=0.5),
            )

    async def test_make_object_succeeds_when_no_hidden_invariant(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """A class whose constraints survive the round-trip mocks and re-validates without the guard firing."""
        result = await content_generator.make_object(
            job_metadata=self._mock_job_metadata(job_metadata),
            object_class=PlainName,
            llm_prompt_for_object=LLMPrompt(user_text="make a plain name"),
            llm_setting_for_object=LLMSetting(model="gpt-4o", temperature=0.5),
        )
        assert isinstance(result, PlainName)
        assert isinstance(result.name, str)
