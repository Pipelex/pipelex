import pytest

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.providers.typesafe.typesafe_client_factory import make_typesafe_client
from pipelex.providers.typesafe.typesafe_exceptions import TypesafeError


class TestTypesafeClientFactory:
    @pytest.mark.parametrize("api_key", [None, ""], ids=["absent", "empty"])
    def test_it_refuses_a_backend_without_a_usable_key(self, api_key: str | None) -> None:
        """An empty key is no key: the SDK would send `Bearer ` and fail as a retried connection error."""
        backend = InferenceBackend(name="typesafe", endpoint=None, api_key=api_key)

        with pytest.raises(TypesafeError, match="no API key"):
            make_typesafe_client(backend=backend)
