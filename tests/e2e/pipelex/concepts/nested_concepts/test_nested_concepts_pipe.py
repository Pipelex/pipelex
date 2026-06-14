"""E2E test for pipes with nested concept-to-concept references.

This test verifies that:
1. Concepts with nested concept references can be loaded from MTHDS files
2. The dependency graph correctly orders concept loading
3. Pipes can generate structured output with nested concepts
4. The generated output contains properly typed nested objects

Note: Dry-run mode generates random values, so we only test types and structure, not exact values.
"""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from tests.e2e.pipelex.concepts.nested_concepts.generated_models.nested_concepts_test__customer import Customer
from tests.e2e.pipelex.concepts.nested_concepts.generated_models.nested_concepts_test__invoice import Invoice
from tests.e2e.pipelex.concepts.nested_concepts.generated_models.nested_concepts_test__line_item import LineItem


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestNestedConceptsPipe:
    """E2E tests for pipes that output concepts with nested concept references."""

    async def test_invoice_with_nested_customer_and_line_items(self, pipe_run_mode: PipeRunMode):
        """Test that a pipe can generate an Invoice with nested Customer and LineItem concepts.

        This test verifies the complete flow:
        1. MTHDS file with concept-to-concept references is loaded
        2. Concepts are loaded in topological order (LineItem, Customer before Invoice)
        3. The LLM generates structured output with proper nested types
        4. The output can be accessed via working_memory.get_stuff_as() with typed models
        """
        runner = PipelexMTHDSProtocol(
            library_dirs=["tests/e2e/pipelex/concepts/nested_concepts"],
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="generate_invoice",
            inputs={
                "description_text": TextContent(
                    text="Create an invoice for John Smith (john.smith@example.com) who ordered 3 widgets at $10 each and 2 gadgets at $25 each."
                ),
            },
        )
        pipe_output = response.pipe_output

        # Verify the concept metadata
        assert pipe_output.main_stuff.concept.code == "Invoice"
        assert pipe_output.main_stuff.concept.domain_code == "nested_concepts_test"

        # Get the typed invoice using working_memory.get_stuff_as()
        invoice = pipe_output.working_memory.get_stuff_as("main_stuff", Invoice)
        assert isinstance(invoice, Invoice)

        # Log output for debugging
        pretty_print(invoice, title="Generated Invoice")

        # Verify invoice_number is a non-empty string (don't check exact value - dry run randomizes)
        assert isinstance(invoice.invoice_number, str)
        assert len(invoice.invoice_number) > 0

        # Verify customer is a properly typed nested Customer object
        assert isinstance(invoice.customer, Customer)
        assert isinstance(invoice.customer.name, str)
        assert isinstance(invoice.customer.email, str)

        # Verify line_items is a list of properly typed LineItem objects
        assert isinstance(invoice.line_items, list)
        assert len(invoice.line_items) >= 1  # Dry run creates at least 1 item

        for line_item in invoice.line_items:
            assert isinstance(line_item, LineItem)
            assert isinstance(line_item.product_name, str)
            assert isinstance(line_item.quantity, int)
            assert isinstance(line_item.unit_price, float)

        # Verify total_amount is a number (don't check exact value - dry run randomizes)
        assert isinstance(invoice.total_amount, float)

        # Verify optional notes field (can be None or string)
        assert invoice.notes is None or isinstance(invoice.notes, str)

        # Log detailed structure for debugging
        pretty_print(
            {
                "invoice_number": invoice.invoice_number,
                "customer_name": invoice.customer.name,
                "customer_email": invoice.customer.email,
                "num_line_items": len(invoice.line_items),
                "total_amount": invoice.total_amount,
            },
            title="Invoice Summary",
        )
