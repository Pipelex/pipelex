import openai

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.types import StrEnum


class OpenAIClientFactoryError(CogtError):
    pass


class OpenAISdkVariant(StrEnum):
    AZURE_OPENAI = "azure_openai"
    AZURE_OPENAI_RESPONSES = "azure_openai_responses"
    OPENAI = "openai"
    OPENAI_RESPONSES = "openai_responses"
    OPENAI_IMG_GEN = "openai_img_gen"
    BLACKBOXAI_IMG_GEN = "blackboxai_img_gen"


class AzureExtraField(StrEnum):
    API_VERSION = "api_version"


class OpenAIClientFactory:
    @classmethod
    def make_openai_client(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> openai.AsyncClient:
        try:
            sdk_variant = OpenAISdkVariant(plugin.sdk)
        except ValueError as exc:
            msg = f"Plugin '{plugin}' is not supported by '{cls.__name__}'"
            raise OpenAIClientFactoryError(msg) from exc

        # We have a workaround here:
        # OpenAI can be used without any API key (for instance when pointing to local Ollama) but the SDK,
        # as it is, raises if there is no API key (api_key is None and there is no env var).
        # But it works fine with an empty string.
        api_key = backend.api_key or ""

        the_client: openai.AsyncOpenAI
        match sdk_variant:
            case OpenAISdkVariant.AZURE_OPENAI | OpenAISdkVariant.AZURE_OPENAI_RESPONSES:
                log.verbose(f"Making AsyncOpenAI client with endpoint: {backend.endpoint}")
                if backend.endpoint is None:
                    msg = "Azure OpenAI endpoint is not set"
                    raise OpenAIClientFactoryError(msg)
                the_client = openai.AsyncAzureOpenAI(
                    azure_endpoint=backend.endpoint,
                    api_key=api_key,
                    api_version=backend.get_extra_config(AzureExtraField.API_VERSION),
                )
            case OpenAISdkVariant.OPENAI | OpenAISdkVariant.OPENAI_RESPONSES | OpenAISdkVariant.OPENAI_IMG_GEN | OpenAISdkVariant.BLACKBOXAI_IMG_GEN:
                log.verbose(f"Making AsyncOpenAI client with endpoint: {backend.endpoint}")
                the_client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url=backend.endpoint,
                )

        return the_client
