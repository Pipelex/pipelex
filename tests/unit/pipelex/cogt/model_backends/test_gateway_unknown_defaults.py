"""The remote gateway config may carry keys this client's model-spec blueprint does not know.

It is served by a component that deploys on its own schedule, so a client can read a config written
by a different release than itself. `InferenceModelSpecBlueprint` forbids extra fields, so without
this pruning an unknown key in the remote `defaults` block hard-fails the boot — which is exactly
what happened the day `prompting_target` was removed while the served config still declared it.

The same skew tolerance applies per model, where it is the loader's rule rather than this function's —
see `test_gateway_unknown_per_model_keys.py`. A local backend file gets the strict counterpart of both
rules — see `test_backend_library_leniency.py`.
"""

from typing import Any, cast

from pytest_mock import MockerFixture

from pipelex import log
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

    def test_pruning_does_not_need_the_log_hub(self, mocker: MockerFixture) -> None:
        """It runs on the success path of every gateway load, including ones that precede runtime_hub.set_config().

        The served config really does carry an unknown key today, so this is the ordinary path, not a corner.
        """
        mocker.patch.object(log.log_dispatch, "_log_config_instance", None)

        pruned = drop_unknown_gateway_defaults(gateway_model_specs=self._specs(defaults={"max_tokens": 4096, "a_field_we_removed": "anthropic"}))

        assert pruned["defaults"] == {"max_tokens": 4096}

    def test_per_model_unknown_keys_are_untouched(self) -> None:
        """This function is scoped to `defaults`; the per-model rule is the loader's, tested in `test_gateway_unknown_per_model_keys.py`."""
        # The unknown key in `defaults` is what forces the deep-copy prune to run at all: without it
        # the function early-returns and this test proves nothing.
        specs = self._specs(defaults={"max_tokens": 4096, "a_field_we_removed": "anthropic"})
        cast("dict[str, Any]", specs["gpt-4o-mini"])["x-some-header"] = "value"

        pruned = drop_unknown_gateway_defaults(gateway_model_specs=specs)

        assert pruned is not specs
        assert cast("dict[str, Any]", pruned["gpt-4o-mini"])["x-some-header"] == "value"
