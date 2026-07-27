from pipelex.plugins.anthropic.anthropic_plugin import AnthropicPlugin
from pipelex.plugins.azure_rest.azure_rest_plugin import AzureRestPlugin
from pipelex.plugins.bedrock.bedrock_plugin import BedrockPlugin
from pipelex.plugins.blackboxai.blackboxai_plugin import BlackboxaiPlugin
from pipelex.plugins.contract import PipelexPlugin
from pipelex.plugins.docling.docling_plugin import DoclingPlugin
from pipelex.plugins.fal.fal_plugin import FalPlugin
from pipelex.plugins.gateway.gateway_plugin import GatewayPlugin
from pipelex.plugins.google.google_plugin import GooglePlugin
from pipelex.plugins.huggingface.huggingface_plugin import HuggingFacePlugin
from pipelex.plugins.linkup.linkup_plugin import LinkupPlugin
from pipelex.plugins.mistral.mistral_plugin import MistralPlugin
from pipelex.plugins.openai.openai_plugin import OpenAIPlugin
from pipelex.plugins.openrouter.openrouter_plugin import OpenRouterPlugin
from pipelex.plugins.portkey.portkey_plugin import PortkeyPlugin
from pipelex.plugins.pypdfium2.pypdfium2_plugin import Pypdfium2Plugin
from pipelex.plugins.secrets.secrets_plugin import SecretsPlugin
from pipelex.plugins.storage.storage_plugin import StoragePlugin

# The **runtime-layer** half of the plugins Pipelex ships with: inference backends, extraction and
# search drivers, storage and secrets. Every one of them adapts a runtime-layer port, so this module
# — like the rest of ``pipelex.plugins`` — stays importable without loading the method interpreter.
# The interpreter-touching built-ins live in ``pipelex.interpreter_plugins.builtins``, which composes
# both halves into the single ``BUILTIN_PLUGINS`` list the boot entrypoint hands to discovery. See
# ``docs/contribute/hub-layering.md``.
#
# Each is import-light: importing this module imports no backend SDK (the SDKs load lazily inside the
# make_worker closures).
RUNTIME_BUILTIN_PLUGINS: list[PipelexPlugin] = [
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

# Runtime-layer built-ins that core requires unconditionally — naming one in ``plugins.disabled`` is a
# configuration error, not a no-op. ``storage`` supplies every built-in storage backend
# (``storage_config.method`` must resolve to a registered factory or boot fails loud); ``secrets``
# supplies the built-in ``env`` secrets backend (``secrets_config.method`` must likewise resolve or boot
# fails loud); ``openai`` is the always-on default inference driver (no optional SDK to avoid), so
# disabling it would only break the out-of-the-box experience. The interpreter-layer half of this set
# lives beside its plugins, in ``pipelex.interpreter_plugins.builtins``.
RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES: frozenset[str] = frozenset({"storage", "secrets", "openai"})
