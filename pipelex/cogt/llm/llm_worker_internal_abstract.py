from opentelemetry.trace import Span
from pydantic import BaseModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_utils import dump_prompt, dump_response_from_text_gen
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.filetype_utils import UNKNOWN_FILE_TYPE


class LLMWorkerInternalAbstract(LLMWorkerAbstract):
    def __init__(
        self,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        """Initialize the LLMWorker.

        Args:
            inference_model (InferenceModelSpec): The inference model to be used by the worker.
            reporting_delegate (ReportingProtocol | None): An optional report delegate for reporting unit jobs.

        """
        LLMWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.inference_model = inference_model

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return self.inference_model.tag

    @property
    @override
    def is_gen_object_supported(self) -> bool:
        return self.inference_model.is_gen_object_supported

    @property
    @override
    def is_vision_supported(self) -> bool:
        return self.inference_model.is_vision_supported

    #########################################################
    # OTel helper method overrides
    #########################################################

    @override
    def _get_provider_name(self) -> str:
        """Get the GenAI provider name from the inference model SDK."""
        return self.inference_model.backend_name

    @override
    def _get_request_model_name(self) -> str:
        """Get the model name from the inference model."""
        return self.inference_model.name

    @override
    def _get_response_model_name(self) -> str:
        """Get the response model name from the inference model."""
        return self.inference_model.model_id

    #########################################################
    # Job lifecycle overrides
    #########################################################

    @override
    async def _before_job(
        self,
        llm_job: LLMJob,
    ):
        log.dev(f"✨ {self.desc} ✨")
        await super()._before_job(llm_job=llm_job)
        llm_job.llm_job_before_start(inference_model=self.inference_model)
        llm_job.applied_job_params = self._apply_constraints(llm_job=llm_job)
        if get_config().cogt.llm_config.is_dump_text_prompts_enabled:
            dump_prompt(llm_prompt=llm_job.llm_prompt)

    def _apply_constraints(self, llm_job: LLMJob) -> LLMJobParams | None:
        """Apply constraints from the inference model to job params.

        Args:
            llm_job: The LLM job containing the original job params

        Returns:
            A copy of job_params with constraints applied, or None if no changes were needed

        """
        original_params = llm_job.job_params
        new_temperature = original_params.temperature
        max_tokens = original_params.max_tokens or self.inference_model.max_tokens
        new_max_tokens = max_tokens
        has_changes = False

        # Temperature constraints
        if ListedConstraint.TEMPERATURE_MUST_BE_MULTIPLIED_BY_2 in self.inference_model.listed_constraints:
            new_temperature *= 2
            has_changes = True
        fixed_temperature = self.inference_model.valued_constraints.get(ValuedConstraint.FIXED_TEMPERATURE)
        if fixed_temperature is not None and new_temperature != fixed_temperature:
            log.warning(
                f"Model {self.inference_model.desc} used with temperature {new_temperature}, "
                f"but it must be {fixed_temperature} for this model so we forced it to {fixed_temperature}"
            )
            new_temperature = fixed_temperature
            has_changes = True

        if not has_changes:
            return None

        return original_params.model_copy(update={"temperature": new_temperature, "max_tokens": new_max_tokens})

    @override
    async def _after_text_job(
        self,
        span: Span | None,
        llm_job: LLMJob,
        result_text: str,
    ):
        if get_config().cogt.llm_config.is_dump_response_text_enabled:
            dump_response_from_text_gen(response=result_text)
        await super()._after_text_job(span=span, llm_job=llm_job, result_text=result_text)

    @override
    async def _after_object_job(
        self,
        span: Span | None,
        llm_job: LLMJob,
        result_object: BaseModel,
    ):
        if get_config().cogt.llm_config.is_dump_response_text_enabled:
            dump_response_from_text_gen(response=result_object)
        await super()._after_object_job(span=span, llm_job=llm_job, result_object=result_object)

    @override
    def _check_can_perform_job(self, llm_job: LLMJob):
        # This can be overridden by subclasses for specific checks
        self._check_vision_support(llm_job=llm_job)
        self._check_document_support(llm_job=llm_job)

    def _check_vision_support(self, llm_job: LLMJob):
        if llm_job.llm_prompt.user_images:
            if not self.inference_model.is_vision_supported:
                msg = f"LLM Engine '{self.inference_model.tag}' does not support vision."
                raise LLMCapabilityError(msg)

            nb_images = len(llm_job.llm_prompt.user_images)
            max_prompt_images = self.inference_model.max_prompt_images or 5000
            if nb_images > max_prompt_images:
                msg = f"LLM Engine '{self.inference_model.tag}' does not accept that many images: {nb_images}."
                raise LLMCapabilityError(msg)

    def _check_document_support(self, llm_job: LLMJob):
        if not llm_job.llm_prompt.user_documents:
            return

        if not self.inference_model.is_document_supported:
            msg = f"LLM Engine '{self.inference_model.tag}' does not support documents."
            raise LLMCapabilityError(msg)

        # Check each document's type is supported
        supported = self.inference_model.supported_document_types
        for doc in llm_job.llm_prompt.user_documents:
            doc_type = doc.get_document_type()
            # Skip validation for unknown types - let the provider handle it
            if doc_type == UNKNOWN_FILE_TYPE:
                continue
            if doc_type not in supported:
                msg = f"LLM Engine '{self.inference_model.tag}' does not support {doc_type} documents."
                raise LLMCapabilityError(msg)
