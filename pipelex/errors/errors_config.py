from pydantic import ConfigDict, field_validator

from pipelex.system.configuration.config_model import ConfigModel


class ErrorsConfig(ConfigModel):
    """Settings governing how Pipelex renders error reports.

    ``base_uri``: the URL prefix used to derive a per-class ``type`` URI for
    every :class:`pipelex.base_exceptions.PipelexError` subclass. The default
    points at the public ``pipelex.dev/errors`` documentation site; private
    deployments may override it to point at their own error doc host.
    """

    model_config = ConfigDict(frozen=True)

    base_uri: str

    @field_validator("base_uri", mode="after")
    @classmethod
    def _normalize_base_uri(cls, value: str) -> str:
        stripped = value.strip().rstrip("/")
        if not stripped:
            msg = "ErrorsConfig.base_uri must be a non-empty, non-whitespace URI"
            raise ValueError(msg)
        return stripped
