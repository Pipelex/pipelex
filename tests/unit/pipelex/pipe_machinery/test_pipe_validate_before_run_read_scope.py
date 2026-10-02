"""On a run with a read scope, the input pre-check does not probe the host's disk for a local path.

The pre-check's resource validation only asks whether a local path exists. A scoped run reads no local
path at all, and its leaves refuse one before any IO, so probing first would stat the host's disk on
the method's say-so, and a missing path failing there while an existing one is refused later would
tell the caller which files exist. An unscoped live run still reports a missing file there.
"""

from typing import Callable

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.exceptions import PipeRunInputsError
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

MISSING_PATH = "/nonexistent/read-scope-probe/photo.png"


def _pipe_llm() -> PipeLLM:
    return PipeFactory[PipeLLM].make_from_blueprint(
        domain_code="test_domain",
        pipe_code="describe_photo",
        blueprint=PipeLLMBlueprint(
            description="Describe a photo",
            inputs={"photo": "native.Image"},
            output="native.Text",
            prompt="Describe $photo",
        ),
    )


def _job_metadata(*, read_scope: str | None) -> JobMetadata:
    storage_scope = "org_abc/mt_1/run_1" if read_scope is not None else "run_1"
    return JobMetadata(run_metadata=RunMetadata(user_id="u", pipeline_run_id="run_1", storage_scope=storage_scope, read_scope=read_scope))


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBeforeRunReadScope:
    async def test_a_scoped_live_run_does_not_probe_a_local_path(self, load_empty_library: Callable[[], None]) -> None:
        load_empty_library()
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
                content=ImageContent(url=MISSING_PATH),
                name="photo",
            )
        )

        await _pipe_llm().validate_before_run(
            job_metadata=_job_metadata(read_scope="org_abc"),
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
        )

    async def test_an_unscoped_live_run_still_reports_a_missing_file(self, load_empty_library: Callable[[], None]) -> None:
        load_empty_library()
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
                content=ImageContent(url=MISSING_PATH),
                name="photo",
            )
        )

        with pytest.raises(PipeRunInputsError, match="invalid resource"):
            await _pipe_llm().validate_before_run(
                job_metadata=_job_metadata(read_scope=None),
                working_memory=working_memory,
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            )
