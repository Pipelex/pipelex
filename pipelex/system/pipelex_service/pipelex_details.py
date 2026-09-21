import os

_DEFAULT_REMOTE_CONFIG_URL = "https://pipelex-config.s3.eu-west-3.amazonaws.com/pipelex_remote_config_13.json"
REMOTE_CONFIG_URL_ENV_VAR = "PIPELEX_REMOTE_CONFIG_URL"


class PipelexDetails:
    @classmethod
    def remote_config_url(cls) -> str:
        """The URL to fetch the Pipelex remote config from.

        Reads ``PIPELEX_REMOTE_CONFIG_URL`` from the environment when set
        (useful for testing/staging), otherwise falls back to the production URL.
        """
        return os.environ.get(REMOTE_CONFIG_URL_ENV_VAR) or _DEFAULT_REMOTE_CONFIG_URL
