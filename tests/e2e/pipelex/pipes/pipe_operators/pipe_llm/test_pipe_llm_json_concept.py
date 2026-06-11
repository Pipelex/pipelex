"""E2E test for PipeLLM whose output concept refines the native JSON concept.

Regression coverage for `NameError: name 'Any' is not defined`: a `PipeLLM` whose
`output` is a concept that `refines = "JSON"` resolves to a structured-output model
carrying an `Any`-typed field (inherited from `JSONContent`). On a LIVE run, that
model is generated as source with `from __future__ import annotations` and rebuilt;
if the rebuild namespace lacks `Any`, the run crashes. DRY runs do not build the
structured-output model, so only the LIVE variant exercises the regression.
"""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexMTHDSProtocol


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestPipeLLMJsonConcept:
    async def test_build_index(self, pipe_run_mode: PipeRunMode) -> None:
        """A PipeLLM outputting a bare `refines = "JSON"` concept must build and
        rebuild its structured-output model without raising.
        """
        pipeline_response = await PipelexMTHDSProtocol(library_dirs=["tests/e2e/pipelex/pipes/pipe_operators"], pipe_run_mode=pipe_run_mode).execute(
            pipe_code="build_index",
            inputs={
                "text": TextContent(
                    text="Vectors, embeddings, and cosine similarity power semantic search and retrieval.",
                ),
            },
        )

        assert pipeline_response.pipe_output is not None
        assert pipeline_response.pipe_output.working_memory is not None
        assert pipeline_response.pipe_output.main_stuff is not None

        json_content = pipeline_response.pipe_output.main_stuff_as(content_type=JSONContent)
        assert isinstance(json_content.json_obj, dict)

        pretty_print(json_content.json_obj, title="Vector index")

        # In live mode, the LLM must have populated the free-form JSON object.
        if pipe_run_mode.is_live:
            assert len(json_content.json_obj) > 0, f"Expected a non-empty JSON index, got {json_content.json_obj}"
