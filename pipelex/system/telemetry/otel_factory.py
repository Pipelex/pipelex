"""OpenTelemetry utilities for GenAI-compliant tracing.

This module provides helpers for instrumenting LLM operations with OpenTelemetry.
"""

import base64
import hashlib

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource as OTelResource
from opentelemetry.sdk.trace import TracerProvider as OTelTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor as OTelBatchSpanProcessor
from opentelemetry.semconv._incubating.attributes import deployment_attributes  # noqa: PLC2701
from opentelemetry.semconv.attributes import service_attributes
from opentelemetry.trace import Tracer as OTelTracer
from posthog import Posthog  # type: ignore[attr-defined]

from pipelex.system.environment import EnvVarNotFoundError, get_optional_env, get_required_env
from pipelex.system.runtime import RunEnvironment
from pipelex.system.telemetry.exceptions import LangfuseCredentialsError
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.posthog_span_exporter import PostHogSpanExporter
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.log.log import log
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
    def make_trace_name(cls, pipeline_run_id: str, pipe_code: str) -> str:
        """Create a trace name from pipeline run ID and optional pipe code.

        Args:
            pipeline_run_id: The pipeline run identifier string.
            pipe_code: pipe code to include in the trace name or not.

        Returns:
            A trace name combining the pipe code (if enabled) with a short deterministic
            hash of the pipeline run ID.
        """
        hashed_id = hashlib.md5(pipeline_run_id.encode("utf-8")).hexdigest()[:8]  # noqa: S324
        if TelemetryManagerAbstract.is_capture_pipe_codes_enabled():
            return f"{pipe_code}_{hashed_id}"
        else:
            return hashed_id

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
        posthog_client: Posthog | None,
        otlp_endpoint: str | None = None,
        otlp_headers: dict[str, str] | None = None,
        langfuse_enabled: bool = False,
        langfuse_base_url: str | None = None,
    ) -> tuple[OTelTracer, OTelTracerProvider]:
        """Create an isolated OpenTelemetry Tracer for GenAI instrumentation.

        This creates a dedicated TracerProvider that does NOT register itself as the
        global tracer to avoid polluting other traces in the host application.

        It can configure multiple types of exporters:
        1. PostHog Exporter: Converts spans to PostHog $ai_generation events
        2. OTLP Exporter: Sends standard OTLP traces to a collector
        3. Langfuse Exporter: Sends OTLP traces to Langfuse for LLM observability

        Args:
            user_id: Optional User ID for event attribution
            posthog_client: Optional PostHog client for sending events
            otlp_endpoint: Optional OTLP endpoint URL
            otlp_headers: Optional headers for OTLP export
            langfuse_enabled: Whether to enable Langfuse OTLP export
            langfuse_base_url: Optional base URL for self-hosted Langfuse

        Returns:
            A tuple of (Tracer, TracerProvider). The caller should call
            provider.shutdown() during teardown to flush pending spans.
        """
        # 1. Define Resource (Identity)
        resource = OTelResource.create(
            attributes={
                service_attributes.SERVICE_NAME: OTelConstants.SERVICE_NAME,
                service_attributes.SERVICE_VERSION: get_package_version(),
                OTelConstants.SERVICE_NAMESPACE_KEY: OTelConstants.SERVICE_NAMESPACE,
                deployment_attributes.DEPLOYMENT_ENVIRONMENT: RunEnvironment.get_from_env_var().value,
            }
        )

        # 2. Create Provider
        provider = OTelTracerProvider(resource=resource)

        # 3. Add PostHog Exporter if client provided
        if posthog_client:
            posthog_exporter = PostHogSpanExporter(posthog_client, distinct_id=user_id)
            provider.add_span_processor(OTelBatchSpanProcessor(posthog_exporter))

        # 4. Add Generic OTLP Exporter if endpoint provided
        if otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                headers=otlp_headers or {},
            )
            provider.add_span_processor(OTelBatchSpanProcessor(otlp_exporter))

        # 5. Add Langfuse OTLP Exporter if enabled
        if langfuse_enabled:
            langfuse_exporter = cls.make_langfuse_exporter(langfuse_base_url)
            if langfuse_exporter:
                provider.add_span_processor(OTelBatchSpanProcessor(langfuse_exporter))
                log.verbose("Langfuse OTLP exporter enabled")

        # 6. Get the Tracer and return both tracer and provider
        tracer = provider.get_tracer(
            instrumenting_module_name=OTelConstants.INSTRUMENTING_MODULE_NAME,
            instrumenting_library_version=get_package_version(),
        )
        return tracer, provider
