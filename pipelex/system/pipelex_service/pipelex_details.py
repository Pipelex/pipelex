from pipelex.tools.misc.hash_utils import hash_sha256


class PipelexDetails:
    REMOTE_CONFIG_URL = "https://pipelex-config.s3.eu-west-3.amazonaws.com/pipelex_remote_config_02.json"
    PIPELEX_GATEWAY_API_KEY_VAR = "PIPELEX_GATEWAY_API_KEY"

    @classmethod
    def make_distinct_id(cls, gateway_api_key: str) -> str:
        """Make a distinct_id for PostHog from the gateway API key.

        Args:
            gateway_api_key: The raw Pipelex Gateway API key.

        Returns:
            First 16 characters of SHA256 hex digest.
        """
        return hash_sha256(data=gateway_api_key, length=16)
