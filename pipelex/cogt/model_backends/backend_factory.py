from typing import Any

from pydantic import Field, field_validator

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.typing.pydantic_utils import empty_dict_factory_of, empty_list_factory_of


class InferenceBackendBlueprint(ConfigModel):
    enabled: bool = True
    endpoint: str | None = None
    api_key: str | None = None
    listed_constraints: list[ListedConstraint] = Field(default_factory=empty_list_factory_of(ListedConstraint))
    valued_constraints: dict[ValuedConstraint, Any] = Field(default_factory=empty_dict_factory_of(ValuedConstraint))
    extra_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("listed_constraints", mode="before")
    @classmethod
    def validate_listed_constraints(cls, value: list[str]) -> list[ListedConstraint]:
        return ConfigModel.transform_list_of_str_to_enum(
            input_list=value,
            enum_cls=ListedConstraint,
        )

    @field_validator("valued_constraints", mode="before")
    @classmethod
    def validate_valued_constraints(cls, value: dict[str, Any]) -> dict[ValuedConstraint, Any]:
        return ConfigModel.transform_dict_keys_str_to_enum(
            input_dict=value,
            key_enum_cls=ValuedConstraint,
        )


class InferenceBackendFactory:
    # The fields Vertex AI derives at boot from its extra config: the endpoint from the project and
    # location, the API key by minting an OAuth token from the service-account file.
    VERTEXAI_DERIVED_FIELDS = ("endpoint", "api_key")

    @classmethod
    def make_inference_backend(
        cls,
        name: str,
        *,
        blueprint: InferenceBackendBlueprint,
        extra_config: dict[str, Any],
        model_specs: ModelSpecIndex,
        credentials: CredentialResolution,
        unresolved_credentials: dict[str, list[str]],
    ) -> InferenceBackend:
        """Build a backend from its loaded blueprint.

        Args:
            name: The backend's name, its table name in `backends.toml`.
            blueprint: The backend's standard fields, already resolved or, on a keyless load, stripped
                of every field that references a variable.
            extra_config: The backend's other keys, likewise.
            model_specs: The backend's models.
            credentials: Whether this load resolves credentials. On `SKIP`, Vertex AI mints no token.
            unresolved_credentials: What the load left unresolved, field by field (see
                `InferenceBackend.unresolved_credentials`).
        """
        endpoint = blueprint.endpoint
        api_key = blueprint.api_key
        unresolved_credentials = dict(unresolved_credentials)
        # Deal with special authentication for some backends
        match name:
            case "vertexai":
                match credentials:
                    case CredentialResolution.REQUIRE:
                        # Deferred import: avoid pulling heavy SDK at module-load time
                        from pipelex.providers.openai.vertexai_factory import VertexAIFactory  # ruff: ignore[import-outside-top-level]

                        endpoint, api_key = VertexAIFactory.make_endpoint_and_api_key(extra_config=extra_config)
                    case CredentialResolution.SKIP:
                        # Minting the token reads the service-account file and calls Google over the
                        # network: exactly the credential resolution a keyless load does not do.
                        endpoint, api_key = None, None
                        for derived_field in cls.VERTEXAI_DERIVED_FIELDS:
                            unresolved_credentials.setdefault(derived_field, [])
            case _:
                pass
        return InferenceBackend(
            name=name,
            enabled=blueprint.enabled,
            endpoint=endpoint,
            api_key=api_key,
            listed_constraints=blueprint.listed_constraints,
            valued_constraints=blueprint.valued_constraints,
            extra_config=extra_config,
            model_specs=model_specs,
            unresolved_credentials=unresolved_credentials,
        )
