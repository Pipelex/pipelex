import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent


def _make_text_stuff(name: str, *, text: str = "hello") -> Stuff:
    return StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text=text),
        name=name,
    )


def _make_record(variable_name: str, *, upstream: AbsenceRecord | None = None) -> AbsenceRecord:
    return AbsenceRecord(
        variable_name=variable_name,
        kind=AbsenceKind.DECLARED_ABSENT,
        reason=f"no value found for {variable_name}",
        producing_pipe="some_producer",
        upstream=upstream,
    )


class TestAbsenceLedger:
    def test_record_and_lookup_absence(self):
        """A recorded absence is retrievable by variable name; the slot holds no stuff."""
        working_memory = WorkingMemory()
        record = _make_record("penalty_clause")
        working_memory.record_absence(record)

        assert working_memory.get_optional_stuff("penalty_clause") is None
        found = working_memory.get_optional_absence("penalty_clause")
        assert found is not None
        assert found.variable_name == "penalty_clause"
        assert found.kind == AbsenceKind.DECLARED_ABSENT
        assert found.reason == "no value found for penalty_clause"
        assert found.producing_pipe == "some_producer"

    def test_resolve_stuff_returns_absence_record_when_absent(self):
        """The tri-state resolved accessor returns the AbsenceRecord for a recorded-absent slot."""
        working_memory = WorkingMemory()
        record = _make_record("penalty_clause")
        working_memory.record_absence(record)

        resolved = working_memory.resolve_stuff("penalty_clause")
        assert isinstance(resolved, AbsenceRecord)
        assert resolved.variable_name == "penalty_clause"

    def test_resolve_stuff_prefers_present_value(self):
        """When a slot has both a stuff and a stale ledger note, the value wins."""
        working_memory = WorkingMemory()
        stuff = _make_text_stuff("items")
        working_memory.set_stuff(name="items", stuff=stuff)
        # A ledger note can coexist with a present value (D4 plural normalization).
        working_memory.absences["items"] = _make_record("items")

        resolved = working_memory.resolve_stuff("items")
        assert isinstance(resolved, Stuff)
        assert resolved.stuff_name == "items"

    def test_resolve_stuff_raises_when_neither_value_nor_record(self):
        """A slot with no value and no record is still a hard miss — that is the bug case."""
        working_memory = WorkingMemory()
        with pytest.raises(WorkingMemoryStuffNotFoundError):
            working_memory.resolve_stuff("never_produced")

    def test_set_stuff_supersedes_absence_record(self):
        """Writing a value under a name clears that name's absence record."""
        working_memory = WorkingMemory()
        working_memory.record_absence(_make_record("assessment"))
        working_memory.set_stuff(name="assessment", stuff=_make_text_stuff("assessment"))

        assert working_memory.get_optional_absence("assessment") is None
        assert isinstance(working_memory.resolve_stuff("assessment"), Stuff)

    def test_record_new_main_absence_mirrors_to_main_stuff(self):
        """Recording a pipe's output absence marks both the slot and the main-stuff position,
        and removes any stale main stuff so the previous value cannot masquerade as the output.
        """
        working_memory = WorkingMemory()
        previous = _make_text_stuff("previous_result")
        working_memory.set_new_main_stuff(previous, name="previous_result")

        record = _make_record("assessment")
        working_memory.record_new_main_absence(record)

        assert working_memory.get_optional_main_stuff() is None
        assert working_memory.get_optional_absence("assessment") == record
        main_resolved = working_memory.resolve_main_stuff()
        assert isinstance(main_resolved, AbsenceRecord)
        assert main_resolved.variable_name == "assessment"
        # The previous value stays in memory under its own name.
        assert working_memory.get_optional_stuff("previous_result") is not None

    def test_set_new_main_stuff_clears_stale_main_absence(self):
        """A later pipe setting a real main stuff supersedes the positional main-stuff record."""
        working_memory = WorkingMemory()
        working_memory.record_new_main_absence(_make_record("assessment"))
        working_memory.set_new_main_stuff(_make_text_stuff("report"), name="report")

        main_resolved = working_memory.resolve_main_stuff()
        assert isinstance(main_resolved, Stuff)
        # The named-slot record stays: 'assessment' is still genuinely absent.
        assert working_memory.get_optional_absence("assessment") is not None
        assert working_memory.get_optional_absence(MAIN_STUFF_NAME) is None

    def test_provenance_chain_walks_to_origin(self):
        """provenance_chain() lists the record then its upstream chain; origin is the first absence."""
        origin = _make_record("penalty_clause")
        middle = AbsenceRecord(
            variable_name="assessment",
            kind=AbsenceKind.SKIPPED,
            reason="skipped because input 'penalty_clause' is absent",
            producing_pipe="assess_penalty",
            upstream=origin,
        )
        tip = AbsenceRecord(
            variable_name="summary",
            kind=AbsenceKind.SKIPPED,
            reason="skipped because input 'assessment' is absent",
            producing_pipe="summarize",
            upstream=middle,
        )

        chain = tip.provenance_chain()
        assert chain == [tip, middle, origin]
        assert tip.origin() == origin
        assert origin.origin() == origin

    def test_deep_copy_preserves_absences(self):
        working_memory = WorkingMemory()
        working_memory.record_absence(_make_record("penalty_clause"))
        copy = working_memory.make_deep_copy()
        copied_record = copy.get_optional_absence("penalty_clause")
        assert copied_record is not None
        assert copied_record.reason == "no value found for penalty_clause"

    def test_model_dump_includes_absences(self):
        working_memory = WorkingMemory()
        working_memory.record_absence(_make_record("penalty_clause"))
        dumped = working_memory.model_dump()
        assert "absences" in dumped
        assert dumped["absences"]["penalty_clause"]["reason"] == "no value found for penalty_clause"
        assert dumped["absences"]["penalty_clause"]["kind"] == "declared_absent"
