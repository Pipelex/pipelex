import pytest

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode
from pipelex.runtime_bridge.exceptions import MissingOrchestratorError


class TestRuntimeBridgeExceptionDisclosure:
    @pytest.mark.parametrize("mode", ["temporal", "mistralai-workflows", "acme"])
    def test_generic_plugin_hint_survives_strict_disclosure(self, mode: str) -> None:
        """MissingOrchestratorError carries a caller-actionable, plugin-decoupled hint in its message.

        ``_authors_caller_facing_message = True`` must keep that message intact under
        STRICT disclosure; without the flag STRICT would replace it with
        ``INTERNAL_ERROR_PLACEHOLDER`` and the "is its plugin installed?" hint would be lost.
        """
        error = MissingOrchestratorError(mode=mode)
        payload = error.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert mode in payload["message"]
        assert "is its plugin installed?" in payload["message"]
        assert payload["message"] != INTERNAL_ERROR_PLACEHOLDER
