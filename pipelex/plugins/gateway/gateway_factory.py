from __future__ import annotations

from typing import TYPE_CHECKING

from portkey_ai import (
    PORTKEY_GATEWAY_URL,
    AsyncPortkey,  # type: ignore[reportUnknownVariableType]
)

from pipelex import log
from pipelex.hub import get_telemetry_manager
from pipelex.plugins.gateway.gateway_exceptions import PortkeyCredentialsError
from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.backend import InferenceBackend


class GatewayFactory(OpenAIResponsesFactory):
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

    @classmethod
    def make_portkey_client(
        cls,
        backend: InferenceBackend,
    ) -> AsyncPortkey:
        is_debug_enabled = cls.is_debug_enabled(backend=backend)
        endpoint = cls.get_endpoint(backend=backend)
        api_key = cls.get_api_key(backend=backend)
        log.verbose(f"Making Portkey client with endpoint: {endpoint}, debug: {is_debug_enabled}")

        return AsyncPortkey(
            base_url=endpoint,
            api_key=api_key,
            debug=is_debug_enabled,
        )
