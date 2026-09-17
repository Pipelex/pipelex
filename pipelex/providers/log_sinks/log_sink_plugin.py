from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.system.runtime import RunEnvironment
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.tools.log.console_log_sink import ConsoleLogSink
from pipelex.tools.log.gcp_log_sink import make_gcp_log_sink
from pipelex.tools.log.json_log_sink import JsonLogSink
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod, stream_for_target
from pipelex.tools.misc.package_utils import get_package_version


def _make_json_log_sink(config: LogConfig) -> LogSink:
    return JsonLogSink(stream=stream_for_target(target=config.console_log_target))


def _make_console_log_sink(config: LogConfig) -> LogSink:
    # Rich is imported when the sink builds its handler, at install, never here.
    return ConsoleLogSink(rich_log_config=config.rich_log, target=config.console_log_target)


def _make_otlp_log_sink(config: LogConfig) -> LogSink:
    # Deferred imports: the OpenTelemetry logs SDK and the exporter load only when this sink is
    # selected, so registering the built-ins stays import-light and a process on another sink never
    # pays for them. The sink module imports the SDK at load, which is why it is imported here too.
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter  # ruff: ignore[import-outside-top-level, import-private-name]
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor  # ruff: ignore[import-outside-top-level, import-private-name]
    from opentelemetry.sdk.resources import Resource as OTelResource  # ruff: ignore[import-outside-top-level]
    from opentelemetry.semconv._incubating.attributes import deployment_attributes  # ruff: ignore[import-outside-top-level, import-private-name]
    from opentelemetry.semconv.attributes import service_attributes  # ruff: ignore[import-outside-top-level]

    from pipelex.tools.log.otlp_log_sink import OtlpLogSink  # ruff: ignore[import-outside-top-level]

    # The same identity the tracer provider declares, so a collector files the logs beside the spans.
    resource = OTelResource.create(
        attributes={
            service_attributes.SERVICE_NAME: OTelConstants.SERVICE_NAME,
            service_attributes.SERVICE_VERSION: get_package_version(),
            OTelConstants.SERVICE_NAMESPACE_KEY: OTelConstants.SERVICE_NAMESPACE,
            deployment_attributes.DEPLOYMENT_ENVIRONMENT: RunEnvironment.get_from_env_var().value,
        }
    )
    # ``None`` for an absent endpoint or empty headers leaves the exporter to the OTEL_EXPORTER_OTLP_*
    # environment conventions, the way a collector-side deployment is configured.
    exporter = OTLPLogExporter(endpoint=config.otlp.endpoint, headers=config.otlp.headers or None)
    return OtlpLogSink(processor=BatchLogRecordProcessor(exporter), resource=resource)


def _make_gcp_log_sink(config: LogConfig) -> LogSink:
    # Deferred import: the Google Cloud Logging client library loads inside ``make_gcp_log_sink``,
    # when this factory runs, so registering the built-ins imports none of it and a process on
    # another sink never pays for it. A missing extra fails there, loud, with the install hint.
    return make_gcp_log_sink(config=config.gcp)


class LogSinkPlugin:
    """Always-on built-in provider of the ``json`` / ``console`` / ``otlp`` / ``gcp`` log sinks.

    Core-unconditional: a process needs somewhere for its records to go, so this plugin cannot be
    disabled into a boot with no sink (see ``KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES``). It registers
    one factory per built-in method; ``runtime.log.sink`` selects which one boot invokes. Importing
    this module is import-light: Rich loads when the console sink builds its handler, the
    OpenTelemetry SDK when the ``otlp`` factory runs, and the Google Cloud Logging client library
    when the ``gcp`` factory runs, never at register.
    """

    name = "log_sinks"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_log_sink(method=LogSinkMethod.JSON, factory=_make_json_log_sink)
        registrar.add_log_sink(method=LogSinkMethod.CONSOLE, factory=_make_console_log_sink)
        registrar.add_log_sink(method=LogSinkMethod.OTLP, factory=_make_otlp_log_sink)
        registrar.add_log_sink(method=LogSinkMethod.GCP, factory=_make_gcp_log_sink)
