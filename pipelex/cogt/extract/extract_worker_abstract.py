from abc import abstractmethod
from typing import Any

from typing_extensions import override

from pipelex.cogt.exceptions import CogtError, ExtractCapabilityError, ExtractInputFormatError
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.inference.inference_call_summary import InferenceCallSummary, InferenceOperation
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.pricing_unit import PricingUnit
from pipelex.cogt.usage.usage_cost import record_unit_priced_usage
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.job_metadata import UnitJobId
from pipelex.tools.misc.filetype_utils import IMAGE_FORMAT_KEY, describe_file_format, describe_format_keys, format_key_from_mime_type
from pipelex.tools.uri.resolved_uri import ResolvedHttpUrl
from pipelex.tools.uri.uri_resolver import resolve_uri

# How a web-page model's declaration is named among the formats it reads, in a refusal.
_WEB_PAGE_INPUT: str = "web_page"


class ExtractWorkerAbstract(InferenceWorkerAbstract):
    def __init__(
        self,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        InferenceWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.extra_config = extra_config
        self.inference_model = inference_model

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"Extraction using {self.inference_model.desc}"

    @property
    def is_pdf_supported(self) -> bool:
        return self.inference_model.is_pdf_supported_for_extract

    @property
    def is_web_page_supported(self) -> bool:
        return self.inference_model.is_web_page_supported_for_extract

    @property
    def is_image_supported(self) -> bool:
        return self.inference_model.is_image_supported_for_extract

    @property
    def is_caption_supported(self) -> bool:
        return self.inference_model.is_caption_supported_for_extract

    def _check_can_perform_job(self, extract_job: ExtractJob):
        # This can be overridden by subclasses for specific checks
        extract_input = extract_job.extract_input
        if extract_input.image_uri:
            if not self.inference_model.is_image_supported_for_extract:
                msg = f"Extract engine '{self.inference_model.tag}' does not support image extraction."
                raise ExtractCapabilityError(msg)
        elif extract_input.document_uri:
            if not (self.inference_model.is_pdf_supported_for_extract or self.inference_model.is_web_page_supported_for_extract):
                msg = f"Extract engine '{self.inference_model.tag}' does not support document extraction."
                raise ExtractCapabilityError(msg)
        if extract_job.job_params.should_caption_images:
            if not self.inference_model.is_caption_supported_for_extract:
                msg = f"Extract engine '{self.inference_model.tag}' does not support image captioning."
                raise ExtractCapabilityError(msg)
        self._check_input_format(extract_input=extract_input)

    def _check_input_format(self, *, extract_input: ExtractInput) -> None:
        """Refuse a file whose known format the model does not read, naming the input and what the model reads.

        An unknown format is left to the provider. A web-page model given an http(s) URL fetches the
        page itself, so its format is not checked. A file given as an image must be an image,
        whatever else the model reads.

        Raises:
            ExtractInputFormatError: If the file's format is known and the model does not read it.
        """
        format_key = format_key_from_mime_type(mime_type=extract_input.mime_type)
        if format_key is None:
            return
        if (
            extract_input.document_uri is not None
            and self.inference_model.is_web_page_supported_for_extract
            and isinstance(resolve_uri(extract_input.document_uri), ResolvedHttpUrl)
        ):
            return
        readable_formats = self.inference_model.readable_formats_for_extract
        if extract_input.image_uri is not None:
            readable_formats &= {IMAGE_FORMAT_KEY}
        if format_key in readable_formats:
            return
        listed_formats = set(readable_formats)
        if extract_input.document_uri is not None and self.inference_model.is_web_page_supported_for_extract:
            listed_formats.add(_WEB_PAGE_INPUT)
        subject = f"Input '{extract_input.input_name}' is" if extract_input.input_name else "The file to extract is"
        msg = (
            f"{subject} {describe_file_format(format_key=format_key, mime_type=extract_input.mime_type)}, "
            f"which model '{self.inference_model.name}' cannot extract: it reads {describe_format_keys(format_keys=listed_formats)}. "
            "Give a file in one of those formats, or use an extract model that reads this one."
        )
        raise ExtractInputFormatError(msg)

    def _call_summary(self, *, extract_job: ExtractJob) -> InferenceCallSummary:
        """The event the call ends with, its usage read off the job it reports."""
        return InferenceCallSummary(
            operation=InferenceOperation.EXTRACT,
            inference_model=self.inference_model,
            read_tokens_usage=lambda: extract_job.job_report.extract_tokens_usage,
        )

    async def extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        # The call ends with its summary event whichever way it ends, a refusal by the checks below included
        with self._call_summary(extract_job=extract_job):
            # Verify that the job is valid
            extract_job.validate_before_execution()

            # Verify feasibility
            self._check_can_perform_job(extract_job=extract_job)
            # TODO: check can generate object (where it will be appropriate)

            # metadata
            extract_job.job_metadata.unit_job_id = UnitJobId.EXTRACT_PAGES

            # Prepare job
            extract_job.extract_job_before_start(inference_model=self.inference_model)

            # Execute job
            try:
                result = await self._extract_pages(extract_job=extract_job)
            except CogtError as exc:
                exc.fill_model_and_provider(model_handle=self.inference_model.name, backend_name=self.inference_model.backend_name)
                raise

            # Price the call by its pages when the provider reported no usage
            if (extract_tokens_usage := extract_job.job_report.extract_tokens_usage) and not extract_tokens_usage.nb_tokens_by_category:
                record_unit_priced_usage(tokens_usage=extract_tokens_usage, pricing_unit=PricingUnit.PAGE, nb_units=len(result.pages))

            # Report job
            extract_job.extract_job_after_complete()
            if self.reporting_delegate:
                self.reporting_delegate.report_inference_job(inference_job=extract_job)

        return result

    @abstractmethod
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        pass
