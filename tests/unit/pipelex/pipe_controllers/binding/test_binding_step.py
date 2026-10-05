import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.pipes.inputs.exceptions import PipeRunInputsError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipe_controllers.binding.binding_derivation import BindingDerivation, BindingRoot, derive_binding
from pipelex.pipe_controllers.binding.binding_step import BindingStep
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.unit.pipelex.pipe_controllers.binding.test_data import INVOICE, RESOLVER, SupplierRecord, make_invoice_record

_INVOICE_CONCEPT = Concept(domain_code="billing", code="Invoice", description="An invoice", structure_class_name="InvoiceRecord")
_SUPPLIER_CONCEPT = Concept(domain_code="billing", code="Supplier", description="A supplier", structure_class_name="SupplierRecord")
_NUMBER_CONCEPT = Concept(domain_code="native", code="Number", description="A number", structure_class_name="NumberContent")
_LINE_CONCEPT = Concept(domain_code="billing", code="InvoiceLine", description="A line", structure_class_name="InvoiceLineRecord")
_SEQUENCE_CODE = "acknowledge_invoice"


def _derive(path: str, *, root: BindingRoot = INVOICE) -> BindingDerivation:
    return derive_binding(path=path, root=root, resolver=RESOLVER)


def _memory_with_invoice(*, note: str | None = None) -> WorkingMemory:
    working_memory = WorkingMemory()
    invoice_stuff = StuffFactory.make_stuff(concept=_INVOICE_CONCEPT, content=make_invoice_record(note=note), name="invoice")
    working_memory.add_new_stuff(name="invoice", stuff=invoice_stuff)
    return working_memory


def _memory_with_absent_invoice() -> tuple[WorkingMemory, AbsenceRecord]:
    working_memory = WorkingMemory()
    root_absence = AbsenceRecord(variable_name="invoice", kind=AbsenceKind.NOT_PROVIDED, reason="the caller did not provide 'invoice'")
    working_memory.record_absence(root_absence)
    return working_memory, root_absence


