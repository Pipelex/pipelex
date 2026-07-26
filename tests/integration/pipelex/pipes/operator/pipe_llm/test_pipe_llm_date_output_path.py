"""Phase 3 verification: a PipeLLM whose output is native Date takes the object path.

`Date` is not Text-compatible, so PipeLLM's output dispatch (`pipe_llm.py`) must route it down the
object path — handing `DateContent` (whose `model_json_schema()` carries the LLM-facing anti-fabrication
field descriptions, a contract not a decoration) to the content generator's `make_object`, never the
text path (`make_llm_text`). A spy on the generator pins both the path selection and the exact class
whose schema is handed down. Runs in DRY mode: the leaf mock short-circuits inside `make_object`, so no
provider is ever called (hence no inference marker).
"""

from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.date_content import DateContent
from pipelex.interpreter_hub import get_pipe_library, get_pipe_router
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.runtime_hub import get_content_generator
from pipelex.system.job_metadata import JobMetadata


@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLMDateOutputPath:
    async def test_date_output_takes_object_path_with_field_descriptions(
        self,
        job_metadata: JobMetadata,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
    ) -> None:
        """`output = "Date"` calls make_object with DateContent whose schema carries both field descriptions."""
        load_empty_library()
        content_generator = get_content_generator()
        make_object_spy = mocker.spy(content_generator, "make_object")

        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="generic",
            pipe_code="adhoc_date_output_path",
            blueprint=PipeLLMBlueprint(
                description="Extract the scheduled departure from a ticket",
                output=NativeConceptCode.DATE,
                prompt="Extract the scheduled departure from this ticket.",
            ),
        )
        get_pipe_library().add_new_pipe(pipe)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            job_metadata=job_metadata,
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        # Object path: make_object was called (the text path would have called make_llm_text instead).
        make_object_spy.assert_called_once()
        object_class: Any = make_object_spy.call_args.kwargs["object_class"]
        assert object_class is DateContent

        # The schema handed to generation carries both LLM-facing field descriptions (contract, not decoration).
        schema = object_class.model_json_schema()
        assert schema["properties"]["date"]["description"]
        assert schema["properties"]["time"]["description"]

        # And the produced value is a Date, not text.
        assert pipe_output.main_stuff.is_date
