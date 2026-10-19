import pytest
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.errors.problem import ProblemView
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.tools.misc.exceptions import RemoteFileFetchError

SCANNED_PDF_URL = "https://example.com/scans/report.pdf"


class _UnreachableFileExtractWorker(ExtractWorkerAbstract):
    """An extract worker whose fetch of the file to extract finds the host unreachable, as the fetch helper reports it."""

    @override
    async def _extract_pages(self, extract_job: ExtractJob) -> ExtractOutput:
        msg = "Could not fetch a remote file: the host could not be reached"
        raise RemoteFileFetchError(msg, host="example.com").with_error_code(CoreCode.INPUT_URL_UNREACHABLE)


def _make_worker() -> _UnreachableFileExtractWorker:
    inference_model = InferenceModelSpec(
        backend_name="test",
        name="test-extractor",
        sdk="test_extract",
        model_type=ModelType.TEXT_EXTRACTOR,
        model_id="test-extractor-1",
        inputs=["pdf"],
        outputs=["text"],
        costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 1.0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return _UnreachableFileExtractWorker(extra_config={}, inference_model=inference_model)


def _make_job(*, input_name: str | None) -> ExtractJob:
    return ExtractJob(
        extract_input=ExtractInput(document_uri=SCANNED_PDF_URL, input_name=input_name),
        job_params=ExtractJobParams.make_default_extract_job_params(),
        job_config=ExtractJobConfig(),
        job_report=ExtractJobReport(),
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="test-user", pipeline_run_id="test-run")
        ),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestExtractFetchFailure:
    @pytest.mark.parametrize(
        ("input_name", "expected_params", "expected_detail"),
        [
            (
                "scans[2]",
                {"input": "scans[2]", "host": "example.com"},
                "The URL of the input 'scans[2]', on 'example.com', did not answer or answered with an error.",
            ),
            (None, {"host": "example.com"}, "An input's URL could not be fetched"),
        ],
        ids=["named_input", "unnamed_input"],
    )
    async def test_the_input_whose_url_could_not_be_fetched_is_named(
        self, input_name: str | None, expected_params: dict[str, str], expected_detail: str
    ) -> None:
        """The fetch knows the URL alone; the worker knows the input it came from, which the code's sentences name."""
        with pytest.raises(RemoteFileFetchError) as exc_info:
            await _make_worker().extract_pages(extract_job=_make_job(input_name=input_name))

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.INPUT_URL_UNREACHABLE
        assert caller.params is not None
        assert caller.params.as_wire() == expected_params
        assert caller.detail == expected_detail
        assert SCANNED_PDF_URL not in str(caller.to_wire())
