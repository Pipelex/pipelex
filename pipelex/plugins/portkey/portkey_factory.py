from __future__ import annotations

from typing import TYPE_CHECKING

import openai
from portkey_ai import createHeaders  # type: ignore[reportUnknownVariableType]

from pipelex import log
from pipelex.plugins.portkey.portkey_exceptions import PortkeyFactoryError
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.plugins.plugin_sdk_registry import Plugin


class PortkeySdkVariant(StrEnum):
    PORTKEY_COMPLETIONS = "portkey_completions"
    PORTKEY_RESPONSES = "portkey_responses"


class PortkeyFactory:
    @classmethod
    def make_portkey_openai_client(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> openai.AsyncOpenAI:
        log.verbose(f"Making AsyncOpenAI client with endpoint: {backend.endpoint}")
        try:
            sdk_variant = PortkeySdkVariant(plugin.sdk)
        except ValueError as exc:
            msg = f"Plugin '{plugin}' is not supported by OpenAIFactory"
            raise PortkeyFactoryError(msg) from exc
        if backend.endpoint is None:
            msg = "Portkey endpoint is not set"
            raise PortkeyFactoryError(msg)
        is_debug = backend.extra_config.get("debug", False)

        the_client: openai.AsyncOpenAI
        match sdk_variant:
            case PortkeySdkVariant.PORTKEY_COMPLETIONS:
                the_client = openai.AsyncOpenAI(
                    base_url=backend.endpoint,
                    api_key="",
                    default_headers=createHeaders(
                        api_key=backend.api_key,
                        strict_open_ai_compliance=False,
                        debug=is_debug,
                    ),  # type: ignore[call-overload]
                )
            case PortkeySdkVariant.PORTKEY_RESPONSES:
                the_client = openai.AsyncOpenAI(
                    base_url=backend.endpoint,
                    api_key="",
                    default_headers=createHeaders(
                        api_key=backend.api_key,
                        debug=is_debug,
                    ),  # type: ignore[call-overload]
                )
        return the_client
