from pipelex.plugins.anthropic.anthropic_plugin import AnthropicPlugin
from pipelex.plugins.azure_rest.azure_rest_plugin import AzureRestPlugin
from pipelex.plugins.bedrock.bedrock_plugin import BedrockPlugin
from pipelex.plugins.blackboxai.blackboxai_plugin import BlackboxaiPlugin
from pipelex.plugins.contract import PipelexPlugin
from pipelex.plugins.direct.direct_plugin import DirectOrchestratorPlugin
from pipelex.plugins.docling.docling_plugin import DoclingPlugin
from pipelex.plugins.fal.fal_plugin import FalPlugin
from pipelex.plugins.gateway.gateway_plugin import GatewayPlugin
from pipelex.plugins.google.google_plugin import GooglePlugin
from pipelex.plugins.huggingface.huggingface_plugin import HuggingFacePlugin
from pipelex.plugins.linkup.linkup_plugin import LinkupPlugin
from pipelex.plugins.mistral.mistral_plugin import MistralPlugin
from pipelex.plugins.openai.openai_plugin import OpenAIPlugin
from pipelex.plugins.openrouter.openrouter_plugin import OpenRouterPlugin
from pipelex.plugins.pipe_func.pipe_func_plugin import PipeFuncPlugin
from pipelex.plugins.portkey.portkey_plugin import PortkeyPlugin
from pipelex.plugins.pypdfium2.pypdfium2_plugin import Pypdfium2Plugin
from pipelex.plugins.secrets.secrets_plugin import SecretsPlugin
from pipelex.plugins.storage.storage_plugin import StoragePlugin

# The plugins Pipelex ships with — discovered at boot ahead of any external
# entry-point plugin. Each is import-light: importing this module imports no
# backend SDK (the SDKs load lazily inside the make_worker closures).
BUILTIN_PLUGINS: list[PipelexPlugin] = [
    DirectOrchestratorPlugin(),
    PipeFuncPlugin(),
    StoragePlugin(),
    SecretsPlugin(),
    OpenAIPlugin(),
    GatewayPlugin(),
    PortkeyPlugin(),
    AnthropicPlugin(),
    MistralPlugin(),
    BedrockPlugin(),
    GooglePlugin(),
    FalPlugin(),
    HuggingFacePlugin(),
    BlackboxaiPlugin(),
    OpenRouterPlugin(),
    AzureRestPlugin(),
    DoclingPlugin(),
    Pypdfium2Plugin(),
    LinkupPlugin(),
]

# Built-in plugins that core requires unconditionally — naming one in
# ``plugins.disabled`` is a configuration error, not a no-op. ``direct`` owns the
# DIRECT orchestrator (you cannot boot without an in-process execution mode);
# ``pipe_func`` owns the built-in PipeFunc execution modes (``pipe_func_config.execution_mode`` must
# resolve to a registered factory or boot fails loud — ``direct`` must always be present);
# ``storage`` supplies every built-in storage backend (``storage_config.method`` must
# resolve to a registered factory or boot fails loud); ``secrets`` supplies the built-in
# ``env`` secrets backend (``secrets_config.method`` must likewise resolve or boot fails loud);
# ``openai`` is the always-on default inference driver (no optional SDK to avoid), so disabling it
# would only break the out-of-the-box experience.
CORE_UNCONDITIONAL_PLUGIN_NAMES: frozenset[str] = frozenset({"direct", "pipe_func", "storage", "secrets", "openai"})
