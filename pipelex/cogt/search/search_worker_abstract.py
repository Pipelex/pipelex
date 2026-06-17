from abc import abstractmethod
from typing import Any

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.search_job import SearchJob
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.pipeline.job_metadata import UnitJobId
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class SearchWorkerAbstract(InferenceWorkerAbstract):
    def __init__(
        self,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        InferenceWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.inference_model = inference_model

    @property
    @override
    def desc(self) -> str:
        return f"Search using {self.inference_model.desc}"

    async def search_sourced_answer(
        self,
        search_job: SearchJob,
    ) -> SearchResultContent:
        """Execute a search query and return a sourced answer with sources."""
        log.dev(f"✨ {self.desc} ✨")
        search_job.validate_before_execution()
        search_job.job_metadata.unit_job_id = UnitJobId.SEARCH_SOURCED_ANSWER
        search_job.search_job_before_start(inference_model=self.inference_model)

        try:
            result = await self._search_sourced_answer(search_job=search_job)
        except CogtError as exc:
            exc.fill_model_and_provider(model_handle=self.inference_model.name, backend_name=self.inference_model.backend_name)
            raise

        search_job.search_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=search_job)

        return result

    async def search_structured(
        self,
        search_job: SearchJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> dict[str, Any]:
        """Execute a search query and return structured data matching the schema."""
        log.dev(f"✨ {self.desc} ✨")
        search_job.validate_before_execution()
        search_job.job_metadata.unit_job_id = UnitJobId.SEARCH_STRUCTURED
        search_job.search_job_before_start(inference_model=self.inference_model)

        try:
            result = await self._search_structured(search_job=search_job, schema=schema)
        except CogtError as exc:
            exc.fill_model_and_provider(model_handle=self.inference_model.name, backend_name=self.inference_model.backend_name)
            raise

        search_job.search_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=search_job)

        return result

    @abstractmethod
    async def _search_sourced_answer(
        self,
        search_job: SearchJob,
    ) -> SearchResultContent:
        pass

    @abstractmethod
    async def _search_structured(
        self,
        search_job: SearchJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> dict[str, Any]:
        pass
