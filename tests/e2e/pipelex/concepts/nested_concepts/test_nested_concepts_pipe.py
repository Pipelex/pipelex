# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false
"""E2E test for pipes with nested concept-to-concept references.

This test verifies that:
1. Concepts with nested concept references can be loaded from PLX files
2. The dependency graph correctly orders concept loading
3. Pipes can generate structured output with nested concepts
4. The generated output contains properly typed nested objects

Note: pyright checks are disabled for this file because it tests dynamically
generated classes with runtime-determined attributes that can't be statically typed.
"""

from typing import Any

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.execute import execute_pipeline


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestNestedConceptsPipe:
    """E2E tests for pipes that output concepts with nested concept references."""

    async def test_invoice_with_nested_customer_and_line_items(self, pipe_run_mode: PipeRunMode):
        """Test that a pipe can generate an Invoice with nested Customer and LineItem concepts.

        This test verifies the complete flow:
        1. PLX file with concept-to-concept references is loaded
        2. Concepts are loaded in topological order (LineItem, Customer before Invoice)
        3. The LLM generates structured output with proper nested types
        4. The output can be accessed and validated
        """
        pipe_output = await execute_pipeline(
            pipe_code="generate_invoice",
            library_dirs=["tests/e2e/pipelex/concepts/nested_concepts"],
            inputs={
                "description_text": TextContent(
                    text="Create an invoice for John Smith (john.smith@example.com) who ordered 3 widgets at $10 each and 2 gadgets at $25 each."
                ),
            },
            pipe_run_mode=pipe_run_mode,
        )

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify the concept
        assert pipe_output.main_stuff.concept.code == "Invoice"
        assert pipe_output.main_stuff.concept.domain_code == "nested_concepts_test"

        # Get the content - attributes are dynamically generated at runtime
        invoice_content = pipe_output.main_stuff.content
        assert isinstance(invoice_content, StructuredContent)

        # Log output for debugging
        pretty_print(invoice_content, title="Generated Invoice")

        # Verify the invoice has the expected fields
        assert hasattr(invoice_content, "invoice_number")
        assert hasattr(invoice_content, "customer")
        assert hasattr(invoice_content, "line_items")
        assert hasattr(invoice_content, "total_amount")

        # Verify invoice_number is a string
        invoice_number: Any = invoice_content.invoice_number
        assert isinstance(invoice_number, str)
        assert len(invoice_number) > 0

        # Verify customer is a nested concept (StructuredContent with name and email)
        customer: Any = invoice_content.customer
        assert customer is not None
        assert isinstance(customer, StructuredContent)
        assert hasattr(customer, "name")
        assert hasattr(customer, "email")
        customer_name: Any = customer.name
        customer_email: Any = customer.email
        assert isinstance(customer_name, str)
        assert isinstance(customer_email, str)

        # Verify line_items is a list of nested concepts
        line_items: Any = invoice_content.line_items
        assert line_items is not None
        assert isinstance(line_items, list)
        assert len(line_items) >= 1  # At least 1 item (dry mode creates 1, live mode may create more)

        # Verify each line item has the expected structure
        for line_item in line_items:
            assert isinstance(line_item, StructuredContent)
            assert hasattr(line_item, "product_name")
            assert hasattr(line_item, "quantity")
            assert hasattr(line_item, "unit_price")
            product_name: Any = line_item.product_name
            quantity: Any = line_item.quantity
            unit_price: Any = line_item.unit_price
            assert isinstance(product_name, str)
            assert isinstance(quantity, int)
            assert isinstance(unit_price, (int, float))

        # Verify total_amount is a number
        total_amount: Any = invoice_content.total_amount
        assert isinstance(total_amount, (int, float))
        assert total_amount > 0

        # Log detailed structure for debugging
        pretty_print(
            {
                "invoice_number": invoice_number,
                "customer_name": customer_name,
                "customer_email": customer_email,
                "num_line_items": len(line_items),
                "total_amount": total_amount,
            },
            title="Invoice Summary",
        )
