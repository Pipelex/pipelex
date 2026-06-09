import pytest

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode
from pipelex.runtime_bridge.exceptions import (
    MissingMistralWorkflowsPluginError,
    MissingPipelexTemporalExtraError,
    PipelexRuntimeBridgeError,
)


class TestRuntimeBridgeExceptionDisclosure:
    @pytest.mark.parametrize(
        ("error_class", "hint_fragment"),
        [
            (MissingPipelexTemporalExtraError, "pip install 'pipelex[temporal]'"),
            (MissingMistralWorkflowsPluginError, "pip install pipelex-mistralai-workflows"),
        ],
    )
    def test_install_hint_survives_strict_disclosure(
        self,
        error_class: type[PipelexRuntimeBridgeError],
        hint_fragment: str,
    ) -> None:
        """These errors carry an actionable pip-install hint in their message.

        ``_authors_caller_facing_message = True`` must keep that message intact
        under STRICT disclosure; without the flag STRICT would replace it with
        ``INTERNAL_ERROR_PLACEHOLDER`` and the hint would be lost.
        """
        message = f"mode unavailable. Install with: {hint_fragment}"
        payload = error_class(message).to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == message
        assert payload["message"] != INTERNAL_ERROR_PLACEHOLDER
