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
from tests.unit.pipelex.core.memory.input_shaper.data import Question, ShaperInvoice, ShaperWeird, build_input_specs


class TestInputShaperExplicitForms:
    def test_envelope_structured_compatible(self) -> None:
        """D6: the {concept, content} envelope still works and is now compat-checked against the signature."""
        input_specs = build_input_specs([("invoice", "shaper_test.ShaperInvoice", None)])
        provided = {"concept": "shaper_test.ShaperInvoice", "content": {"invoice_number": "INV-001", "amount": 1250.0}}

        working_memory = InputShaper.shape({"invoice": provided}, input_specs=input_specs)

        stuff = working_memory.root["invoice"]
        pretty_print(stuff, title="envelope structured")
        assert stuff.concept.concept_ref == "shaper_test.ShaperInvoice"
        assert stuff.content == ShaperInvoice(invoice_number="INV-001", amount=1250.0)

    def test_envelope_refining_concept_wins(self) -> None:
        """D6: when the envelope names a concept that refines the declared one, the more specific concept wins."""
        input_specs = build_input_specs([("answer", "native.Text", None)])
        provided = {"concept": "shaper_test.Question", "content": "What are the fees?"}

        working_memory = InputShaper.shape({"answer": provided}, input_specs=input_specs)

        stuff = working_memory.root["answer"]
        pretty_print(stuff, title="envelope refining wins")
        # The declared lower bound is native.Text, but the caller volunteered the more specific Question.
        assert stuff.concept.concept_ref == "shaper_test.Question"
        assert stuff.content == TextContent(text="What are the fees?")

    def test_prebuilt_stuff_content_object(self) -> None:
        """D6: a directly-provided StuffContent keeps today's behavior, plus the compat check."""
        input_specs = build_input_specs([("invoice", "shaper_test.ShaperInvoice", None)])
        provided = ShaperInvoice(invoice_number="INV-002", amount=99.0)

        working_memory = InputShaper.shape({"invoice": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"])

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

        working_memory = InputShaper.shape({"questions": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"])

        stuff = working_memory.root["questions"]
        pretty_print(stuff, title="list of prebuilt StuffContent")
        assert stuff.concept.concept_ref == "shaper_test.Question"
        assert stuff.content == ListContent(items=[Question(text="a"), Question(text="b")])

    def test_list_of_prebuilt_incompatible_item_raises(self) -> None:
        """D6: an already-built item whose concept is incompatible with the declared item concept is a D4 error."""
        input_specs = build_input_specs([("priorities", "shaper_test.Priority", True)])
        provided = [Question(text="a")]

        with pytest.raises(ExplicitConceptIncompatibleError, match="not compatible"):
            InputShaper.shape({"priorities": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"])

    def test_explicit_list_into_singular_raises(self) -> None:
        """D2: an explicit ListContent (or envelope-with-list) must not fill a singular-declared slot.

        Without the reconcile in `_shape_explicit`, this list would be *silently* stored into the
        singular slot (the D6 compat check alone never looks at multiplicity).
        """
        input_specs = build_input_specs([("question", "shaper_test.Question", None)])
        provided: ListContent[Question] = ListContent(items=[Question(text="a"), Question(text="b")])

        with pytest.raises(ListWhereSingularError, match="declares a single"):
            InputShaper.shape({"question": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"])

    def test_explicit_list_wrong_fixed_count_raises(self) -> None:
        """D2: an explicit ListContent whose length differs from a declared [N] count is a D4 error."""
        input_specs = build_input_specs([("questions", "shaper_test.Question", 2)])
        provided: ListContent[Question] = ListContent(items=[Question(text="only-one")])

        with pytest.raises(MultiplicityCountMismatchError, match="exactly 2 items"):
            InputShaper.shape({"questions": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"])

    def test_explicit_list_into_list_slot_ok(self) -> None:
        """D2/D6: an explicit ListContent whose length matches a declared list slot shapes cleanly."""
        input_specs = build_input_specs([("questions", "shaper_test.Question", True)])
        provided: ListContent[Question] = ListContent(items=[Question(text="a"), Question(text="b")])

        working_memory = InputShaper.shape({"questions": provided}, input_specs=input_specs, search_domain_codes=["shaper_test"])

        stuff = working_memory.root["questions"]
        pretty_print(stuff, title="explicit list into list slot")
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

        working_memory = InputShaper.shape({"weird": provided}, input_specs=input_specs)

        stuff = working_memory.root["weird"]
        pretty_print(stuff, title="collision rule")
        assert stuff.concept.concept_ref == "shaper_test.ShaperWeird"
        assert stuff.content == ShaperWeird(concept="x", content="y")
