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

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.input_shaper import InputKind, InputShaper
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_concept_library

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.core.concepts.concept import Concept


class UnregisteredNote(TextContent):
    """A structure class that exists as a type but is deliberately never registered.

    The whole discriminating power of the content-building test below rests on this: the ambient
    class registry cannot resolve the name `UnregisteredNote`, so a build that succeeds proves the
    class came from the injected provider and from nowhere else.
    """


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

    def test_building_a_value_resolves_the_structure_class_through_the_injected_provider(self, mocker: MockerFixture) -> None:
        """Content building takes the class from the provider, not from the ambient class registry.

        The provider was consulted for *resolution* and for *compatibility* long before it was
        consulted for this: `_make_content` handed the whole job to
        `StuffContentFactory.make_stuff_content_from_concept_required`, which resolves the declared
        `structure_class_name` through `get_class_registry()`. That is the regression shape this
        module's docstring describes — a parameter accepted and then bypassed — and it is invisible
        to every other test here, because the real library and the ambient registry agree on every
        name the suite uses.

        So the stub is made to *disagree*: the concept declares `TextContent`, which the registry
        resolves perfectly well, while the provider answers `UnregisteredNote`. Whichever of the two
        the shaper actually asked is then readable off the built content's exact type.

        Beyond pinning the seam, this is the property a caller with no loaded library depends on:
        the registry is empty outside a booted process, so a shaper that reaches it cannot run there
        at all — `is_compatible` is left on the real library here precisely so the failure this
        catches is class resolution and nothing else.
        """
        library = get_concept_library()
        note_concept = ConceptFactory.make(
            concept_code="Note",
            domain_code="injection_probe",
            description="A note the ambient registry and the injected provider deliberately disagree about",
            structure_class_name=TextContent.__name__,
            refines=NativeConceptCode.TEXT.concept_ref,
        )

        stub = mocker.Mock(spec=ConceptProviderAbstract)
        stub.get_native_concept.side_effect = library.get_native_concept
        stub.is_compatible.side_effect = library.is_compatible
        stub.get_structure_class.return_value = UnregisteredNote

        memory = InputShaper.shape(
            {"note": "shaped through the provider"},
            concept_provider=stub,
            input_specs=InputStuffSpecs(root={"note": StuffSpec(concept=note_concept)}),
        )

        stuff = memory.get_stuff(name="note")
        # `is` rather than `isinstance`: `UnregisteredNote` subclasses `TextContent`, so the registry's
        # answer would satisfy an isinstance check against the base and pass a broken implementation.
        assert type(stuff.content) is UnregisteredNote
        assert stuff.content.text == "shaped through the provider"
        assert stuff.concept.concept_ref == "injection_probe.Note"
        assert stub.get_structure_class.called
