from typing import Any

from botocore.exceptions import ClientError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory, LLMCapabilityError, LLMCompletionError, SdkTypeError
from pipelex.cogt.inference.error_classification import (
    is_quota_exhaustion_aws,
)
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.bedrock.bedrock_client_protocol import BedrockClientProtocol
from pipelex.plugins.bedrock.bedrock_factory import BedrockFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from pipelex.urls import URLs


class BedrockWorkerConfigurationError(CogtError):
    pass


class BedrockLLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        LLMWorkerInternalAbstract.__init__(
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

    def _validate_no_reasoning_params(self, job_params: LLMJobParams) -> None:
        """Validate that no reasoning parameters are set for Bedrock native models."""
        if job_params.reasoning_effort is not None or job_params.reasoning_budget is not None:
            msg = (
                f"Model '{self.inference_model.desc}' does not support reasoning parameters; "
                "Bedrock native models do not support reasoning_effort or reasoning_budget"
            )
            raise LLMCapabilityError(msg)

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        job_params = llm_job.applied_job_params or llm_job.job_params
        self._validate_no_reasoning_params(job_params=job_params)
        message = BedrockFactory.make_simple_message(llm_job=llm_job)

        log.verbose(self.inference_model.model_id)

        try:
            bedrock_response_text, nb_tokens_by_category = await self.bedrock_client_for_text.chat(
                messages=message.to_dict_list(),
                system_text=llm_job.llm_prompt.system_text,
                model=self.inference_model.model_id,
                temperature=job_params.temperature,
                max_tokens=job_params.max_tokens or self.default_max_tokens,
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            error_msg = exc.response.get("Error", {}).get("Message", str(exc))

            if error_code == "ServiceQuotaExceededException":
                msg = f"AWS service quota exceeded for model '{self.inference_model.desc}': {error_msg}"
                raise LLMCompletionError(
                    msg,
                    error_category=InferenceErrorCategory.CAPACITY,
                    user_action=f"Your AWS account has exceeded its service quota — check billing at {URLs.aws_billing}",
                ) from exc

            if error_code == "ThrottlingException":
                if is_quota_exhaustion_aws(error_msg):
                    msg = f"AWS quota exhausted for model '{self.inference_model.desc}': {error_msg}"
                    raise LLMCompletionError(
                        msg,
                        error_category=InferenceErrorCategory.CAPACITY,
                        user_action=f"Your AWS account has exceeded its quota — check billing at {URLs.aws_billing}",
                    ) from exc
                msg = f"AWS rate limit exceeded for model '{self.inference_model.desc}': {error_msg}"
                raise LLMCompletionError(
                    msg,
                    error_category=InferenceErrorCategory.TRANSIENT,
                    user_action="Rate limited by AWS — the system will retry automatically",
                ) from exc

            if error_code == "AccessDeniedException":
                msg = f"AWS access denied for model '{self.inference_model.desc}': {error_msg}"
                raise LLMCompletionError(msg, error_category=InferenceErrorCategory.CONFIGURATION) from exc

            if error_code == "ValidationException":
                msg = f"AWS validation error for model '{self.inference_model.desc}': {error_msg}"
                raise LLMCompletionError(msg, error_category=InferenceErrorCategory.CONTENT) from exc

            if error_code in {"ModelNotReadyException", "ServiceUnavailableException"}:
                msg = f"AWS service unavailable for model '{self.inference_model.desc}': {error_msg}"
                raise LLMCompletionError(msg, error_category=InferenceErrorCategory.TRANSIENT) from exc

            # Fallback for unknown AWS errors
            msg = f"AWS error for model '{self.inference_model.desc}' ({error_code}): {error_msg}"
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.TRANSIENT) from exc

        if (llm_tokens_usage := llm_job.job_report.llm_tokens_usage) and nb_tokens_by_category:
            llm_tokens_usage.nb_tokens_by_category = nb_tokens_by_category
        return bedrock_response_text

    @override
    async def _gen_object(
        self,
        llm_job: LLMJob,
        schema: type[BaseModelTypeVar],
    ) -> BaseModelTypeVar:
        # TODO: try with the newest instructor release
        msg = f"It is not possible to generate objects with a {self.__class__.__name__}."
        raise LLMCapabilityError(msg)
