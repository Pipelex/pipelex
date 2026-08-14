import copy
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from pipelex import log
from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs, InferenceModelSpecBlueprint


class GatewayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_specs: BackendModelSpecs = Field(description="Model specifications for Pipelex Gateway (model_name -> spec dict)")
    aws_region: str = Field(description="AWS region")


def drop_unknown_gateway_defaults(*, gateway_model_specs: BackendModelSpecs) -> BackendModelSpecs:
    """Drop keys the model-spec blueprint no longer knows from the remote config's `defaults` block.

    The gateway config is served by a component that deploys on its own schedule, so a client can
    legitimately read a config written by a newer or older release than itself. An unknown key there
    is version skew, and dropping it keeps a boot working across that skew; a *local* backend file
    stays strict, because there an unknown key really is the author's typo.

    Scoped to `defaults` on purpose. A per-model key the blueprint does not know is already meaningful
    — `_load_backend` reclassifies it as an outbound HTTP header — and that behaviour is not this
    function's to reinterpret.
    """
    known_fields = InferenceModelSpecBlueprint.model_fields.keys()
    defaults = gateway_model_specs.get("defaults")
    if not isinstance(defaults, dict):
        return gateway_model_specs

    unknown_keys = [key for key in cast("dict[str, Any]", defaults) if key not in known_fields]
    if not unknown_keys:
        return gateway_model_specs

    log.verbose(f"Ignoring unknown key(s) in the remote gateway config defaults: {', '.join(sorted(unknown_keys))}")
    pruned: BackendModelSpecs = copy.deepcopy(gateway_model_specs)
    pruned_defaults = cast("dict[str, Any]", pruned["defaults"])
    for unknown_key in unknown_keys:
        del pruned_defaults[unknown_key]
    return pruned
