"""The corpus generator's divergence gate sees every engine/projection difference.

The generator states one guarantee, in its module docstring and again in `DivergenceCollector`'s:
every difference between the reference projection and the engine's own renderer lands in a declared
class, and an undeclared one fails the command. Nothing in the committed corpus can check that — the
corpus is exactly the case where the projection is *right*. So each case here mutates one projected
value the way a real regression would, and states that the gate reports it rather than absorbing it
into a declared class that would then explain it away in `mthds-js` and `mthds-python` as contract
bytes. The controls beside them state the real divergences, which must keep their class.
"""

from __future__ import annotations

import pytest

from pipelex.cli.dev_cli.commands.generate_projection_corpus_cmd import (
    COMPACT_SHAPE,
    MOCK_URL_PREFIX,
    DivergenceCollector,
)
from pipelex.core.pipes.variable_multiplicity import PresenceMarker
from pipelex.pipeline.input_form import ListField, PipeInputFormDescriptor, TextItem


def _list_slot_descriptor(*, name: str, item_count: int | None) -> PipeInputFormDescriptor:
    """A one-slot descriptor whose only field is a list, fixed-count (`[N]`) or variable (`[]`)."""
    return PipeInputFormDescriptor(
        fields=[
            ListField(
                name=name,
                required=True,
                presence=PresenceMarker.PLAIN,
                gating=item_count is not None,
                item=TextItem(required=True),
                item_count=item_count,
            )
        ]
    )


class TestTheDivergenceGateSeesEveryDifference:
    def test_a_key_only_the_engine_renders_refuses_the_record(self) -> None:
        """A field the projection stopped rendering: the dict walk iterates the projected keys."""
        collector = DivergenceCollector()

        collector.compare(
            engine_value={"title": "title_value", "stamp": "stamp_value"},
            projected_value={"title": "title_value"},
            path=["probe.dossier", COMPACT_SHAPE],
        )

        assert collector.counts.get("engine-only-field") == 1
        # Undeclared on purpose: no bundle reaches it today, so a capture that does must write the
        # declaration rather than inherit one nobody reviewed.
        with pytest.raises(ValueError, match="Undeclared divergence class"):
            collector.declared()

    def test_a_regressed_file_leaf_url_is_not_absorbed_by_its_own_class(self) -> None:
        """The file-leaf arm returned without ever comparing the one key both sides carry."""
        collector = DivergenceCollector()

        collector.compare(
            engine_value={"url": f"{MOCK_URL_PREFIX}url", "width": 100, "mime_type": "image/png"},
            projected_value={"url": "WRONG"},
            path=["probe.probe_native_inputs", COMPACT_SHAPE, "icon"],
        )

        assert collector.counts.get("file-leaf-not-expanded") == 1
        # Nor re-absorbed one arm further down: plain recursion would hand the regressed placeholder
        # to `text-named-url`, whose only test is that the *engine* value is a mock URL.
        assert "text-named-url" not in collector.counts
        assert any("icon.url" in site for site in collector.unclassified), collector.unclassified

    def test_an_intact_file_leaf_stays_one_declared_divergence(self) -> None:
        """The control: the expansion is the declared difference, and it stands alone."""
        collector = DivergenceCollector()

        collector.compare(
            engine_value={"url": f"{MOCK_URL_PREFIX}url", "width": 100, "mime_type": "image/png"},
            projected_value={"url": f"{MOCK_URL_PREFIX}url"},
            path=["probe.probe_native_inputs", COMPACT_SHAPE, "icon"],
        )

        assert collector.counts == {"file-leaf-not-expanded": 1}
        assert not collector.unclassified

    def test_a_wrong_element_count_at_a_fixed_slot_is_not_absorbed(self) -> None:
        """`fixed-count-honoured` means the declared count, not merely more than one element."""
        collector = DivergenceCollector()
        collector.register_fixed_counts(pipe_ref="probe.probe_markers", descriptor=_list_slot_descriptor(name="two", item_count=2))

        collector.compare(
            engine_value=["gadget"],
            projected_value=["gadget", "gadget", "gadget", "gadget"],
            path=["probe.probe_markers", COMPACT_SHAPE, "two"],
        )

        assert "fixed-count-honoured" not in collector.counts
        assert collector.unclassified

    def test_a_duplicated_variable_list_is_not_misattributed(self) -> None:
        """A `Concept[]` slot declares no count, so a second element there is nobody's declared divergence."""
        collector = DivergenceCollector()
        collector.register_fixed_counts(pipe_ref="probe.probe_markers", descriptor=_list_slot_descriptor(name="many", item_count=None))

        collector.compare(
            engine_value=["widget"],
            projected_value=["widget", "widget"],
            path=["probe.probe_markers", COMPACT_SHAPE, "many"],
        )

        assert "fixed-count-honoured" not in collector.counts
        assert collector.unclassified

    def test_an_honoured_fixed_count_keeps_its_class(self) -> None:
        """The control: the engine emits one element whatever the count, and that is the declared difference."""
        collector = DivergenceCollector()
        collector.register_fixed_counts(pipe_ref="probe.probe_markers", descriptor=_list_slot_descriptor(name="two", item_count=2))

        collector.compare(
            engine_value=["gadget"],
            projected_value=["gadget", "gadget"],
            path=["probe.probe_markers", COMPACT_SHAPE, "two"],
        )

        assert collector.counts == {"fixed-count-honoured": 1}
        assert not collector.unclassified