class TestBindingStep:
    def test_c3_the_result_is_a_fresh_stuff_under_the_result_name(self) -> None:
        working_memory = _memory_with_invoice()
        root_stuff = working_memory.get_stuff("invoice")
        step = BindingStep(from_path="invoice.supplier", output_name="supplier")

        outcome = step.bind(
            working_memory=working_memory,
            derivation=_derive("invoice.supplier"),
            result_concept=_SUPPLIER_CONCEPT,
            calling_pipe_code=_SEQUENCE_CODE,
            run_mode=PipeRunMode.LIVE,
        )

        assert outcome.stuff is not None
        assert outcome.absence is None
        bound_stuff = working_memory.get_stuff("supplier")
        assert bound_stuff is outcome.stuff
        assert bound_stuff.stuff_name == "supplier"
        assert bound_stuff.concept == _SUPPLIER_CONCEPT
        assert bound_stuff.stuff_code != root_stuff.stuff_code
        assert working_memory.get_main_stuff() is bound_stuff
        assert isinstance(bound_stuff.content, SupplierRecord)
        assert bound_stuff.content.address.city == "Quimper"

    def test_the_run_can_fix_the_result_stuff_code(self) -> None:
        working_memory = _memory_with_invoice()
        step = BindingStep(from_path="invoice.total", output_name="total_amount")

        outcome = step.bind(
            working_memory=working_memory,
            derivation=_derive("invoice.total"),
            result_concept=_NUMBER_CONCEPT,
            calling_pipe_code=_SEQUENCE_CODE,
            run_mode=PipeRunMode.LIVE,
            stuff_code="final_code",
        )

        assert outcome.stuff is not None
        assert outcome.stuff.stuff_code == "final_code"
        assert outcome.stuff.content == NumberContent(number=1250.5)

    def test_v24_a_bare_name_keeps_the_root_concept(self) -> None:
        working_memory = _memory_with_invoice()
        step = BindingStep(from_path="invoice", output_name="invoice_copy")

        outcome = step.bind(
            working_memory=working_memory,
            derivation=_derive("invoice"),
            result_concept=_INVOICE_CONCEPT,
            calling_pipe_code=_SEQUENCE_CODE,
            run_mode=PipeRunMode.LIVE,
        )

        assert outcome.stuff is not None
        assert outcome.stuff.concept == _INVOICE_CONCEPT
        assert outcome.stuff.content == working_memory.get_stuff("invoice").content
        assert outcome.stuff.content is not working_memory.get_stuff("invoice").content

    def test_c2_rebinding_the_root_leaves_the_bound_value_as_it_was(self) -> None:
        working_memory = _memory_with_invoice()
        step = BindingStep(from_path="invoice.total", output_name="total_amount")
        step.bind(
            working_memory=working_memory,
            derivation=_derive("invoice.total"),
            result_concept=_NUMBER_CONCEPT,
            calling_pipe_code=_SEQUENCE_CODE,
            run_mode=PipeRunMode.LIVE,
        )
        other_invoice = make_invoice_record()
        other_invoice.total = 3.0
        working_memory.set_new_main_stuff(StuffFactory.make_stuff(concept=_INVOICE_CONCEPT, content=other_invoice, name="invoice"), name="invoice")

        assert working_memory.get_stuff("total_amount").content == NumberContent(number=1250.5)

    def test_v18_a_path_holding_nothing_records_a_declared_absence_naming_the_segment(self) -> None:
        working_memory = _memory_with_invoice(note=None)
        step = BindingStep(from_path="invoice.note", output_name="delivery_note")

        outcome = step.bind(
            working_memory=working_memory,
            derivation=_derive("invoice.note"),
            result_concept=_NUMBER_CONCEPT,
            calling_pipe_code=_SEQUENCE_CODE,
            run_mode=PipeRunMode.LIVE,
        )

        expected_record = AbsenceRecord(
            variable_name="delivery_note",
            kind=AbsenceKind.DECLARED_ABSENT,
            reason=(
                'the binding step { from = "invoice.note", result = "delivery_note" } of pipe \'acknowledge_invoice\' bound nothing, '
                "because 'invoice.note' holds nothing"
            ),
        )
        assert outcome.stuff is None
        assert outcome.absence == expected_record
        assert outcome.is_skipped is False
        assert working_memory.get_optional_stuff("delivery_note") is None
        assert working_memory.get_optional_absence("delivery_note") == expected_record
        assert working_memory.get_optional_absence(MAIN_STUFF_NAME) == expected_record

    def test_v20_an_absent_root_skips_the_binding_with_upstream_provenance(self) -> None:
        working_memory, root_absence = _memory_with_absent_invoice()
        step = BindingStep(from_path="invoice.total", output_name="total_amount")

        outcome = step.bind(
            working_memory=working_memory,
            derivation=_derive("invoice.total"),
            result_concept=_NUMBER_CONCEPT,
            calling_pipe_code=_SEQUENCE_CODE,
            run_mode=PipeRunMode.LIVE,
        )

        assert outcome.stuff is None
        assert outcome.is_skipped is True
        assert outcome.absence == AbsenceRecord(
            variable_name="total_amount",
            kind=AbsenceKind.SKIPPED,
            reason="skipped because input 'invoice' is absent",
            upstream=root_absence,
        )
        recorded = working_memory.get_optional_absence("total_amount")
        assert recorded is not None
        assert recorded.provenance_chain() == [outcome.absence, root_absence]
        assert recorded.origin() == root_absence

    def test_a_list_result_over_an_absent_root_is_an_empty_list_with_a_note(self) -> None:
        """A plural slot is never absent: the skip is kept as a note beside an empty list."""
        working_memory, root_absence = _memory_with_absent_invoice()
        step = BindingStep(from_path="invoice.lines", output_name="lines")

        outcome = step.bind(
            working_memory=working_memory,
            derivation=_derive("invoice.lines"),
            result_concept=_LINE_CONCEPT,
            calling_pipe_code=_SEQUENCE_CODE,
            run_mode=PipeRunMode.LIVE,
        )

        bound_stuff = working_memory.get_stuff("lines")
        assert outcome.stuff is bound_stuff
        assert bound_stuff.content == ListContent[StuffContent](items=[])
        assert outcome.absence is not None
        assert outcome.absence.kind == AbsenceKind.SKIPPED
        assert outcome.absence.upstream == root_absence
        assert working_memory.get_optional_absence("lines") == outcome.absence

    def test_an_empty_list_over_an_absent_root_takes_the_stuff_code_the_run_fixes(self) -> None:
        """A binding ending a sequence takes the run's final stuff code, which the graph tracer links its producer by."""
        working_memory, _ = _memory_with_absent_invoice()
        step = BindingStep(from_path="invoice.lines", output_name="lines")

        outcome = step.bind(
            working_memory=working_memory,
            derivation=_derive("invoice.lines"),
            result_concept=_LINE_CONCEPT,
            calling_pipe_code=_SEQUENCE_CODE,
            run_mode=PipeRunMode.LIVE,
            stuff_code="final_code",
        )

        assert outcome.stuff is not None
        assert outcome.stuff.stuff_code == "final_code"
        assert working_memory.get_stuff("lines").stuff_code == "final_code"

    def test_a_root_neither_present_nor_recorded_absent_is_a_run_error(self) -> None:
        step = BindingStep(from_path="invoice.total", output_name="total_amount")

        with pytest.raises(PipeRunInputsError, match="reads 'invoice', which is not in working memory"):
            step.bind(
                working_memory=WorkingMemory(),
                derivation=_derive("invoice.total"),
                result_concept=_NUMBER_CONCEPT,
                calling_pipe_code=_SEQUENCE_CODE,
                run_mode=PipeRunMode.LIVE,
            )

    def test_the_step_is_written_back_as_mthds_writes_it(self) -> None:
        step = BindingStep(from_path="invoice.supplier.address.city", output_name="city")

        assert step.root_name == "invoice"
        assert step.as_written == '{ from = "invoice.supplier.address.city", result = "city" }'
