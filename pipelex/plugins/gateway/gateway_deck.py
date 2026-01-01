from pipelex import log
from pipelex.config import get_config
from pipelex.plugins.gateway.gateway_exceptions import GatewayDeckError
from pipelex.plugins.portkey.portkey_constants import PortkeyHeaderKey


class GatewayDeck:
    @classmethod
    def get_config_id(cls, headers: dict[str, str]) -> str:
        config_id = headers.get(PortkeyHeaderKey.CONFIG)
        if not config_id:
            msg = f"Could not get '{PortkeyHeaderKey.CONFIG}' field from headers"
            raise GatewayDeckError(msg)
        config_id_substitutions = get_config().cogt.gateway_test_config.config_id_substitutions
        if config_id_substitutions:
            log.dev(f"Substituting config ID '{config_id}' with '{config_id_substitutions.get(config_id, config_id)}'")
            return config_id_substitutions.get(config_id, config_id)
        return config_id
