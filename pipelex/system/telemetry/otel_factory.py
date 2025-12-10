"""OpenTelemetry utilities for GenAI-compliant tracing.

This module provides helpers for instrumenting LLM operations with OpenTelemetry.
"""

import base64
import hashlib
from typing import Any

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource as OTelResource
from opentelemetry.sdk.trace import TracerProvider as OTelTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor as OTelBatchSpanProcessor
from opentelemetry.semconv._incubating.attributes import deployment_attributes  # noqa: PLC2701
from opentelemetry.semconv.attributes import service_attributes
from opentelemetry.trace import Tracer as OTelTracer
from posthog import Posthog  # type: ignore[attr-defined]

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.system.environment import EnvVarNotFoundError, get_optional_env, get_required_env
from pipelex.system.runtime import RunEnvironment
from pipelex.system.telemetry.exceptions import LangfuseCredentialsError
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.posthog_span_exporter import PostHogSpanExporter
from pipelex.system.telemetry.telemetry_config import OtlpExporterConfig, TelemetryRedactionConfig
from pipelex.tools.log.log import log
from pipelex.tools.misc.json_utils import JsonContent, pure_json_str
from pipelex.tools.misc.package_utils import get_package_version


class OtelFactory:
    @classmethod
    def make_truncated_content(cls, content: str, max_length: int | None) -> str:
        """Truncate content for telemetry capture if it exceeds max length.

        Args:
            content: The content to potentially truncate.
            max_length: Maximum allowed length, or None for no limit.

        Returns:
            The original content if within limit, or truncated content with suffix.
        """
        if max_length is None or len(content) <= max_length:
            return content
        truncate_at = max(0, max_length - len(OTelConstants.TRUNCATION_SUFFIX))
        return content[:truncate_at] + OTelConstants.TRUNCATION_SUFFIX

    @classmethod
    def stringify_json(cls, json_conent: JsonContent) -> str:
        """Serialize a JSON dictionary to a string.

        Args:
            json_conent: The JSON content to serialize.

        Returns:
            The serialized JSON string.
        """
        # return json.dumps(json_conent, default=str)
        return pure_json_str(data=json_conent)

    @classmethod
    def make_inputs_json(
        cls,
        working_memory: WorkingMemory,
        needed_input_names: set[str],
        max_length: int | None,
    ) -> str:
        """Serialize pipe inputs from working memory to JSON for telemetry.

        Args:
            working_memory: The working memory containing input stuffs.
            needed_input_names: Set of input variable names to capture.
            max_length: Maximum allowed length for the JSON string, or None for no limit.

        Returns:
            JSON string representing the inputs, potentially truncated.
        """
        inputs_dict: dict[str, Any] = {}
        for input_name in needed_input_names:
            stuff = working_memory.get_stuff(name=input_name)
            inputs_dict[input_name] = {
                "concept": stuff.concept.simple_concept_string,
                "content": stuff.content.smart_dump(),
            }

        json_str = cls.stringify_json(json_conent=inputs_dict)
        return cls.make_truncated_content(content=json_str, max_length=max_length)

    @classmethod
    def make_output_json(
        cls,
        pipe_output: PipeOutput,
        max_length: int | None,
    ) -> str:
        """Serialize pipe output to JSON for telemetry.

        Args:
            pipe_output: The pipe output containing the main stuff.
            max_length: Maximum allowed length for the JSON string, or None for no limit.

        Returns:
            JSON string representing the output, potentially truncated.
        """
        main_stuff = pipe_output.working_memory.get_optional_main_stuff()
        if main_stuff is None:
            return "{}"

        output_dict: dict[str, Any] = {
            "concept": main_stuff.concept.simple_concept_string,
            "content": main_stuff.content.smart_dump(),
        }

        json_str = cls.stringify_json(json_conent=output_dict)
        return cls.make_truncated_content(content=json_str, max_length=max_length)

    @classmethod
    def make_trace_id(cls, pipeline_run_id: str) -> int:
        """Convert pipeline_run_id to a 128-bit OTel trace ID (deterministic).

        Uses MD5 hash to generate a consistent trace ID from the pipeline_run_id.
        This ensures all spans within the same pipeline run share the same trace ID.

        Args:
            pipeline_run_id: The pipeline run identifier string.

        Returns:
            A 128-bit integer suitable for use as an OTel trace ID.
        """
        return int(hashlib.md5(pipeline_run_id.encode("utf-8")).hexdigest(), 16)  # noqa: S324

    @classmethod
    def make_trace_names(cls, pipeline_run_id: str, pipe_code: str) -> tuple[str, str]:
        """Create both full and redacted trace names from pipeline run ID and pipe code.

        Args:
            pipeline_run_id: The pipeline run identifier string.
            pipe_code: The pipe code to include in the full trace name.

        Returns:
            A tuple of (trace_name, trace_name_redacted):
            - trace_name: Full version with pipe code (e.g., "my_pipe_abc12345")
            - trace_name_redacted: Just the hash (e.g., "abc12345")
        """
        hashed_id = hashlib.md5(pipeline_run_id.encode("utf-8")).hexdigest()[:8]  # noqa: S324
        trace_name = f"{pipe_code}_{hashed_id}"
        trace_name_redacted = hashed_id
        return trace_name, trace_name_redacted

    @classmethod
    def make_langfuse_exporter(cls, langfuse_base_url: str | None) -> OTLPSpanExporter:
        """Create a Langfuse OTLP exporter using environment credentials.

        Requires LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY environment variables.
        Optionally LANGFUSE_BASE_URL can be set via env var or config.

        Args:
            langfuse_base_url: Optional base URL override from config

        Returns:
            OTLPSpanExporter configured for Langfuse, or None if credentials missing
        """
        try:
            public_key = get_required_env("LANGFUSE_PUBLIC_KEY")
            secret_key = get_required_env("LANGFUSE_SECRET_KEY")
        except EnvVarNotFoundError as exc:
            msg = "Langfuse enabled but credentials not found"
            raise LangfuseCredentialsError(msg) from exc

        # Config takes precedence, then env var, then default
        base_url = langfuse_base_url or get_optional_env("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com"

        # Build Basic auth header
        langfuse_auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()

        return OTLPSpanExporter(
            endpoint=f"{base_url}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {langfuse_auth}"},
        )

    @classmethod
    def make_ai_tracer(
        cls,
        user_id: str | None,
        custom_posthog_client: Posthog | None,
        custom_redaction_config: TelemetryRedactionConfig,
        pipelex_posthog_client: Posthog | None = None,
        pipelex_distinct_id: str | None = None,
        otlp_exporters: list[OtlpExporterConfig] | None = None,
        is_langfuse_enabled: bool = False,
        langfuse_base_url: str | None = None,
    ) -> tuple[OTelTracer, OTelTracerProvider]:
        """Create an isolated OpenTelemetry Tracer for GenAI instrumentation.

        This creates a dedicated TracerProvider that does NOT register itself as the
        global tracer to avoid polluting other traces in the host application.

        It can configure multiple types of exporters:
        1. Custom PostHog Exporter: User's PostHog for their own analytics
        2. Pipelex PostHog Exporter: Pipelex internal telemetry (mandatory for gateway)
        3. OTLP Exporters: Sends standard OTLP traces to collectors (supports multiple)
        4. Langfuse Exporter: Sends OTLP traces to Langfuse for LLM observability

        Args:
            user_id: Optional User ID for event attribution (custom telemetry)
            custom_posthog_client: Optional user's PostHog client for sending events
            custom_redaction_config: Redaction config for custom PostHog exporter
            pipelex_posthog_client: Optional Pipelex internal PostHog client (for gateway)
            pipelex_distinct_id: Distinct ID for Pipelex telemetry
            otlp_exporters: List of OTLP exporter configurations
            is_langfuse_enabled: Whether to enable Langfuse OTLP export
            langfuse_base_url: Optional base URL for self-hosted Langfuse

        Returns:
            A tuple of (Tracer, TracerProvider). The caller should call
            provider.shutdown() during teardown to flush pending spans.
        """
        # Define Resource (Identity)
        resource = OTelResource.create(
            attributes={
                service_attributes.SERVICE_NAME: OTelConstants.SERVICE_NAME,
                service_attributes.SERVICE_VERSION: get_package_version(),
                OTelConstants.SERVICE_NAMESPACE_KEY: OTelConstants.SERVICE_NAMESPACE,
                deployment_attributes.DEPLOYMENT_ENVIRONMENT: RunEnvironment.get_from_env_var().value,
            }
        )

        # Create Provider
        provider = OTelTracerProvider(resource=resource)

        # Add Custom PostHog Exporter if client provided (custom telemetry)
        # Uses user's redaction config (may capture content/pipe codes based on user settings)
        if custom_posthog_client:
            custom_posthog_exporter = PostHogSpanExporter(
                posthog_client=custom_posthog_client,
                distinct_id=user_id,
                redaction_config=custom_redaction_config,
            )
            provider.add_span_processor(OTelBatchSpanProcessor(custom_posthog_exporter))
            log.verbose("Custom PostHog exporter enabled for custom telemetry")

        # Add Pipelex PostHog Exporter if client provided (mandatory for gateway)
        # Always uses full redaction config (never captures sensitive content/pipe codes)
        if pipelex_posthog_client:
            pipelex_redaction_config = TelemetryRedactionConfig.pipelex_config()
            pipelex_posthog_exporter = PostHogSpanExporter(
                posthog_client=pipelex_posthog_client,
                distinct_id=pipelex_distinct_id,
                redaction_config=pipelex_redaction_config,
            )
            provider.add_span_processor(OTelBatchSpanProcessor(pipelex_posthog_exporter))
            log.verbose("Pipelex PostHog exporter enabled for gateway telemetry (with full redaction)")

        # Add OTLP Exporters (supports multiple)
        if otlp_exporters:
            for exporter_config in otlp_exporters:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=exporter_config.endpoint,
                    headers=exporter_config.headers,
                )
                provider.add_span_processor(OTelBatchSpanProcessor(otlp_exporter))
                log.verbose(f"OTLP exporter '{exporter_config.name}' enabled: {exporter_config.endpoint}")

        # Add Langfuse OTLP Exporter if enabled
        if is_langfuse_enabled:
            langfuse_exporter = cls.make_langfuse_exporter(langfuse_base_url)
            provider.add_span_processor(OTelBatchSpanProcessor(langfuse_exporter))
            log.verbose("Langfuse OTLP exporter enabled")

        # Get the Tracer and return both tracer and provider
        tracer = provider.get_tracer(
            instrumenting_module_name=OTelConstants.INSTRUMENTING_MODULE_NAME,
            instrumenting_library_version=get_package_version(),
        )
        return tracer, provider
