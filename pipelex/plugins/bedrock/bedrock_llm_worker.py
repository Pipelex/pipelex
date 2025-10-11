from typing import Any

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import CogtError, LLMCapabilityError, SdkTypeError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.bedrock.bedrock_client_protocol import BedrockClientProtocol
from pipelex.plugins.bedrock.bedrock_factory import BedrockFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class BedrockWorkerConfigurationError(CogtError):
    pass


class BedrockLLMWorker(LLMWorkerInternalAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        structure_method: StructureMethod | None = None,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        LLMWorkerInternalAbstract.__init__(
            self,
            inference_model=inference_model,
            structure_method=structure_method,
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

    @override
    async def _gen_text(
        self,
        llm_job: LLMJob,
    ) -> str:
        message = BedrockFactory.make_simple_message(llm_job=llm_job)

        log.debug(self.inference_model.model_id)

        bedrock_response_text, nb_tokens_by_category = await self.bedrock_client_for_text.chat(
            messages=message.to_dict_list(),
            system_text=llm_job.llm_prompt.system_text,
            model=self.inference_model.model_id,
            temperature=llm_job.job_params.temperature,
            max_tokens=llm_job.job_params.max_tokens or self.default_max_tokens,
        )
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
