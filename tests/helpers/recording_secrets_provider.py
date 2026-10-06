"""A secrets provider that answers every lookup the same way and records them.

The keyless-boot tests vary exactly one thing, whether credentials are present, so the result does
not depend on which keys the developer or the CI runner happens to hold. The same double plays the
three parts those tests need: built with no value it holds no secret at all, built with a value it
holds every secret, and in both cases `looked_up` says what the boot asked it, in order.
"""

from typing_extensions import override

from pipelex.tools.secrets.exceptions import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class RecordingSecretsProvider(SecretsProviderAbstract):
    def __init__(self, *, value: str | None) -> None:
        self._value = value
        self.looked_up: list[str] = []

    @classmethod
    def make_empty(cls) -> "RecordingSecretsProvider":
        """Holds no secret: every lookup raises `SecretNotFoundError`."""
        return cls(value=None)

    @classmethod
    def make_credentialed(cls) -> "RecordingSecretsProvider":
        """Holds every secret, each one `"fake-key"`."""
        return cls(value="fake-key")

    @override
    def get_required_secret(self, secret_id: str) -> str:
        self.looked_up.append(secret_id)
        if self._value is None:
            msg = f"No secret '{secret_id}' in this test provider"
            raise SecretNotFoundError(msg)
        return self._value

    @override
    def get_optional_secret(self, secret_id: str) -> str | None:
        self.looked_up.append(secret_id)
        return self._value

    @override
    def get_required_secret_specific_version(self, secret_id: str, *, version_id: str) -> str:
        return self.get_required_secret(secret_id=secret_id)

    @override
    def get_optional_secret_specific_version(self, secret_id: str, *, version_id: str) -> str | None:
        return self.get_optional_secret(secret_id=secret_id)

    @override
    def set_secret_as_env_var(self, secret_id: str, *, version_id: str = "latest") -> None:
        raise NotImplementedError
