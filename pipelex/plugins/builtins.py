from pipelex.plugins.anthropic.anthropic_plugin import AnthropicPlugin
from pipelex.plugins.bedrock.bedrock_plugin import BedrockPlugin
from pipelex.plugins.contract import PipelexPlugin
from pipelex.plugins.gateway.gateway_plugin import GatewayPlugin
from pipelex.plugins.google.google_plugin import GooglePlugin
from pipelex.plugins.mistral.mistral_plugin import MistralPlugin
from pipelex.plugins.openai.openai_plugin import OpenAIPlugin
from pipelex.plugins.portkey.portkey_plugin import PortkeyPlugin

# The plugins Pipelex ships with — discovered at boot ahead of any external
# entry-point plugin. Each is import-light: importing this module imports no
# backend SDK (the SDKs load lazily inside the make_worker closures).
BUILTIN_PLUGINS: list[PipelexPlugin] = [
    OpenAIPlugin(),
    GatewayPlugin(),
    PortkeyPlugin(),
    AnthropicPlugin(),
    MistralPlugin(),
    BedrockPlugin(),
    GooglePlugin(),
]

# Built-in plugins that core requires unconditionally — naming one in
# ``plugins.disabled`` is a configuration error, not a no-op. OpenAI is the
# always-on default driver (no optional SDK to avoid), so disabling it would only
# break the out-of-the-box experience.
CORE_UNCONDITIONAL_PLUGIN_NAMES: frozenset[str] = frozenset({"openai"})
