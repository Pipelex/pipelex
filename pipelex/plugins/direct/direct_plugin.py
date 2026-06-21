from pipelex.pipeline.direct_bundle_validator import DirectBundleValidator
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.runtime_bridge.direct_orchestrator import DirectOrchestrator
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode


class DirectOrchestratorPlugin:
    """Core, always-on plugin contributing the in-process DIRECT orchestrator and validator.

    DIRECT is the default execution mode and must always be available; this plugin
    is core-unconditional (denylisting it is a startup error). It contributes both the
    DIRECT pipe orchestrator and the DIRECT (in-process) ``/validate`` bundle validator —
    constructing either imports no host-runtime SDK.
    """

    name = "direct"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_orchestrator(mode=PipelexExecutionMode.DIRECT, orchestrator=DirectOrchestrator())
        registrar.add_bundle_validator(mode=PipelexExecutionMode.DIRECT, validator=DirectBundleValidator())
