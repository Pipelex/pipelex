from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent


def _make_text_stuff(name: str, *, text: str) -> Stuff:
    return StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text=text),
        name=name,
    )


def _make_memory() -> WorkingMemory:
    """A memory holding a long list, a context, a main stuff aliased under its own name, and an absence."""
    working_memory = WorkingMemory()
    notes_stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=ListContent[TextContent](items=[TextContent(text=f"note {index_note}") for index_note in range(50)]),
        name="notes",
    )
    working_memory.add_new_stuff(name="notes", stuff=notes_stuff)
    working_memory.add_new_stuff(name="context", stuff=_make_text_stuff("context", text="the context"))
    working_memory.set_new_main_stuff(stuff=_make_text_stuff("summary", text="the summary"), name="summary")
    working_memory.record_absence(
        AbsenceRecord(
            variable_name="penalty_clause",
            kind=AbsenceKind.DECLARED_ABSENT,
            reason="no value found for penalty_clause",
            producing_pipe="some_producer",
        )
    )
    return working_memory


class TestWorkingMemoryDeepCopyOf:
    def test_carries_only_the_named_stuffs(self):
        """The copy holds what the names reach and nothing else: the list nobody named stays behind."""
        working_memory = _make_memory()

        copied_memory = working_memory.make_deep_copy_of(names={"context", "penalty_clause", "not_in_memory"})

        assert set(copied_memory.root) == {"context"}
        assert copied_memory.aliases == {}
        assert set(copied_memory.absences) == {"penalty_clause"}
        assert copied_memory.get_stuff_as_str("context") == "the context"
        assert not copied_memory.is_stuff_exists("notes")
        assert not copied_memory.is_stuff_exists("not_in_memory")

    def test_the_copy_is_deep(self):
        """Rewriting a copied stuff in place, or adding to the copy, leaves the original memory as it was."""
        working_memory = _make_memory()

        copied_memory = working_memory.make_deep_copy_of(names={"context"})
        copied_memory.get_stuff_as_text("context").text = "rewritten"
        copied_memory.add_new_stuff(name="added", stuff=_make_text_stuff("added", text="added"))

        assert working_memory.get_stuff_as_str("context") == "the context"
        assert not working_memory.is_stuff_exists("added")
        assert copied_memory.get_stuff("context") is not working_memory.get_stuff("context")

    def test_an_alias_brings_its_target(self):
        """A name that is an alias brings the alias and the stuff it targets, so it reads in the copy as in the original."""
        working_memory = _make_memory()

        copied_memory = working_memory.make_deep_copy_of(names={MAIN_STUFF_NAME})

        assert copied_memory.aliases == {MAIN_STUFF_NAME: "summary"}
        assert set(copied_memory.root) == {"summary"}
        assert copied_memory.get_main_stuff().content == TextContent(text="the summary")

    def test_an_alias_to_an_absent_slot_brings_its_record(self):
        """An alias whose target resolved as absent brings the target's record, so it resolves to that absence in the copy."""
        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="clause", stuff=_make_text_stuff("clause", text="a clause"))
        working_memory.set_alias("current_clause", target="clause")
        working_memory.record_resolved_absence(
            AbsenceRecord(variable_name="clause", kind=AbsenceKind.DECLARED_ABSENT, reason="no clause", producing_pipe="some_producer")
        )

        copied_memory = working_memory.make_deep_copy_of(names={"current_clause"})

        resolved = copied_memory.resolve_stuff("current_clause")
        assert isinstance(resolved, AbsenceRecord)
        assert resolved.reason == "no clause"
