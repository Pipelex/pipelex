from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from portkey_ai import (
    PORTKEY_GATEWAY_URL,
    AsyncPortkey,
)

from pipelex import log
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.img_gen.img_gen_gemini_mapping import ImgGenGeminiMapping
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.providers.gateway.gateway_exceptions import GatewayCredentialsError
from pipelex.providers.gateway.gateway_protocols import GatewayExtractProtocol
from pipelex.providers.gateway.gateway_schemas import GatewayExtractRequestParams
from pipelex.providers.portkey.portkey_constants import PortkeyHeaderKey
from pipelex.runtime_hub import get_telemetry_manager
from pipelex.system.telemetry.otel_constants import OTelConstants

if TYPE_CHECKING:
    from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobParams
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
    def _make_gemini_image_config(cls, inference_model: InferenceModelSpec, *, job_params: ImgGenJobParams) -> dict[str, str]:
        """Build the gemini `image_config` extra-body block, honoring the portable size.

        Any requested size (tier or exact) resolves through the model's taxonomy rules and
        their published grids — same validation as the native Google worker, never a silent
        forward of an unsupported size. An unset size omits `image_size` entirely so the
        provider applies its own default (the 1K class); when the model has no usable taxonomy
        (rules missing, or a remotely-fetched spec carrying a taxonomy string that predates
        this factory), that no-size case abstains like the support checks and keeps the plain
        ratio-only mapping.
        """
        if job_params.size is None:
            taxonomy = ImgGenGeminiMapping.optional_img_gen_taxonomy(inference_model)
            if taxonomy is None:
                return {"aspect_ratio": ImgGenGeminiMapping.aspect_ratio_literal(job_params.aspect_ratio)}
        else:
            taxonomy = ImgGenGeminiMapping.img_gen_taxonomy(inference_model)
        resolved = ImgGenGeminiMapping.resolve_image_config(
            taxonomy,
            aspect_ratio=job_params.aspect_ratio,
            size=job_params.size,
            model_name=inference_model.name,
        )
        image_config: dict[str, str] = {"aspect_ratio": resolved.aspect_ratio}
        if resolved.image_size is not None:
            image_config["image_size"] = resolved.image_size
        return image_config

    @classmethod
    def make_extras(
        cls, inference_model: InferenceModelSpec, *, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        extra_headers: dict[str, str] = {}
        extra_body: dict[str, Any] = {}
        if inference_model.extra_headers:
            # Per-model outbound headers the catalog sets through model_spec_keys'
            # hyphenated-key rule — `anthropic-beta` is the live example. Nothing
            # here is routing: the gateway decides which integration serves a model
            # from the model id in the body, and refuses any client header that
            # tries to say otherwise.
            extra_headers.update(inference_model.extra_headers)

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
                case GatewayExtractProtocol.LINKUP_FETCH:
                    pass  # Fetch params are built directly in GatewayExtractWorker._extract_web_fetch
        elif isinstance(inference_job, LLMJob) and inference_model.model_id.lower().startswith("mistral-") and inference_job.job_params.seed is None:
            # Mistral models really want non-null seed
            extra_body["seed"] = random.randint(0, 1000000)
        elif isinstance(inference_job, ImgGenJob) and inference_model.model_id.startswith("gemini"):
            extra_body["image_config"] = cls._make_gemini_image_config(inference_model, job_params=inference_job.job_params)
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
