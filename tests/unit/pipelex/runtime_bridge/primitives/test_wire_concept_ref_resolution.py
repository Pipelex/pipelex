from collections.abc import Callable

import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_concept_library
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory
from pipelex.runtime_hub import get_class_registry

#: On the live route a dependency's alias is its whole package address (`_load_address_based_dependency`),
#: so the key a dependency concept lands under is long and contains slashes — which the enumeration must
#: still match on its `-><domain>.<Code>` tail alone.
_DEPENDENCY_ALIAS = "github.com/mthds/scoring-lib/scoring_lib"
_SHARED_SPELLING = "wire_ref_scoring.WeightedScore"


def _make_weighted_score_concept(description: str) -> Concept:
    return Concept(
        code="WeightedScore",
        domain_code="wire_ref_scoring",
        description=description,
        structure_class_name="TextContent",
    )


class TestWireConceptRefResolution:
    """A stuff names its concept `<domain>.<Code>`, and the library is what says which package meant it.

    This runtime emits only that form. The standard also defines `<package_address>::<domain>.<Code>`
    for a concept a dependency contributes, which this runtime neither emits nor resolves — so a
    dependency's concept arrives spelled exactly like a host's, and the library holds it under
    `<alias>-><domain>.<Code>` with no unaliased twin. One candidate is the answer; two are a
    collision no ref can settle.
    """

    @pytest.fixture(scope="class", autouse=True)
    def _open_library(self, load_empty_library: Callable[[], str]) -> None:
        load_empty_library()

    @pytest.fixture(autouse=True)
    def _register_content_classes(self) -> None:
        registry = get_class_registry()
        if not registry.has_class(name="TextContent"):
            registry.register_class(TextContent)

    @pytest.fixture(autouse=True)
    def _clean_concepts(self):
        yield
        get_concept_library().remove_concepts_by_concept_refs([_SHARED_SPELLING, f"{_DEPENDENCY_ALIAS}->{_SHARED_SPELLING}"])

    def test_a_dependency_contributed_concept_round_trips(self) -> None:
        """A concept only a dependency declares hydrates back, through its aliased entry.

        This is the parity claim: back when the definition rode along on the wire, such a stuff
        rebuilt itself without any lookup. With the ref alone, the aliased key is the only entry
        that holds it — a direct lookup by the bare ref misses.
        """
        dependency_concept = _make_weighted_score_concept("the score as the dependency package shapes it")
        get_concept_library().add_dependency_concept(alias=_DEPENDENCY_ALIAS, concept=dependency_concept)
        working_memory = WorkingMemory()
        working_memory.root["score"] = Stuff(
            stuff_code="s1",
            stuff_name="score",
            concept=dependency_concept,
            content=TextContent(text="87"),
        )

        raw = working_memory.dump_for_transport()
        assert raw["root"]["score"]["concept"] == _SHARED_SPELLING

        hydrated = hydrate_working_memory(raw)

        assert hydrated.root["score"].concept.concept_ref == _SHARED_SPELLING
        assert hydrated.root["score"].concept.description == "the score as the dependency package shapes it"
        assert hydrated.root["score"].content == TextContent(text="87")

    def test_a_spelling_two_packages_share_refuses_by_name(self) -> None:
        """A host bundle and a dependency spelling the same `<domain>.<Code>` refuse, listing both keys.

        This is the case that used to bind the host's definition to the dependency's data with no
        error at all, which is worse than a failure: wrong data, silently.
        """
        host_concept = _make_weighted_score_concept("the HOST's weighted score")
        dependency_concept = _make_weighted_score_concept("the dependency's weighted score")
        concept_library = get_concept_library()
        concept_library.add_new_concept(host_concept)
        concept_library.add_dependency_concept(alias=_DEPENDENCY_ALIAS, concept=dependency_concept)
        working_memory = WorkingMemory()
        working_memory.root["score"] = Stuff(
            stuff_code="s1",
            stuff_name="score",
            concept=dependency_concept,
            content=TextContent(text="87"),
        )

        with pytest.raises(PipeJobError) as exc_info:
            hydrate_working_memory(working_memory.dump_for_transport())

        message = str(exc_info.value)
        assert "score" in message
        assert "ambiguous" in message
        assert _SHARED_SPELLING in message
        assert f"{_DEPENDENCY_ALIAS}->{_SHARED_SPELLING}" in message

    def test_the_host_entry_alone_still_resolves(self) -> None:
        """With no dependency contributing that spelling, the host entry is the one candidate."""
        host_concept = _make_weighted_score_concept("the HOST's weighted score")
        get_concept_library().add_new_concept(host_concept)
        working_memory = WorkingMemory()
        working_memory.root["score"] = Stuff(
            stuff_code="s1",
            stuff_name="score",
            concept=host_concept,
            content=TextContent(text="87"),
        )

        hydrated = hydrate_working_memory(working_memory.dump_for_transport())

        assert hydrated.root["score"].concept.description == "the HOST's weighted score"
