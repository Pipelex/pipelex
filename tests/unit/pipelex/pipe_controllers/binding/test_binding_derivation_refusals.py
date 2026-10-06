import pytest

from pipelex.pipe_controllers.binding.binding_derivation import BindingRoot, derive_binding
from pipelex.pipe_controllers.binding.exceptions import BindingPathUnresolvedError
from tests.unit.pipelex.pipe_controllers.binding.test_data import INVOICE, RESOLVER, make_root


class TestBindingDerivationRefusals:
    @pytest.mark.parametrize(
        ("path", "root", "failed_segment", "available_fields", "message_fragment"),
        [
            # A segment naming no field lists the fields that were available
            ("invoice.totl", INVOICE, "totl", None, "has no field 'totl'"),
            ("invoice.supplier.adress", INVOICE, "adress", ["name", "address"], "Its fields are: 'name', 'address'."),
            # A segment after a plain field, whatever native it derives
            ("invoice.total.amount", INVOICE, "amount", [], "a number field, a leaf"),
            ("invoice.paid.probability", INVOICE, "probability", [], "a boolean field, a leaf"),
            ("invoice.issued_on.date", INVOICE, "date", [], "a date field, a leaf"),
            # A segment after a native holding its value in a single field, however the walk reached it
            ("invoice.amount_due.number", INVOICE, "number", [], "holds its value in a single field"),
            ("note.text", make_root("native.Text"), "text", [], "holds its value in a single field"),
            ("count.number", make_root("native.Number"), "number", [], "holds its value in a single field"),
            ("payload.json_obj", make_root("native.JSON"), "json_obj", [], "holds its value in a single field"),
            ("summary.text", make_root("native.Markdown"), "text", [], "holds its value in a single field"),
            ("departure.time", make_root("native.Time"), "time", [], "holds its value in a single field"),
            ("caption.text", make_root("billing.Caption"), "text", [], "refines 'native.Text'"),
            # A segment after a dict
            ("invoice.metadata.code", INVOICE, "code", [], "a dict field, a leaf"),
            # A segment after a list with no item_type, and a path ending on one
            ("invoice.attachments.name", INVOICE, "name", [], "the list declares no item_type"),
            ("invoice.attachments", INVOICE, "attachments", [], "the path ends on the segment 'attachments'"),
            # A concept with no structure to walk
            ("anything.name", make_root("native.Anything"), "name", [], "is structureless by definition"),
            ("dynamic.name", make_root("native.Dynamic"), "name", [], "is structureless by definition"),
            ("composite.name", make_root("native.Composite"), "name", [], "is structureless by definition"),
            ("remark.text", make_root("billing.Remark"), "text", [], "is declared with neither a structure nor refines"),
            ("memo.subject", make_root("billing.Memo"), "subject", [], "is declared with neither a structure nor refines"),
            ("memo_copy.subject", make_root("billing.MemoCopy"), "subject", [], "refines 'billing.Memo'"),
            ("invoice.remark.text", INVOICE, "text", [], "is declared with neither a structure nor refines"),
            ("stranger.name", make_root("billing.Stranger"), "name", [], "is not declared in this bundle"),
        ],
    )
    def test_refuses_the_path(
        self,
        path: str,
        root: BindingRoot,
        failed_segment: str,
        available_fields: list[str] | None,
        message_fragment: str,
    ):
        with pytest.raises(BindingPathUnresolvedError) as raised:
            derive_binding(path=path, root=root, resolver=RESOLVER)

        assert raised.value.failed_segment == failed_segment
        assert raised.value.path == path
        if available_fields is not None:
            assert raised.value.available_fields == available_fields
        assert message_fragment in str(raised.value)
        assert f"'{failed_segment}'" in str(raised.value)

    def test_an_unknown_field_lists_every_field_available_there(self):
        with pytest.raises(BindingPathUnresolvedError) as raised:
            derive_binding(path="invoice.totl", root=INVOICE, resolver=RESOLVER)

        assert "total" in raised.value.available_fields
        assert "'total'" in str(raised.value)
        assert raised.value.available_fields[0] == "supplier_name"
