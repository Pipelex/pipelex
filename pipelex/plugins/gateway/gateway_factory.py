from __future__ import annotations

from typing import TYPE_CHECKING, Any

from portkey_ai import (
    PORTKEY_GATEWAY_URL,
    AsyncPortkey,  # type: ignore[reportUnknownVariableType]
)

from pipelex import log
from pipelex.hub import get_telemetry_manager
from pipelex.plugins.gateway.gateway_exceptions import GatewayCredentialsError
from pipelex.plugins.portkey.portkey_constants import PortkeyHeaderKey
from pipelex.system.telemetry.otel_constants import REDACTED
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

if TYPE_CHECKING:
    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class GatewayFactory:
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
            raise GatewayCredentialsError(msg)
        return backend.api_key

    @classmethod
    def make_portkey_client(
        cls,
        backend: InferenceBackend,
    ) -> AsyncPortkey:
        is_debug_enabled = cls.is_debug_enabled(backend=backend)
        endpoint = cls.get_endpoint(backend=backend)
        api_key = cls.get_api_key(backend=backend)
        log.verbose(f"Making Portkey client with endpoint: {endpoint}, debug: {is_debug_enabled}")

        return AsyncPortkey(
            base_url=endpoint,
            api_key=api_key,
            debug=is_debug_enabled,
        )

    @classmethod
    def make_extras(cls, inference_model: InferenceModelSpec, llm_job: LLMJob, output_desc: str) -> tuple[dict[str, str], dict[str, Any]]:
        extra_headers: dict[str, str] = {}
        if inference_model.extra_headers:
            extra_headers.update(inference_model.extra_headers)
        if not extra_headers.get(PortkeyHeaderKey.CONFIG) and not extra_headers.get(PortkeyHeaderKey.PROVIDER):
            extra_headers[PortkeyHeaderKey.PROVIDER] = inference_model.backend_name

        # OTel-correlated Portkey tracing (only when enabled and OTel context available)
        if get_telemetry_manager().is_portkey_tracing_enabled() and (otel_context := llm_job.job_metadata.otel_context):
            # Use OTel trace_id and span_id for correlation
            extra_headers[PortkeyHeaderKey.TRACE_ID] = f"{otel_context.trace_id:032x}"
            extra_headers[PortkeyHeaderKey.SPAN_ID] = f"{otel_context.span_id:016x}"

            # Build span name respecting privacy settings
            pipe_code = llm_job.job_metadata.pipe_code or "main"
            if not TelemetryManagerAbstract.is_capture_pipe_codes_enabled():
                pipe_code = REDACTED

            unit_job_id = llm_job.job_metadata.unit_job_id or "unknown"
            extra_headers[PortkeyHeaderKey.SPAN_NAME] = f"{pipe_code}: {unit_job_id} -> {output_desc}"

        return extra_headers, {}
