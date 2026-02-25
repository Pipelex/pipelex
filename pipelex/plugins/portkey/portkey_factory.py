from __future__ import annotations

from typing import TYPE_CHECKING, Any

from portkey_ai import PORTKEY_GATEWAY_URL

from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.hub import get_telemetry_manager
from pipelex.plugins.openai.openai_constants import OpenAIBodyKey
from pipelex.plugins.portkey.portkey_constants import PortkeyHeaderKey
from pipelex.plugins.portkey.portkey_exceptions import PortkeyCredentialsError
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

if TYPE_CHECKING:
    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class PortkeyFactory:
    @classmethod
    def is_debug_enabled(cls, backend: InferenceBackend) -> bool:
        is_debug_configured = backend.extra_config.get("debug", False)
        return get_telemetry_manager().is_custom_portkey_logging_enabled(is_debug_configured=is_debug_configured)

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
    def make_extras(
        cls, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        extra_headers: dict[str, str] = {}
        extra_body: dict[str, Any] = {}

        # Model-level extras (unchanged)
        if inference_model.extra_headers:
            extra_headers.update(inference_model.extra_headers)
        if isinstance(inference_job, LLMJob) and not inference_job.job_params.max_tokens and inference_model.max_tokens:
            extra_body[OpenAIBodyKey.MAX_TOKENS] = inference_model.max_tokens

        # OTel-correlated Portkey tracing (only when enabled and OTel context available)
        if get_telemetry_manager().is_custom_portkey_tracing_enabled() and (otel_context := inference_job.job_metadata.otel_context):
            # Use OTel trace_id and span_id for correlation
            extra_headers[PortkeyHeaderKey.TRACE_ID] = f"{otel_context.trace_id:032x}"
            extra_headers[PortkeyHeaderKey.SPAN_ID] = f"{otel_context.span_id:016x}"

            # Build span name respecting privacy settings
            pipe_code = inference_job.job_metadata.pipe_code or "main"
            if not TelemetryManagerAbstract.is_capture_pipe_codes_enabled():
                pipe_code = OTelConstants.PIPE_CODE_REDACTED

            # Redact output class name if not "text" and capture is disabled
            if output_desc == InferenceOutputType.TEXT or TelemetryManagerAbstract.is_capture_output_class_name_enabled():
                display_output = output_desc
            else:
                display_output = OTelConstants.OUTPUT_CLASS_REDACTED

            unit_job_id = inference_job.job_metadata.unit_job_id or "unknown"
            extra_headers[PortkeyHeaderKey.SPAN_NAME] = f"{pipe_code}: {unit_job_id} -> {display_output}"

        return extra_headers, extra_body
