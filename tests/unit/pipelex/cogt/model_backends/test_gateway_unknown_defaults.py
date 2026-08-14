"""The remote gateway config may carry keys this client's model-spec blueprint does not know.

It is served by a component that deploys on its own schedule, so a client can read a config written
by a different release than itself. `InferenceModelSpecBlueprint` forbids extra fields, so without
this pruning an unknown key in the remote `defaults` block hard-fails the boot — which is exactly
what happened the day `prompting_target` was removed while the served config still declared it.
"""

from typing import Any, cast

from pipelex.cogt.model_backends.gateway_config import drop_unknown_gateway_defaults
from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs, InferenceModelSpecBlueprint


class TestGatewayUnknownDefaults:
    def _specs(self, *, defaults: dict[str, Any]) -> BackendModelSpecs:
        return cast(
            "BackendModelSpecs",
            {
                "defaults": defaults,
                "gpt-4o-mini": {"model_id": "gpt-4o-mini", "sdk": "openai"},
            },
        )

    def test_unknown_default_key_is_dropped(self) -> None:
        pruned = drop_unknown_gateway_defaults(gateway_model_specs=self._specs(defaults={"max_tokens": 4096, "a_field_we_removed": "anthropic"}))

        assert pruned["defaults"] == {"max_tokens": 4096}

    def test_the_spec_still_validates_after_pruning(self) -> None:
        """The point of the pruning, stated as the thing that used to raise."""
        pruned = drop_unknown_gateway_defaults(gateway_model_specs=self._specs(defaults={"max_tokens": 4096, "a_field_we_removed": "anthropic"}))

        merged = dict(cast("dict[str, Any]", pruned["defaults"]))
        merged.update(cast("dict[str, Any]", pruned["gpt-4o-mini"]))
        blueprint = InferenceModelSpecBlueprint.model_validate(merged)

        assert blueprint.max_tokens == 4096

    def test_known_defaults_are_left_alone(self) -> None:
        """No unknown key means the caller gets its own object back, uncopied."""
        specs = self._specs(defaults={"max_tokens": 4096})

        assert drop_unknown_gateway_defaults(gateway_model_specs=specs) is specs

    def test_per_model_unknown_keys_are_untouched(self) -> None:
        """A per-model unknown key means something already — it becomes an outbound HTTP header."""
        specs = self._specs(defaults={"max_tokens": 4096})
        cast("dict[str, Any]", specs["gpt-4o-mini"])["x-some-header"] = "value"

        pruned = drop_unknown_gateway_defaults(gateway_model_specs=specs)

        assert cast("dict[str, Any]", pruned["gpt-4o-mini"])["x-some-header"] == "value"
