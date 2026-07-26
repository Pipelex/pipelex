"""Core seam for routing usage emissions out of an isolated sub-execution.

Detecting whether the current call runs inside an isolated sub-execution (an orchestrator's
worker activity) is an orchestrator concern, not core's. A boot-orchestrator plugin claims
``HubSlot.ISOLATED_EXECUTION_PROBE`` with an ambient predicate; core consults it through
``RuntimeHub.is_in_isolated_execution`` and names no orchestrator.
"""

from pipelex.runtime_hub import RuntimeHub


class TestIsolatedExecutionProbe:
    def test_default_is_never_isolated(self) -> None:
        """A fresh hub (no boot-orchestrator claim) reports the in-process default: never isolated."""
        hub = RuntimeHub()
        assert hub.is_in_isolated_execution() is False

    def test_claimed_probe_is_honored_and_consulted_each_call(self) -> None:
        """A claimed probe replaces the default and is ambient — consulted on every call, not cached."""
        hub = RuntimeHub()
        flag = {"isolated": True}
        hub.set_isolated_execution_probe(lambda: flag["isolated"])
        assert hub.is_in_isolated_execution() is True
        flag["isolated"] = False
        assert hub.is_in_isolated_execution() is False
