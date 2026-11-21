from abc import abstractmethod
from typing import Any

from typing_extensions import override

from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.inference.inference_call_summary import InferenceCallSummary, InferenceOperation
from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.inference.inference_span import InferenceSpanScope, start_inference_span
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.search_job import SearchJob
from pipelex.cogt.search.search_sources import deduplicate_search_sources
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.job_metadata import UnitJobId
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

    def _call_summary(self, *, search_job: SearchJob) -> InferenceCallSummary:
        """The event the call ends with, its model and its usage read off the worker and the job it reports when it ends."""
        return InferenceCallSummary(
            operation=InferenceOperation.SEARCH,
            model_handle=self.inference_model.name,
            read_inference_model=lambda: self.inference_model,
            read_tokens_usage=lambda: search_job.job_report.search_tokens_usage,
        )

    def _inference_span_scope(
        self,
        *,
        search_job: SearchJob,
        call_summary: InferenceCallSummary,
        output_type: InferenceOutputType,
        output_class_name: str | None = None,
    ) -> InferenceSpanScope:
        """The block the call runs in under its generation span, which ends the span with the call's usage and outcome."""
        return InferenceSpanScope(
            span=start_inference_span(
                job_metadata=search_job.job_metadata,
                operation=InferenceOperation.SEARCH,
                inference_model=self.inference_model,
                request_model=self.inference_model.model_id,
                output_type=output_type,
                output_class_name=output_class_name,
            ),
            call_summary=call_summary.ends_here(),
            read_tokens_usage=lambda: search_job.job_report.search_tokens_usage,
            read_response_model=lambda: self.inference_model.model_id,
        )

    async def search_sourced_answer(
        self,
        search_job: SearchJob,
    ) -> SearchResultContent:
        """Execute a search query and return a sourced answer with sources."""
        # The call ends with its summary event whichever way it ends, a refusal by the job's validation included
        with self._call_summary(search_job=search_job) as call_summary:
            search_job.validate_before_execution()
            search_job.job_metadata.unit_job_id = UnitJobId.SEARCH_SOURCED_ANSWER
            search_job.search_job_before_start(inference_model=self.inference_model)

            # Under the call's generation span, which the summary event names as it ends
            with self._inference_span_scope(search_job=search_job, call_summary=call_summary, output_type=InferenceOutputType.TEXT):
                try:
                    result = await self._search_sourced_answer(search_job=search_job)
                except CogtError as exc:
                    exc.fill_model_and_provider(model_handle=self.inference_model.name, backend_name=self.inference_model.backend_name)
                    raise
                finally:
                    # Completion and reporting belong on *every* way out, not just the happy one. A backend's
                    # response-shape guard raises after the provider already answered and after usage was
                    # recorded, so that call is billed — reporting only on success would make the spend vanish
                    # from the run's cost report. A failure that never reached the provider recorded no tokens
                    # (`search_job_before_start` initialises `nb_tokens_by_category` empty), so it reports as the
                    # zero-cost attempt it was rather than inventing a charge. The summary event the call ends
                    # with reads the same usage, so a billed failure carries its tokens and cost there too.
                    search_job.search_job_after_complete()
                    if self.reporting_delegate:
                        self.reporting_delegate.report_inference_job(inference_job=search_job)

        # Every provider's answer passes here, so each lists its sources once whichever provider listed one twice
        return deduplicate_search_sources(
            search_result=result,
            renumber_citations=search_job.job_params.search_setting.include_inline_citations,
        )

    async def search_structured(
        self,
        search_job: SearchJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> dict[str, Any]:
        """Execute a search query and return structured data matching the schema."""
        # The call ends with its summary event whichever way it ends, a refusal by the job's validation included
        with self._call_summary(search_job=search_job) as call_summary:
            search_job.validate_before_execution()
            search_job.job_metadata.unit_job_id = UnitJobId.SEARCH_STRUCTURED
            search_job.search_job_before_start(inference_model=self.inference_model)

            # Under the call's generation span, which the summary event names as it ends
            with self._inference_span_scope(
                search_job=search_job, call_summary=call_summary, output_type=InferenceOutputType.OBJECT, output_class_name=schema.__name__
            ):
                try:
                    result = await self._search_structured(search_job=search_job, schema=schema)
                except CogtError as exc:
                    exc.fill_model_and_provider(model_handle=self.inference_model.name, backend_name=self.inference_model.backend_name)
                    raise
                finally:
                    # Reported on every way out, for the reason spelled out in `search_sourced_answer` — and it
                    # bites hardest here, because this arm is the one whose response-shape guards reject a
                    # payload the provider already charged for.
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
