from pipelex.pipeline.direct_bundle_validator import DirectBundleValidator
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.runtime_bridge.direct_orchestrator import DirectOrchestrator
from pipelex.runtime_bridge.orchestration_mode import DIRECT_ORCHESTRATION_MODE


class DirectOrchestratorPlugin:
    """Core, always-on plugin contributing the in-process ``"direct"`` orchestrator and validator.

    ``"direct"`` is the default orchestration mode and must always be available; this
    plugin is core-unconditional (denylisting it is a startup error). It contributes both
    the in-process pipe orchestrator and the in-process ``/validate`` bundle validator —
    constructing either imports no host-runtime SDK.
    """

    name = "direct"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_orchestrator(mode=DIRECT_ORCHESTRATION_MODE, orchestrator=DirectOrchestrator())
        registrar.add_bundle_validator(mode=DIRECT_ORCHESTRATION_MODE, validator=DirectBundleValidator())
