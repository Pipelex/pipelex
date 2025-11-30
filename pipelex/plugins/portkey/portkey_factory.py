from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import openai
from portkey_ai import (
    AsyncPortkey,
    createHeaders,  # type: ignore[reportUnknownVariableType]
)

from pipelex import log
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.plugins.portkey.portkey_exceptions import PortkeyFactoryError
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.plugins.plugin_sdk_registry import Plugin


class PortkeyOpenAISdkVariant(StrEnum):
    PORTKEY_COMPLETIONS = "portkey_completions"
    PORTKEY_RESPONSES = "portkey_responses"


class PortkeyFactory:
    @classmethod
    def make_portkey_client(
        cls,
        backend: InferenceBackend,
    ) -> AsyncPortkey:
        log.verbose(f"Making Portkey client with endpoint: {backend.endpoint}")
        is_debug = backend.extra_config.get("debug", False)
        if backend.endpoint is None:
            msg = "Portkey endpoint is not set"
            raise PortkeyFactoryError(msg)

        return AsyncPortkey(
            base_url=backend.endpoint,
            api_key=backend.api_key,
            debug=is_debug,
        )

    @classmethod
    def make_portkey_openai_client(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
        config_override: str | None = None,
    ) -> openai.AsyncOpenAI:
        log.verbose(f"Making AsyncOpenAI client with endpoint: {backend.endpoint}")
        try:
            sdk_variant = PortkeyOpenAISdkVariant(plugin.sdk)
        except ValueError as exc:
            msg = f"Plugin '{plugin}' is not supported by OpenAIFactory"
            raise PortkeyFactoryError(msg) from exc
        if backend.endpoint is None:
            msg = "Portkey endpoint is not set"
            raise PortkeyFactoryError(msg)

        config = config_override or backend.extra_config.get("x-portkey-config")
        if not config:
            msg = "x-portkey-config header is required"
            raise ValueError(msg)
        is_debug = backend.extra_config.get("debug", False)

        the_client: openai.AsyncOpenAI
        match sdk_variant:
            case PortkeyOpenAISdkVariant.PORTKEY_COMPLETIONS:
                the_client = openai.AsyncOpenAI(
                    base_url=backend.endpoint,
                    api_key="",
                    default_headers=createHeaders(
                        api_key=backend.api_key,
                        strict_open_ai_compliance=False,
                        debug=is_debug,
                    ),  # type: ignore[call-overload]
                )
            case PortkeyOpenAISdkVariant.PORTKEY_RESPONSES:
                the_client = openai.AsyncOpenAI(
                    base_url=backend.endpoint,
                    api_key="",
                    default_headers=createHeaders(
                        api_key=backend.api_key,
                        debug=is_debug,
                    ),  # type: ignore[call-overload]
                )
        return the_client

    @classmethod
    def make_extract_output_from_portkey_response(
        cls,
        portkey_extract_response: dict[str, Any],
    ) -> ExtractOutput:
        dump = json.dumps(portkey_extract_response, indent=4)
        print(dump)
        # return ExtractOutput(
        #     text=portkey_extract_response["text"],
        #     images=portkey_extract_response["images"],
        # )
        fake_page = Page(
            text=dump,
        )
        return ExtractOutput(
            pages={1: fake_page},
        )
