from __future__ import annotations

from typing import TYPE_CHECKING, Any

from portkey_ai import (
    PORTKEY_GATEWAY_URL,  # type: ignore[reportUnknownVariableType]
)

from pipelex.hub import get_telemetry_manager
from pipelex.plugins.openai.openai_constants import OpenAIBodyKey
from pipelex.plugins.portkey.portkey_constants import PortkeyHeaderKey
from pipelex.plugins.portkey.portkey_exceptions import PortkeyCredentialsError, PortkeyFactoryError

if TYPE_CHECKING:
    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class PortkeyFactory:
    @classmethod
    def is_debug_enabled(cls, backend: InferenceBackend) -> bool:
        is_debug_configured = backend.extra_config.get("debug", False)
        return get_telemetry_manager().is_portkey_logging_enabled(is_debug_configured=is_debug_configured)

    @classmethod
    def get_endpoint(cls, backend: InferenceBackend) -> str:
        return backend.endpoint or PORTKEY_GATEWAY_URL

    @classmethod
    def get_api_key(cls, backend: InferenceBackend) -> str:
        if not backend.api_key:
            msg = "Portkey API key is not set"
            raise PortkeyCredentialsError(msg)
        return backend.api_key

    @classmethod
    def make_extras(cls, inference_model: InferenceModelSpec, llm_job: LLMJob, output_desc: str) -> tuple[dict[str, str], dict[str, Any]]:
        extra_headers: dict[str, str] = {}
        extra_body: dict[str, Any] = {}
        if inference_model.extra_headers:
            extra_headers.update(inference_model.extra_headers)
        if not llm_job.job_params.max_tokens and inference_model.max_tokens:
            extra_body[OpenAIBodyKey.MAX_TOKENS] = inference_model.max_tokens
        if get_telemetry_manager().is_portkey_tracing_enabled():
            if llm_job.job_metadata.pipe_job_ids:
                last_pipe_job_id = llm_job.job_metadata.pipe_job_ids[-1]
            else:
                last_pipe_job_id = "main"
            extra_headers[PortkeyHeaderKey.TRACE_ID] = llm_job.job_metadata.pipeline_run_id
            if not llm_job.job_metadata.unit_job_id:
                msg = f"Unit job id is not set for LLM job: {llm_job}"
                raise PortkeyFactoryError(msg)
            model_kind = llm_job.job_metadata.unit_job_id.model_kind
            span_id = f"{model_kind} -> {output_desc}"
            extra_headers[PortkeyHeaderKey.SPAN_ID] = span_id
            extra_headers[PortkeyHeaderKey.SPAN_NAME] = f"{last_pipe_job_id}: {span_id}"
        return extra_headers, extra_body
