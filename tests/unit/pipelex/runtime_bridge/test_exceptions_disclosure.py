import pytest

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode
from pipelex.runtime_bridge.exceptions import MissingOrchestratorError
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode


class TestRuntimeBridgeExceptionDisclosure:
    @pytest.mark.parametrize(
        ("mode", "hint_fragment"),
        [
            (PipelexExecutionMode.TEMPORAL_BLOCKING, "pip install pipelex-temporal"),
            (PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET, "pip install pipelex-temporal"),
            (PipelexExecutionMode.MISTRAL_NATIVE, "pip install pipelex-mistralai-workflows"),
        ],
    )
    def test_install_hint_survives_strict_disclosure(
        self,
        mode: PipelexExecutionMode,
        hint_fragment: str,
    ) -> None:
        """MissingOrchestratorError carries a per-mode actionable pip-install hint in its message.

        ``_authors_caller_facing_message = True`` must keep that message intact
        under STRICT disclosure; without the flag STRICT would replace it with
        ``INTERNAL_ERROR_PLACEHOLDER`` and the hint would be lost.
        """
        error = MissingOrchestratorError(mode=mode)
        payload = error.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert hint_fragment in payload["message"]
        assert payload["message"] != INTERNAL_ERROR_PLACEHOLDER
