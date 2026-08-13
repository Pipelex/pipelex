import datetime
from typing import Any

import pytest

from pipelex import log, pretty_print
from pipelex.core.memory.exceptions import (
    ExplicitConceptIncompatibleError,
    ListWhereSingularError,
    MultiplicityCountMismatchError,
)
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.interpreter_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import OpeningTime, Question, ShaperInvoice, ShaperWeird, build_input_specs


class TestInputShaperExplicitForms:
    def test_envelope_structured_compatible(self) -> None:
        """D6: the {concept, content} envelope still works and is now compat-checked against the signature."""
        input_specs = build_input_specs([("invoice", "shaper_test.ShaperInvoice", None)])
        provided = {"concept": "shaper_test.ShaperInvoice", "content": {"invoice_number": "INV-001", "amount": 1250.0}}

        working_memory = InputShaper.shape({"invoice": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["invoice"]
        pretty_print(stuff, title="envelope structured")
        assert stuff.concept.concept_ref == "shaper_test.ShaperInvoice"
        assert stuff.content == ShaperInvoice(invoice_number="INV-001", amount=1250.0)

    def test_envelope_refining_concept_wins(self) -> None:
        """D6: when the envelope names a concept that refines the declared one, the more specific concept wins."""
        input_specs = build_input_specs([("answer", "native.Text", None)])
        provided = {"concept": "shaper_test.Question", "content": "What are the fees?"}

        working_memory = InputShaper.shape({"answer": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["answer"]
        pretty_print(stuff, title="envelope refining wins")
        # The declared lower bound is native.Text, but the caller volunteered the more specific Question.
        assert stuff.concept.concept_ref == "shaper_test.Question"
        assert stuff.content == TextContent(text="What are the fees?")

    @pytest.mark.parametrize(
        ("concept_ref", "expected_type"),
        [("native.Time", TimeContent), ("shaper_test.OpeningTime", OpeningTime)],
    )
    def test_time_envelope_accepts_iso_string(self, concept_ref: str, expected_type: type[TimeContent]) -> None:
        """Explicit envelopes use the shared temporal factory for native Time and refinements."""
        input_specs = build_input_specs([("opening", "native.Time", None)])
        provided = {"concept": concept_ref, "content": "15:40:00+02:00"}

        working_memory = InputShaper.shape({"opening": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["opening"]
        assert stuff.concept.concept_ref == concept_ref
        assert stuff.content == expected_type(time=datetime.time(15, 40, tzinfo=datetime.timezone(datetime.timedelta(hours=2))))

    def test_time_envelope_accepts_time_object(self) -> None:
        input_specs = build_input_specs([("opening", "native.Time", None)])
        provided = {"concept": "native.Time", "content": datetime.time(15, 40)}

        working_memory = InputShaper.shape({"opening": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        assert working_memory.root["opening"].content == TimeContent(time=datetime.time(15, 40))

    def test_prebuilt_stuff_content_object(self) -> None:
        """D6: a directly-provided StuffContent keeps today's behavior, plus the compat check."""
        input_specs = build_input_specs([("invoice", "shaper_test.ShaperInvoice", None)])
        provided = ShaperInvoice(invoice_number="INV-002", amount=99.0)

        working_memory = InputShaper.shape(
            {"invoice": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"], concept_provider=get_concept_library()
        )

        stuff = working_memory.root["invoice"]
        pretty_print(stuff, title="prebuilt object")
        assert stuff.concept.concept_ref == "shaper_test.ShaperInvoice"
        assert stuff.content == ShaperInvoice(invoice_number="INV-002", amount=99.0)

    def test_list_of_prebuilt_stuff_content_items(self) -> None:
        """D6: a bare list of already-built StuffContent items (Case 1.4) shapes element-wise, no regression.

        Each item keeps today's behavior — concept inferred from its class, then compat-checked — so a
        Python-API caller passing typed content in a list works exactly like the wrapped ListContent form.
        """
        input_specs = build_input_specs([("questions", "shaper_test.Question", True)])
        provided = [Question(text="a"), Question(text="b")]

        working_memory = InputShaper.shape(
            {"questions": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"], concept_provider=get_concept_library()
        )

        stuff = working_memory.root["questions"]
        pretty_print(stuff, title="list of prebuilt StuffContent")
        assert stuff.concept.concept_ref == "shaper_test.Question"
        assert stuff.content == ListContent(items=[Question(text="a"), Question(text="b")])

    def test_list_of_prebuilt_incompatible_item_raises(self) -> None:
        """D6: an already-built item whose concept is incompatible with the declared item concept is a D4 error."""
        input_specs = build_input_specs([("priorities", "shaper_test.Priority", True)])
        provided = [Question(text="a")]

        with pytest.raises(ExplicitConceptIncompatibleError, match="not compatible"):
            InputShaper.shape(
                {"priorities": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"], concept_provider=get_concept_library()
            )

    def test_explicit_list_into_singular_raises(self) -> None:
        """D2: an explicit ListContent (or envelope-with-list) must not fill a singular-declared slot.

        Without the reconcile in `_shape_explicit`, this list would be *silently* stored into the
        singular slot (the D6 compat check alone never looks at multiplicity).
        """
        input_specs = build_input_specs([("question", "shaper_test.Question", None)])
        provided: ListContent[Question] = ListContent(items=[Question(text="a"), Question(text="b")])

        with pytest.raises(ListWhereSingularError, match="declares a single"):
            InputShaper.shape(
                {"question": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"], concept_provider=get_concept_library()
            )

    def test_explicit_list_wrong_fixed_count_raises(self) -> None:
        """D2: an explicit ListContent whose length differs from a declared [N] count is a D4 error."""
        input_specs = build_input_specs([("questions", "shaper_test.Question", 2)])
        provided: ListContent[Question] = ListContent(items=[Question(text="only-one")])

        with pytest.raises(MultiplicityCountMismatchError, match="exactly 2 items"):
            InputShaper.shape(
                {"questions": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"], concept_provider=get_concept_library()
            )

    def test_explicit_list_into_list_slot_ok(self) -> None:
        """D2/D6: an explicit ListContent whose length matches a declared list slot shapes cleanly."""
        input_specs = build_input_specs([("questions", "shaper_test.Question", True)])
        provided: ListContent[Question] = ListContent(items=[Question(text="a"), Question(text="b")])

        working_memory = InputShaper.shape(
            {"questions": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"], concept_provider=get_concept_library()
        )

        stuff = working_memory.root["questions"]
        pretty_print(stuff, title="explicit list into list slot")
        assert stuff.concept.concept_ref == "shaper_test.Question"
        assert stuff.content == ListContent(items=[Question(text="a"), Question(text="b")])

    def test_explicit_list_content_into_dynamic_slot_ok(self) -> None:
        """D5/D6: a Dynamic slot keeps bottom-up list behavior for prebuilt ListContent."""
        input_specs = build_input_specs([("payload", "native.Dynamic", None)])
        provided: ListContent[Question] = ListContent(items=[Question(text="a"), Question(text="b")])

        working_memory = InputShaper.shape(
            {"payload": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"], concept_provider=get_concept_library()
        )

        stuff = working_memory.root["payload"]
        pretty_print(stuff, title="explicit list into Dynamic slot")
        assert stuff.concept.concept_ref == "shaper_test.Question"
        assert stuff.content == ListContent(items=[Question(text="a"), Question(text="b")])

    def test_envelope_collision_rule_nested_escape_hatch(self) -> None:
        """D6: a dict with exactly {concept, content} is ALWAYS an envelope, even for a structure with those fields.

        The escape hatch for a structure literally named with `concept`/`content` fields is the nested
        envelope: the inner content dict carries the real field values.
        """
        log.info("Testing the {concept, content} collision rule")
        input_specs = build_input_specs([("weird", "shaper_test.ShaperWeird", None)])
        provided = {"concept": "shaper_test.ShaperWeird", "content": {"concept": "x", "content": "y"}}

        working_memory = InputShaper.shape({"weird": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["weird"]
        pretty_print(stuff, title="collision rule")
        assert stuff.concept.concept_ref == "shaper_test.ShaperWeird"
        assert stuff.content == ShaperWeird(concept="x", content="y")

    def test_envelope_empty_list_yields_empty_list_content(self) -> None:
        """An envelope carrying an empty list builds an empty ListContent, like the bare `[]` does.

        Regression: this raised "Cannot create Stuff from empty list in content". The bottom-up
        factory infers a list's item type from its first item, and an empty list has none — but
        with an envelope it never needed to infer, because the envelope NAMES the concept. The
        result was that the two spellings of one input disagreed: a caller with no pictures could
        send `[]` and run, or send `{"concept": ..., "content": []}` and fail.
        """
        input_specs = build_input_specs([("pics", "native.Image", True)])
        provided: dict[str, Any] = {"concept": "native.Image", "content": []}

        working_memory = InputShaper.shape({"pics": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["pics"]
        pretty_print(stuff, title="envelope empty list")
        assert stuff.concept.concept_ref == "native.Image"
        assert stuff.content == ListContent(items=[])

    def test_envelope_and_bare_empty_list_agree(self) -> None:
        """The two spellings of "a plural input with nothing in it" must produce the same Stuff content."""
        input_specs = build_input_specs([("pics", "native.Image", True)])

        envelope: dict[str, Any] = {"concept": "native.Image", "content": []}
        via_envelope = InputShaper.shape({"pics": envelope}, input_specs=input_specs, concept_provider=get_concept_library())
        via_bare = InputShaper.shape({"pics": []}, input_specs=input_specs, concept_provider=get_concept_library())

        assert via_envelope.root["pics"].content == via_bare.root["pics"].content
        assert via_envelope.root["pics"].concept.concept_ref == via_bare.root["pics"].concept.concept_ref

    def test_envelope_empty_list_under_structured_concept(self) -> None:
        """Not just natives: a structured concept's empty list is equally representable."""
        input_specs = build_input_specs([("questions", "shaper_test.Question", True)])
        provided: dict[str, Any] = {"concept": "shaper_test.Question", "content": []}

        working_memory = InputShaper.shape({"questions": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["questions"]
        assert stuff.concept.concept_ref == "shaper_test.Question"
        assert stuff.content == ListContent(items=[])
