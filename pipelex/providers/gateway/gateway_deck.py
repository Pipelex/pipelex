from pipelex import log
from pipelex.config import get_config
from pipelex.providers.gateway.gateway_exceptions import GatewayDeckError
from pipelex.providers.portkey.portkey_constants import PortkeyHeaderKey


class GatewayDeck:
    """Resolve the gateway config id a model's headers name.

    Kept only for the img_gen worker, which is the last caller and is itself
    unreachable: the gateway now routes on the model id in the request body, so
    no served model carries a config header and none of the completions, extract
    or search paths asks for one any more. It goes when that worker moves onto
    the real /images/generations and /images/edits routes; removing it before
    then would mean half-editing a worker that is meant to be left alone.
    """

    @classmethod
    def get_config_id(cls, headers: dict[str, str]) -> str:
        config_id = headers.get(PortkeyHeaderKey.CONFIG)
        if not config_id:
            msg = f"Could not get '{PortkeyHeaderKey.CONFIG}' field from headers"
            raise GatewayDeckError(msg)
        config_id_substitutions = get_config().inference.gateway_test.config_id_substitutions
        if config_id_substitutions and (substitute := config_id_substitutions.get(config_id)) and substitute != config_id:
            log.warning(f"Substituting config ID '{config_id}' with '{substitute}'")
            return substitute
        return config_id
