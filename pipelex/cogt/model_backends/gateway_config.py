import copy
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs, InferenceModelSpecBlueprint


class GatewayConfig(BaseModel):
    """One managed gateway backend's slice of the fetched artifact.

    There is one of these per declared managed backend, built from that backend's named section of
    the single fetched artifact. They are held in a `dict[backend_name, GatewayConfig]` rather than
    merged, because the two services are two services: a handle that one serves and the other does
    not is a legitimate configuration, not a conflict to resolve.
    """

    model_config = ConfigDict(extra="forbid")

    model_specs: BackendModelSpecs = Field(description="Model specifications for this managed gateway (model_name -> spec dict)")
    aws_region: str | None = Field(
        default=None,
        description=(
            "AWS region, threaded into the backend's extra_config. Optional because it is a top-level key of the artifact rather than "
            "a property of a section, and only a direct-SDK Bedrock backend ever reads it back — nothing on the manifold path does, "
            "because Bedrock credentials live gateway-side. A managed config built without one simply contributes no region."
        ),
    )


def drop_unknown_gateway_defaults(*, gateway_model_specs: BackendModelSpecs) -> BackendModelSpecs:
    """Drop keys the model-spec blueprint no longer knows from the remote config's `defaults` block.

    The gateway config is served by a component that deploys on its own schedule, so a client can
    legitimately read a config written by a newer or older release than itself. An unknown key there
    is version skew, and dropping it keeps a boot working across that skew; a *local* backend file
    stays strict, because there an unknown key really is the author's typo.

    Scoped to `defaults` on purpose. A per-model key gets its own rule in `InferenceBackendLibrary.load`,
    via `split_model_spec_keys`: header-shaped keys are outbound request headers, and the rest is pruned
    from a remote payload (the same skew judgement as here) or fatal in a local file.

    Deliberately pure, and deliberately silent: it runs on the success path of every gateway-backend
    load, including loads that happen before `runtime_hub.set_config()` has configured the log
    dispatch. A `log` call here would turn a plain data transform into a boot-order dependency and
    crash the caller with `LogConfig is not set`.
    """
    known_fields = InferenceModelSpecBlueprint.model_fields.keys()
    defaults = gateway_model_specs.get("defaults")
    if not isinstance(defaults, dict):
        return gateway_model_specs

    unknown_keys = [key for key in cast("dict[str, Any]", defaults) if key not in known_fields]
    if not unknown_keys:
        return gateway_model_specs

    pruned: BackendModelSpecs = copy.deepcopy(gateway_model_specs)
    pruned_defaults = cast("dict[str, Any]", pruned["defaults"])
    for unknown_key in unknown_keys:
        del pruned_defaults[unknown_key]
    return pruned
