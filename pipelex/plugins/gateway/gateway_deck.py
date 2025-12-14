from pipelex.plugins.gateway.gateway_exceptions import GatewayDeckError
from pipelex.plugins.portkey.portkey_constants import PortkeyHeaderKey


class GatewayDeck:
    @classmethod
    def get_config_id(cls, headers: dict[str, str]) -> str:
        config_id = headers.get(PortkeyHeaderKey.CONFIG)
        if not config_id:
            msg = f"Could not get '{PortkeyHeaderKey.CONFIG}' field from headers"
            raise GatewayDeckError(msg)
        return config_id
