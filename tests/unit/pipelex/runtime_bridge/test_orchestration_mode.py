from pipelex.runtime_bridge.orchestration_mode import DIRECT_ORCHESTRATION_MODE, OrchestrationMode


class TestOrchestrationMode:
    def test_direct_token_is_stable(self) -> None:
        """Core's one built-in token is the literal ``"direct"`` — the registry key and the input default."""
        assert DIRECT_ORCHESTRATION_MODE == "direct"

    def test_orchestration_mode_is_a_plain_str_alias(self) -> None:
        """The open token is assignment-compatible with plain ``str`` so plugins register raw strings, cast-free."""
        # OrchestrationMode is a semantic alias for str: a bare token (here a synthetic plugin's)
        # is a valid OrchestrationMode with no construction/cast.
        token: OrchestrationMode = "acme"
        assert isinstance(token, str)
        assert token == "acme"
        assert OrchestrationMode is str
