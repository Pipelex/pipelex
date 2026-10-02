from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, ErrorReport
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.model_backends.model_type import ModelType


class TestModelChoiceNotFoundDisclosure:
    @staticmethod
    def _make_error() -> ModelChoiceNotFoundError:
        return ModelChoiceNotFoundError(
            message="Model handle 'gpt-5.1' was not found in the model deck",
            model_type=ModelType.LLM,
            model_choice="gpt-5.1",
            suggestions=["gpt-5.5", "gpt-5.4"],
        )

    def test_message_survives_strict_disclosure(self) -> None:
        """The unknown model name and its suggestions reach a STRICT (hosted) caller instead of the placeholder."""
        payload = self._make_error().to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == "Model handle 'gpt-5.1' was not found in the model deck\n\nDid you mean: gpt-5.5, gpt-5.4"
        assert payload["message"] != INTERNAL_ERROR_PLACEHOLDER
        assert payload["error_type"] == "ModelChoiceNotFoundError"
        assert payload["error_domain"] == "input"

    def test_message_survives_the_worker_to_runner_hop(self) -> None:
        """The hosted path packs the report VERBOSE on the worker, rebuilds it on the runner, then projects STRICT.

        The caller-facing flag is computed where the error is raised (the worker), so it must ride the
        VERBOSE round trip for the runner's STRICT projection to keep the message.
        """
        packed = self._make_error().to_error_report().to_dict()
        recovered = ErrorReport.from_dict(packed)
        assert recovered.caller_facing_message is True
        payload = recovered.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert "gpt-5.1" in payload["message"]
        assert "Did you mean: gpt-5.5, gpt-5.4" in payload["message"]
