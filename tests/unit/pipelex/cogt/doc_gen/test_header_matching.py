import pytest

from pipelex.cogt.doc_gen.header_matching import column_fields, field_key


class TestHeaderMatching:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            pytest.param("unit_price", "unitprice", id="underscores"),
            pytest.param("Unit price", "unitprice", id="spaces-and-case"),
            pytest.param("invoice.customer.name", "invoicecustomername", id="dots"),
            pytest.param("  Due\tDate ", "duedate", id="every-whitespace"),
            pytest.param("InvoiceCustomerName", "invoicecustomername", id="camel-case"),
        ],
    )
    def test_field_key_ignores_case_spaces_dots_and_underscores(self, name: str, expected: str) -> None:
        assert field_key(name) == expected

    def test_a_header_binds_the_field_it_matches(self) -> None:
        matched = column_fields(headers={0: "Unit price", 1: "Quantity", 2: "Notes"}, field_names=["unit_price", "quantity"])

        assert matched == {0: ["unit_price"], 1: ["quantity"]}

    def test_a_header_matching_several_fields_lists_them_all(self) -> None:
        matched = column_fields(headers={3: "Unit price"}, field_names=["unit_price", "unitprice"])

        assert matched == {3: ["unit_price", "unitprice"]}

    def test_a_header_spelling_a_field_exactly_binds_it_before_any_comparison(self) -> None:
        matched = column_fields(headers={0: "unit_price", 1: "unitprice", 2: "Unit Price"}, field_names=["unit_price", "unitprice"])

        # Each exact header binds its own field; a header spelling neither exactly is still ambiguous.
        assert matched == {0: ["unit_price"], 1: ["unitprice"], 2: ["unit_price", "unitprice"]}
