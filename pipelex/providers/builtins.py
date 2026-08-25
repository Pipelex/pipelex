from pipelex.plugins.contract import PipelexPlugin
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.providers.anthropic.anthropic_plugin import AnthropicPlugin
from pipelex.providers.azure_rest.azure_rest_plugin import AzureRestPlugin
from pipelex.providers.bedrock.bedrock_plugin import BedrockPlugin
from pipelex.providers.blackboxai.blackboxai_plugin import BlackboxaiPlugin
from pipelex.providers.docling.docling_plugin import DoclingPlugin
from pipelex.providers.fal.fal_plugin import FalPlugin
from pipelex.providers.gateway.gateway_plugin import GatewayPlugin
from pipelex.providers.google.google_plugin import GooglePlugin
from pipelex.providers.huggingface.huggingface_plugin import HuggingFacePlugin
from pipelex.providers.linkup.linkup_plugin import LinkupPlugin
from pipelex.providers.manifold.manifold_plugin import ManifoldPlugin
from pipelex.providers.mistral.mistral_plugin import MistralPlugin
from pipelex.providers.openai.openai_plugin import OpenAIPlugin
from pipelex.providers.openrouter.openrouter_plugin import OpenRouterPlugin
from pipelex.providers.portkey.portkey_plugin import PortkeyPlugin
from pipelex.providers.pypdfium2.pypdfium2_plugin import Pypdfium2Plugin
from pipelex.providers.secrets.secrets_plugin import SecretsPlugin
from pipelex.providers.storage.storage_plugin import StoragePlugin

# The **kernel-layer** half of the plugins Pipelex ships with: inference backends, extraction and
# search drivers, storage and secrets. Every one of them adapts a kernel-layer port, so this module
# — like the rest of ``pipelex.providers`` — stays importable without loading the method interpreter.
# The interpreter-touching built-ins live in ``pipelex.interpreter_plugins.builtins``, which composes
# both halves into the single ``BUILTIN_PLUGINS`` list the boot entrypoint hands to discovery. See
# ``docs/contribute/hub-layering.md``.
#
# This module is the vendor adapters' aggregate, and it sits with them in ``pipelex.providers`` rather
# than with the plugin mechanism in ``pipelex.plugins``: it names every vendor package, which is
# exactly the dependency direction the two-package split makes visible. The mechanism must not know
# its adapters; the adapters' manifest may.
#
# Each is import-light: importing this module imports no backend SDK (the SDKs load lazily inside the
# make_worker closures).
KERNEL_BUILTIN_PLUGINS: list[PipelexPlugin] = [
    StoragePlugin(),
    SecretsPlugin(),
    OpenAIPlugin(),
    GatewayPlugin(),
    ManifoldPlugin(),
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

# Kernel-layer built-ins that core requires unconditionally — naming one in ``runtime.plugins.disabled`` is a
# configuration error, not a no-op. ``storage`` supplies every built-in storage backend
# (``runtime.storage.method`` must resolve to a registered factory or boot fails loud); ``secrets``
# supplies the built-in ``env`` secrets backend (``runtime.secrets.method`` must likewise resolve or boot
# fails loud); ``openai`` is the always-on default inference driver (no optional SDK to avoid), so
# disabling it would only break the out-of-the-box experience. The interpreter-layer half of this set
# lives beside its plugins, in ``pipelex.interpreter_plugins.builtins``.
KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES: frozenset[str] = frozenset({"storage", "secrets", "openai"})

# The entry-point groups a kernel-only boot reads: its own, and only its own. Sits beside the
# built-in manifest because it answers the same question for the other half of discovery — what an
# installation contributes to *this* layer. The interpreter's composed list lives next to its own
# built-ins, in ``pipelex.interpreter_plugins.builtins``.
KERNEL_ENTRY_POINT_GROUPS: tuple[PluginGroup, ...] = (PluginGroup.KERNEL,)
