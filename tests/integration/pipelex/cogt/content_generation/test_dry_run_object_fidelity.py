"""Where the dry-run object-mock fidelity gap still lives, now that the in-process path is fixed.

The gap only exists when the mock is built from a class *rebuilt from JSON schema*: an invariant the
round trip cannot capture — here a custom ``@field_validator`` — is absent from the rebuild, so
polyfactory fills a value the original class rejects. That is the boundary case (a worker holding only
a serialized ``ObjectAssignment``), and there the failure must still surface as a clear typed
``DryRunObjectFidelityError`` naming the class and the ``examples`` / ``mock_format`` remedy, not an
opaque ``pydantic.ValidationError`` mid-run.

In-process the caller's real class travels down to the leaf, so the mock is built from it and the gap
cannot occur — the constrained class instead fails at *build* time with the equally typed
``DryRunMockBuildError``, which names the same remedy. A class with no hidden invariant mocks and
validates cleanly either way.

No provider is ever called (the leaf mock short-circuits before ``get_llm_worker``), so this needs no
inference marker.
"""

import pytest

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator import _revalidate_against_object_class  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.content_generation.dry_mock import dry_llm_gen_object, dry_llm_gen_object_list
from pipelex.cogt.content_generation.exceptions import DryRunMockBuildError, DryRunObjectFidelityError
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.cogt.content_generation.test_data import ConstrainedName, PlainName


def _boundary_assignment(job_metadata: JobMetadata) -> ObjectAssignment:
    """The payload a worker receives across the boundary: schema only, no live class."""
    return ObjectAssignment.make_for_class(
        object_class=ConstrainedName,
        llm_assignment=LLMAssignment(
            job_metadata=job_metadata,
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt=LLMPrompt(user_text="make a prefixed name"),
        ),
        nb_items=2,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunObjectFidelity:
    def _dry_cogt_run_params(self) -> CogtRunParams:
        return CogtRunParams(run_mode=PipeRunMode.DRY)

    async def test_boundary_object_mock_raises_typed_fidelity_error(self, job_metadata: JobMetadata) -> None:
        """No class in hand: the schema-built mock fails re-validation as the typed fidelity error."""
        raw_mock = dry_llm_gen_object(_boundary_assignment(job_metadata))

        with pytest.raises(DryRunObjectFidelityError) as exc_info:
            _revalidate_against_object_class(raw_mock, object_class=ConstrainedName, is_mock_built=True)
        assert ConstrainedName.__name__ in str(exc_info.value)
        assert "mock_format" in str(exc_info.value)

    async def test_boundary_object_list_mock_raises_typed_fidelity_error(self, job_metadata: JobMetadata) -> None:
        """The list leaf carries the same boundary-path fidelity contract, per item."""
        raw_mocks = dry_llm_gen_object_list(_boundary_assignment(job_metadata))

        # Same comprehension shape as ContentGenerator.make_object_list, so this is the real composition.
        with pytest.raises(DryRunObjectFidelityError):
            _ = [_revalidate_against_object_class(raw_mock, object_class=ConstrainedName, is_mock_built=True) for raw_mock in raw_mocks]

    async def test_make_object_builds_the_mock_from_the_caller_class(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """In-process the invariant is present at build time, so the failure is a build error, not a fidelity gap."""
        with pytest.raises(DryRunMockBuildError) as exc_info:
            await content_generator.make_object(
                job_metadata=job_metadata,
                cogt_run_params=self._dry_cogt_run_params(),
                object_class=ConstrainedName,
                llm_prompt_for_object=LLMPrompt(user_text="make a prefixed name"),
                llm_setting_for_object=LLMSetting(model="gpt-4o", temperature=0.5),
            )
        assert ConstrainedName.__name__ in str(exc_info.value)
        assert "mock_format" in str(exc_info.value)

    async def test_make_object_list_builds_the_mock_from_the_caller_class(
        self, job_metadata: JobMetadata, content_generator: ContentGeneratorProtocol
    ) -> None:
        """List counterpart: same in-process resolution, same typed build error."""
        with pytest.raises(DryRunMockBuildError):
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
        """A class whose constraints survive the round-trip mocks and re-validates without any guard firing."""
        result = await content_generator.make_object(
            job_metadata=job_metadata,
            cogt_run_params=self._dry_cogt_run_params(),
            object_class=PlainName,
            llm_prompt_for_object=LLMPrompt(user_text="make a plain name"),
            llm_setting_for_object=LLMSetting(model="gpt-4o", temperature=0.5),
        )
        assert isinstance(result, PlainName)
        assert isinstance(result.name, str)
