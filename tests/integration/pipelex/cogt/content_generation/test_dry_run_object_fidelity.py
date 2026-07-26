"""Regression test for the dry-run object-mock fidelity gap (review F2).

A dry-run object mock is built from the schema-reconstructed class, then re-validated by
``ContentGenerator.make_object`` against the **original** class. An invariant the JSON-schema round-trip
cannot capture — here a custom ``@field_validator`` — is absent from the reconstructed class, so the mock
carries a value the original class rejects. The contract under test: that failure surfaces as a clear typed
``DryRunObjectFidelityError`` (naming the class and the ``examples`` / ``mock_format`` remedy), NOT an
opaque ``pydantic.ValidationError`` mid-run. A class without such a hidden invariant round-trips fine and the mock
validates — proving the guard is scoped to genuine fidelity failures, not every mock object.

No provider is ever called (the leaf mock short-circuits before ``get_llm_worker``), so this needs no
inference marker.
"""

import pytest

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.exceptions import DryRunObjectFidelityError
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.content_generation.test_data import ConstrainedName, PlainName


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunObjectFidelity:
    def _dry_cogt_run_params(self) -> CogtRunParams:
        return CogtRunParams(run_mode=PipeRunMode.DRY)

    async def test_make_object_raises_typed_error_on_fidelity_gap(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """make_object re-raises the dropped-invariant ValidationError as DryRunObjectFidelityError."""
        with pytest.raises(DryRunObjectFidelityError) as exc_info:
            await content_generator.make_object(
                job_metadata=job_metadata,
                cogt_run_params=self._dry_cogt_run_params(),
                object_class=ConstrainedName,
                llm_prompt_for_object=LLMPrompt(user_text="make a prefixed name"),
                llm_setting_for_object=LLMSetting(model="gpt-4o", temperature=0.5),
            )
        assert ConstrainedName.__name__ in str(exc_info.value)
        assert "mock_format" in str(exc_info.value)

    async def test_make_object_list_raises_typed_error_on_fidelity_gap(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """make_object_list re-raises the per-item fidelity failure as the same typed error."""
        with pytest.raises(DryRunObjectFidelityError):
            await content_generator.make_object_list(
                job_metadata=job_metadata,
                cogt_run_params=self._dry_cogt_run_params(),
                object_class=ConstrainedName,
                llm_prompt_for_object_list=LLMPrompt(user_text="make prefixed names"),
                llm_setting_for_object_list=LLMSetting(model="gpt-4o", temperature=0.5),
            )

    async def test_make_object_succeeds_when_no_hidden_invariant(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """A class whose constraints survive the round-trip mocks and re-validates without the guard firing."""
        result = await content_generator.make_object(
            job_metadata=job_metadata,
            cogt_run_params=self._dry_cogt_run_params(),
            object_class=PlainName,
            llm_prompt_for_object=LLMPrompt(user_text="make a plain name"),
            llm_setting_for_object=LLMSetting(model="gpt-4o", temperature=0.5),
        )
        assert isinstance(result, PlainName)
        assert isinstance(result.name, str)
