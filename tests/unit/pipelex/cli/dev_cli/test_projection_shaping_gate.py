"""The corpus generator refuses a template the input shaper cannot take back.

A fill-in template exists to be filled in and handed to the runtime, so every slot it pins must
survive `InputShaper.shape`. Twice the corpus committed bytes the runtime rejects outright, and both
times a human review round caught it rather than the capture — the second time the divergence gate
absorbed the broken sites into a declared class and exited 0. This states the gate that catches the
next one, and it follows the declared-never-discovered discipline the divergence record already has:
an unshapeable template no registry entry declares refuses the capture, and a declared entry that has
started shaping refuses it too, so a fix retires its declaration deliberately rather than leaving the
manifest claiming a gap that closed.

The round-trip itself — the shaper actually running against the corpus bundles — is stated in
`test_generate_projection_corpus.py`. The verdicts here are injected, which is what lets the decision
logic be put to the cases no corpus bundle produces: the corpus is exactly where every template is
either declared or shapes cleanly.
"""

from __future__ import annotations

import pytest

from pipelex.cli.dev_cli.commands.generate_projection_corpus_cmd import (
    COMPACT_SHAPE,
    EXPLICIT_SHAPE,
    ShapingGate,
)
from pipelex.core.memory.exceptions import WrongScalarKindError

GAP_ITEM = "L-260830-191719"
DECLARED_PIPE = "probe.probe_single"
CLEAN_PIPE = "probe.probe_native_inputs"


def _shaping_error(*, variable_name: str) -> WrongScalarKindError:
    """A refusal of the shape the corpus's own escapes took: a bare value the declared concept rejects."""
    return WrongScalarKindError.make(
        variable_name=variable_name,
        declared_concept_ref="probe.Widget",
        expected_kind="an object",
        provided_description="a string",
        expected_shape="{...}",
    )


class TestTheShapingGateRefusesWhatTheRuntimeWouldReject:
    def test_an_undeclared_unshapeable_template_refuses_the_capture(self) -> None:
        """The mechanism that would have caught both prior escapes at generation time."""
        gate = ShapingGate(registry={})

        gate.record(pipe_ref=CLEAN_PIPE, shape=COMPACT_SHAPE, error=_shaping_error(variable_name="icon"))

        with pytest.raises(ValueError, match="no EXPECTED_UNSHAPEABLE entry") as refusal:
            gate.declared()
        # The refusal names the pipe, the shape and the error class: enough to go straight to the site.
        assert CLEAN_PIPE in str(refusal.value)
        assert COMPACT_SHAPE in str(refusal.value)
        assert "WrongScalarKindError" in str(refusal.value)

    def test_a_failure_that_is_not_an_input_shaping_error_still_refuses(self) -> None:
        """The round-trip wraps `Exception`: the explicit arm lets a raw pydantic error escape untyped."""
        gate = ShapingGate(registry={})

        gate.record(pipe_ref=CLEAN_PIPE, shape=EXPLICIT_SHAPE, error=ValueError("1 validation error for probe__Widget"))

        with pytest.raises(ValueError, match="no EXPECTED_UNSHAPEABLE entry"):
            gate.declared()

    def test_a_declared_entry_that_now_shapes_refuses_the_capture(self) -> None:
        """The lapse rule: a closed gap retires its declaration deliberately, or the capture stops."""
        gate = ShapingGate(registry={(DECLARED_PIPE, COMPACT_SHAPE): GAP_ITEM})

        gate.record(pipe_ref=DECLARED_PIPE, shape=COMPACT_SHAPE, error=None)

        with pytest.raises(ValueError, match="now shape") as refusal:
            gate.declared()
        assert DECLARED_PIPE in str(refusal.value)

    def test_a_declared_entry_never_walked_at_all_refuses_the_capture(self) -> None:
        """Symmetric with the divergence record: a registry keyed on a pipe this capture never met."""
        gate = ShapingGate(registry={(DECLARED_PIPE, COMPACT_SHAPE): GAP_ITEM})

        gate.record(pipe_ref=CLEAN_PIPE, shape=COMPACT_SHAPE, error=None)

        with pytest.raises(ValueError, match="now shape"):
            gate.declared()

    def test_a_declared_failure_is_stated_in_the_manifest_with_its_ledger_item(self) -> None:
        """Generation is never blocked by the known-open gap: it is declared, recorded and printed."""
        gate = ShapingGate(registry={(DECLARED_PIPE, COMPACT_SHAPE): GAP_ITEM})

        gate.record(pipe_ref=DECLARED_PIPE, shape=COMPACT_SHAPE, error=_shaping_error(variable_name="widget"))
        gate.record(pipe_ref=CLEAN_PIPE, shape=COMPACT_SHAPE, error=None)

        entries = gate.declared()

        assert len(entries) == 1
        entry = entries[0]
        assert entry.pipe_ref == DECLARED_PIPE
        assert entry.shape == COMPACT_SHAPE
        assert entry.error_type == "WrongScalarKindError"
        assert entry.ledger_item == GAP_ITEM

    def test_a_capture_where_every_template_shapes_declares_nothing(self) -> None:
        """The control, and the state this gate exists to reach: an empty registry and no failure."""
        gate = ShapingGate(registry={})

        gate.record(pipe_ref=CLEAN_PIPE, shape=COMPACT_SHAPE, error=None)
        gate.record(pipe_ref=CLEAN_PIPE, shape=EXPLICIT_SHAPE, error=None)

        assert gate.declared() == []

    def test_the_refusal_carries_the_error_message_the_manifest_deliberately_omits(self) -> None:
        """The message is wording that would churn committed bytes, so it stays out of the manifest.

        It is exactly what whoever hits the refusal needs, though, so the refusal itself carries it —
        which is also why the manifest can hold the contract-stable class name alone.
        """
        gate = ShapingGate(registry={})

        gate.record(pipe_ref=CLEAN_PIPE, shape=COMPACT_SHAPE, error=_shaping_error(variable_name="icon"))

        with pytest.raises(ValueError, match="no EXPECTED_UNSHAPEABLE entry") as refusal:
            gate.declared()
        assert "Input 'icon' declares concept" in str(refusal.value)

    def test_the_passing_count_is_kept_but_never_committed(self) -> None:
        """The corpus is almost entirely passing verdicts, so they are counted rather than listed."""
        gate = ShapingGate(registry={(DECLARED_PIPE, COMPACT_SHAPE): GAP_ITEM})

        gate.record(pipe_ref=DECLARED_PIPE, shape=COMPACT_SHAPE, error=_shaping_error(variable_name="widget"))
        gate.record(pipe_ref=CLEAN_PIPE, shape=COMPACT_SHAPE, error=None)
        gate.record(pipe_ref=CLEAN_PIPE, shape=EXPLICIT_SHAPE, error=None)

        assert gate.passing_count == 2
