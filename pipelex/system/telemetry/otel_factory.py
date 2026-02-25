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
from pipelex.system.environment import get_optional_env
from pipelex.system.runtime import RunEnvironment
from pipelex.system.telemetry.exceptions import LangfuseCredentialsError
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.posthog_span_exporter import PostHogSpanExporter
from pipelex.system.telemetry.telemetry_config import LangfuseConfig, OtlpExporterConfig, TelemetryRedactionConfig
from pipelex.tools.log.log import log
from pipelex.tools.misc.hash_utils import hash_md5_to_int
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
                "concept": stuff.concept.simple_concept_ref,
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
            "concept": main_stuff.concept.simple_concept_ref,
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
        return hash_md5_to_int(pipeline_run_id)

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
    def _is_unresolved_placeholder(cls, value: str | None) -> bool:
        """Check if a value is an unresolved env var placeholder."""
        return value is not None and value.startswith("${")

    @classmethod
    def make_langfuse_exporter(cls, langfuse_config: LangfuseConfig) -> OTLPSpanExporter:
        """Create a Langfuse OTLP exporter using config credentials.

        Credentials can be provided via config (with env var substitution) or
        fall back to LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY environment variables.

        Args:
            langfuse_config: Langfuse configuration with credentials

        Returns:
            OTLPSpanExporter configured for Langfuse

        Raises:
            LangfuseCredentialsError: If credentials are missing or unresolved
        """
        # Get credentials from config, falling back to env vars
        public_key = langfuse_config.public_key or get_optional_env("LANGFUSE_PUBLIC_KEY")
        secret_key = langfuse_config.secret_key or get_optional_env("LANGFUSE_SECRET_KEY")

        # Check for missing or unresolved credentials
        if not public_key or cls._is_unresolved_placeholder(public_key):
            msg = "Langfuse enabled but public_key not found (set LANGFUSE_PUBLIC_KEY or configure in telemetry.toml)"
            raise LangfuseCredentialsError(msg)
        if not secret_key or cls._is_unresolved_placeholder(secret_key):
            msg = "Langfuse enabled but secret_key not found (set LANGFUSE_SECRET_KEY or configure in telemetry.toml)"
            raise LangfuseCredentialsError(msg)

        # Config takes precedence, then env var, then default
        endpoint = langfuse_config.endpoint or get_optional_env("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com"

        # Build Basic auth header
        langfuse_auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()

        return OTLPSpanExporter(
            endpoint=f"{endpoint}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {langfuse_auth}"},
        )

    @classmethod
    def make_ai_tracer(
        cls,
        user_id: str | None,
        custom_posthog_client: Posthog | None,
        custom_redaction_config: TelemetryRedactionConfig,
        pipelex_posthog_client: Posthog | None,
        pipelex_gateway_redaction_config: TelemetryRedactionConfig,
        pipelex_distinct_id: str | None,
        otlp_exporters: list[OtlpExporterConfig] | None,
        langfuse_config: LangfuseConfig | None,
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
            pipelex_gateway_redaction_config: Redaction config for Pipelex Gateway PostHog exporter
            pipelex_distinct_id: Distinct ID for Pipelex telemetry
            otlp_exporters: List of OTLP exporter configurations
            langfuse_config: Optional Langfuse configuration (enables Langfuse if provided and enabled)

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

        # Add Custom PostHog Exporter if client is provided (custom telemetry)
        # Uses user's redaction config (may capture content/pipe codes based on user settings)
        if custom_posthog_client:
            custom_posthog_exporter = PostHogSpanExporter(
                posthog_client=custom_posthog_client,
                distinct_id=user_id,
                redaction_config=custom_redaction_config,
            )
            provider.add_span_processor(OTelBatchSpanProcessor(custom_posthog_exporter))
            log.verbose("Custom PostHog exporter enabled for custom telemetry")

        # Add Pipelex PostHog Exporter if client is provided (mandatory for gateway)
        if pipelex_posthog_client:
            pipelex_posthog_exporter = PostHogSpanExporter(
                posthog_client=pipelex_posthog_client,
                distinct_id=pipelex_distinct_id,
                redaction_config=pipelex_gateway_redaction_config,
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
        if langfuse_config and langfuse_config.enabled:
            langfuse_exporter = cls.make_langfuse_exporter(langfuse_config)
            provider.add_span_processor(OTelBatchSpanProcessor(langfuse_exporter))
            log.verbose("Langfuse OTLP exporter enabled")

        # Get the Tracer and return both tracer and provider
        tracer = provider.get_tracer(
            instrumenting_module_name=OTelConstants.INSTRUMENTING_MODULE_NAME,
            instrumenting_library_version=get_package_version(),
        )
        return tracer, provider
