from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from portkey_ai import (
    PORTKEY_GATEWAY_URL,
    AsyncPortkey,
)
from portkey_ai.api_resources import exceptions as portkey_exc

from pipelex import log
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.hub import get_telemetry_manager
from pipelex.plugins.gateway.gateway_exceptions import GatewayCredentialsError
from pipelex.plugins.gateway.gateway_protocols import GatewayExtractProtocol
from pipelex.plugins.gateway.gateway_schemas import GatewayExtractRequestParams
from pipelex.plugins.portkey.portkey_constants import PortkeyHeaderKey
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.urls import URLs

if TYPE_CHECKING:
    from portkey_ai.api_resources import exceptions as portkey_exceptions

    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class GatewayFactory:
    @classmethod
    def is_debug_enabled(cls, backend: InferenceBackend) -> bool:
        is_debug_configured = backend.extra_config.get("debug", False)
        return get_telemetry_manager().is_pipelex_gateway_portkey_logging_enabled(is_debug_configured=is_debug_configured)

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
    def make_extras(
        cls, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        extra_headers: dict[str, str] = {}
        extra_body: dict[str, Any] = {}
        if inference_model.extra_headers:
            extra_headers.update(inference_model.extra_headers)
        if not extra_headers.get(PortkeyHeaderKey.CONFIG) and not extra_headers.get(PortkeyHeaderKey.PROVIDER):
            extra_headers[PortkeyHeaderKey.PROVIDER] = inference_model.backend_name

        if isinstance(inference_job, ExtractJob):
            # Derive boolean from max_nb_images: None/positive = True, 0 = False
            max_nb_images = inference_job.job_params.max_nb_images
            should_include_images = max_nb_images is None or max_nb_images > 0
            extract_protocol = GatewayExtractProtocol.make_from_model_handle(model_handle=inference_model.name)
            match extract_protocol:
                case GatewayExtractProtocol.MISTRAL_DOC_AI:
                    extra_body["include_image_base64"] = should_include_images
                case GatewayExtractProtocol.AZURE_DOC_INTEL:
                    request_params = GatewayExtractRequestParams(should_include_images=should_include_images)
                    messages_azure: list[dict[str, str]] = [{"role": "user", "content": request_params.model_dump_json()}]
                    extra_body["messages"] = messages_azure
                case GatewayExtractProtocol.DEEPSEEK_OCR:
                    messages_deepseek: list[dict[str, str]] = [{"role": "user", "content": "Convert the document to markdown."}]
                    extra_body["messages"] = messages_deepseek
        elif isinstance(inference_job, LLMJob) and inference_model.model_id.lower().startswith("mistral-") and inference_job.job_params.seed is None:
            # Mistral models really want non-null seed
            extra_body["seed"] = random.randint(0, 1000000)

        # OTel-correlated Portkey tracing (only when enabled and OTel context available)
        if get_telemetry_manager().is_pipelex_gateway_portkey_tracing_enabled() and (otel_context := inference_job.job_metadata.otel_context):
            # Use OTel trace_id and span_id for correlation
            extra_headers[PortkeyHeaderKey.TRACE_ID] = f"{otel_context.trace_id:032x}"
            extra_headers[PortkeyHeaderKey.SPAN_ID] = f"{otel_context.span_id:016x}"

            # Build span name with redacted output class name (consistent with Pipelex telemetry policy)
            # Pipelex services always redact sensitive data to protect user privacy
            unit_job_id = inference_job.job_metadata.unit_job_id or "unknown"
            display_output = output_desc if output_desc == InferenceOutputType.TEXT else OTelConstants.OUTPUT_CLASS_REDACTED
            extra_headers[PortkeyHeaderKey.SPAN_NAME] = f"{unit_job_id} -> {display_output}"

        return extra_headers, extra_body

    @classmethod
    def make_error_summary_from_portkey_error(cls, exc: portkey_exceptions.APIError) -> str:
        """Extract a clean, human-readable error summary from a Portkey API error.

        Args:
            exc: The Portkey API error

        Returns:
            A concise error message suitable for logging and user display
        """
        error_type = type(exc).__name__
        support_hint = f"If the problem persists, get support on Discord: {URLs.discord}"

        # Connection errors (no HTTP response received)
        if isinstance(exc, portkey_exc.APITimeoutError):
            return f"{error_type}: Request timed out - service may be overloaded. {support_hint}"
        if isinstance(exc, portkey_exc.APIConnectionError):
            return f"{error_type}: Cannot connect to Pipelex Gateway - check network or service availability. {support_hint}"

        # HTTP status errors (4xx/5xx)
        if isinstance(exc, portkey_exc.APIStatusError):
            status_code = exc.status_code
            error_body = str(exc)

            # For HTML responses, provide a generic message (gateway/proxy error pages)
            if error_body.strip().startswith("<!DOCTYPE") or "<html" in error_body.lower():
                return f"{error_type} (HTTP {status_code}): Pipelex Gateway unavailable. {support_hint}"

            # For other errors, truncate if too long
            max_length = 200
            if len(error_body) > max_length:
                error_body = error_body[:max_length] + "..."

            return f"{error_type} (HTTP {status_code}): {error_body}"

        # Response validation errors
        if isinstance(exc, portkey_exc.APIResponseValidationError):
            return f"{error_type}: Invalid response from Pipelex Gateway. {support_hint}"

        # Fallback for any other APIError
        return f"{error_type}: {exc.message}. {support_hint}"
