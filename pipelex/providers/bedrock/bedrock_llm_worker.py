from typing import Any

from botocore.exceptions import ClientError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCapabilityError, SdkTypeError
from pipelex.cogt.inference.error_classification import extract_bedrock_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.providers.bedrock.bedrock_client_protocol import BedrockClientProtocol
from pipelex.providers.bedrock.bedrock_exceptions import BedrockWorkerConfigurationError
from pipelex.providers.bedrock.bedrock_factory import BedrockFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class BedrockLLMWorker(LLMWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        LLMWorkerAbstract.__init__(
            self,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )

        if not isinstance(sdk_instance, BedrockClientProtocol):
            msg = f"Provided sdk_instance for {self.__class__.__name__} is not of type BedrockClientProtocol: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        if default_max_tokens := inference_model.max_tokens:
            self.default_max_tokens = default_max_tokens
        else:
            msg = f"No max_tokens provided for llm model '{self.inference_model.desc}', but it is required for Bedrock"
            raise BedrockWorkerConfigurationError(msg)
        self.bedrock_client_for_text = sdk_instance

    @classmethod
    @override
    def check_request(cls, *, inference_model: InferenceModelSpec, job_params: LLMJobParams, is_structured: bool) -> None:
        """Refuse every reasoning setting, and every structured output: Bedrock native models take neither."""
        if job_params.reasoning_effort is not None or job_params.reasoning_budget is not None:
            msg = (
                f"Model '{inference_model.desc}' does not support reasoning parameters; "
                "Bedrock native models do not support reasoning_effort or reasoning_budget"
            )
            raise LLMCapabilityError(msg)
        if is_structured:
            raise LLMCapabilityError(cls._structured_output_refusal(inference_model=inference_model))

    @classmethod
    def _structured_output_refusal(cls, *, inference_model: InferenceModelSpec) -> str:
        return f"Model '{inference_model.desc}' does not support structured outputs; Bedrock native models generate text only"

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        job_params = llm_job.applied_job_params or llm_job.job_params
        message = BedrockFactory.make_simple_message(llm_job=llm_job)

        log.verbose(self.inference_model.model_id)

        try:
            bedrock_response_text, nb_tokens_by_category = await self.bedrock_client_for_text.chat(
                messages=message.to_dict_list(),
                system_text=llm_job.llm_prompt.system_text,
                model=self.inference_model.model_id,
                temperature=job_params.temperature if self.inference_model.accepts_temperature else None,
                max_tokens=job_params.max_tokens or self.default_max_tokens,
            )
        except ClientError as exc:
            metadata = extract_bedrock_metadata(exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.LLM,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from exc

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and nb_tokens_by_category:
            llm_tokens_usage.nb_tokens_by_category = nb_tokens_by_category
        return bedrock_response_text

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        *,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        # Refused by check_request before this is reached. TODO: try with the newest instructor release
        raise LLMCapabilityError(self._structured_output_refusal(inference_model=self.inference_model))
