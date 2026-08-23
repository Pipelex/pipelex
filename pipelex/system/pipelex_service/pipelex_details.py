import os

from pipelex.tools.misc.hash_utils import hash_sha256

# Spike 4 workbench catalog, out of band at version 1000 so it sits beside the
# official files without pushing the next real build past its natural successor.
# It is the first catalog that carries no gateway routing at all: no
# `x-portkey-config`, no `endpoint_path`. When the change ships, this line moves
# to the real next version and the 1000 file is abandoned.
_DEFAULT_REMOTE_CONFIG_URL = "https://pipelex-config.s3.eu-west-3.amazonaws.com/pipelex_remote_config_1000.json"
REMOTE_CONFIG_URL_ENV_VAR = "PIPELEX_REMOTE_CONFIG_URL"


class PipelexDetails:
    PIPELEX_GATEWAY_API_KEY_VAR = "PIPELEX_GATEWAY_API_KEY"

    @classmethod
    def remote_config_url(cls) -> str:
        """The URL to fetch the Pipelex remote config from.

        Reads ``PIPELEX_REMOTE_CONFIG_URL`` from the environment when set
        (useful for testing/staging), otherwise falls back to the production URL.
        """
        return os.environ.get(REMOTE_CONFIG_URL_ENV_VAR) or _DEFAULT_REMOTE_CONFIG_URL

    @classmethod
    def make_distinct_id(cls, gateway_api_key: str) -> str:
        """Make a distinct_id for PostHog from the gateway API key.

        Args:
            gateway_api_key: The raw Pipelex Gateway API key.

        Returns:
            First 16 characters of SHA256 hex digest.
        """
        return hash_sha256(data=gateway_api_key, length=16)
