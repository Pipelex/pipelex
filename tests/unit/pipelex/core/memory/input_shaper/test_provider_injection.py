"""The injected `concept_provider` is consulted, not merely accepted.

Phase 4 of the hub split converted `core/`'s straddlers to take a `ConceptProviderAbstract` as a
parameter instead of calling `interpreter_hub.get_concept_library()` — that inversion is what lets
core's data model measure zero interpreter modules. But every call site in the suite passes the
identical `get_concept_library()`, so the parameter is only ever proven *accepted*: a regression that
took the provider and then reached for the hub anyway would produce the same answers everywhere and
fail nothing. These pass a provider that answers *differently* from the real library, so an ignored
parameter changes the result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.input_shaper import InputKind, InputShaper
from pipelex.interpreter_hub import get_concept_library

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.core.concepts.concept import Concept


class TestConceptProviderInjection:
    def test_resolve_input_kind_reads_the_injected_provider(self, mocker: MockerFixture) -> None:
        """A stub answering compatibility differently must select a different arm.

        `resolve_input_kind` walks the natives in a fixed order and takes the first `is_compatible`
        hit, so a stub that only ever matches `Number` moves a `Text` concept off the TEXT arm — an
        outcome unreachable through the real library, and unreachable at all if the parameter were
        ignored.
        """
        library = get_concept_library()
        text_concept = library.get_native_concept(native_concept=NativeConceptCode.TEXT)
        number_concept = library.get_native_concept(native_concept=NativeConceptCode.NUMBER)

        # Baseline through the real provider, so the contrast below is not an artefact of the fixture.
        assert InputShaper.resolve_input_kind(text_concept, concept_provider=library) is InputKind.TEXT

        def _only_number_is_compatible(*, wanted_concept: Concept, **_kwargs: object) -> bool:
            """Disagree with the real library on purpose: nothing but `Number` ever matches."""
            return wanted_concept == number_concept

        stub = mocker.Mock(spec=ConceptProviderAbstract)
        stub.get_native_concept.side_effect = library.get_native_concept
        stub.is_compatible.side_effect = _only_number_is_compatible

        assert InputShaper.resolve_input_kind(text_concept, concept_provider=stub) is InputKind.NUMBER
        assert stub.is_compatible.called
        assert stub.get_native_concept.called
