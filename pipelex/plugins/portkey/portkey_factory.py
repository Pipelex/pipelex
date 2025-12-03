from __future__ import annotations

from typing import TYPE_CHECKING

from portkey_ai import (
    PORTKEY_GATEWAY_URL,  # type: ignore[reportUnknownVariableType]
)

from pipelex.hub import get_telemetry_manager
from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory
from pipelex.plugins.portkey.portkey_exceptions import PortkeyCredentialsError

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.backend import InferenceBackend


class PortkeyFactory(OpenAIResponsesFactory):
    @classmethod
    def is_debug_enabled(cls, backend: InferenceBackend) -> bool:
        is_debug_configured = backend.extra_config.get("debug", False)
        return get_telemetry_manager().is_portkey_logging_enabled(is_debug_configured=is_debug_configured)

    @classmethod
    def get_endpoint(cls, backend: InferenceBackend) -> str:
        return backend.endpoint or PORTKEY_GATEWAY_URL

    @classmethod
    def get_api_key(cls, backend: InferenceBackend) -> str:
        if not backend.api_key:
            msg = "Portkey API key is not set"
            raise PortkeyCredentialsError(msg)
        return backend.api_key
