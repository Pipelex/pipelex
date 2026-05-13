"""Test for PipeSequence with PipeLLM list output bug.

This test reproduces a bug where a PipeLLM with output like "Expense[]"
should produce ListContent, but when used inside a PipeSequence, the
subsequent step with batch_over fails because the content is not ListContent.

Error: "Content of 'expenses' is of type 'Expense', it should be 'ListContent'"
"""

import tempfile
from pathlib import Path
from typing import ClassVar

import pytest

from pipelex.hub import get_required_pipe
from pipelex.pipe_run.dry_run import dry_run_pipe
from pipelex.pipeline.validate_bundle import validate_bundle


class TestData:
    """Test data for pipe_sequence list output bug."""

    MTHDS_BUNDLE: ClassVar[str] = """
domain = "test_list_output"
description = "Test bundle for list output bug"

[concept.Item]
description = "A simple item"

[concept.Item.structure]
name = { type = "text", description = "Item name", required = true }

[concept.ProcessedItem]
description = "A processed item"

[concept.ProcessedItem.structure]
original_name = { type = "text", description = "Original name", required = true }
status = { type = "text", description = "Processing status", required = true }

# Main sequence that should fail
[pipe.main_sequence]
type = "PipeSequence"
description = "Main sequence that generates items and processes them"
inputs = { topic = "Text" }
output = "ProcessedItem[]"
steps = [
    { pipe = "generate_items", result = "items" },
    { pipe = "process_item", batch_over = "items", batch_as = "item", result = "processed_items" },
]

# PipeLLM that outputs a list - THIS IS THE KEY PIPE
[pipe.generate_items]
type = "PipeLLM"
description = "Generate multiple items"
inputs = { topic = "Text" }
output = "Item[]"
model = "$testing-text"
prompt = "Generate 3 items about: $topic"

# PipeLLM that processes a single item
[pipe.process_item]
type = "PipeLLM"
description = "Process a single item"
inputs = { item = "Item" }
output = "ProcessedItem"
model = "$testing-text"
prompt = "Process this item: $item"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestPipeSequenceListOutputBug:
    """Test that PipeLLM with list output produces ListContent in PipeSequence."""

    async def test_pipe_llm_list_output_produces_list_content_in_sequence(self):
        """Test that a PipeLLM with output="Item[]" produces ListContent when run in a PipeSequence.

        This test reproduces the bug where:
        1. generate_items (PipeLLM with output="Item[]") runs and should produce ListContent[Item]
        2. process_item with batch_over="items" expects ListContent
        3. But the content is a single Item, not ListContent, causing the error:
           "Content of 'items' is of type 'Item', it should be 'ListContent'"
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create the .mthds file
            mthds_file = temp_path / "test_bundle.mthds"
            mthds_file.write_text(TestData.MTHDS_BUNDLE)

            # Load the bundle
            result = await validate_bundle(
                mthds_file_path=mthds_file,
                library_dirs=[temp_path],
            )

            assert result is not None
            assert len(result.pipes) > 0

            # Get the main sequence pipe (without domain prefix since it's loaded into the library)
            main_sequence = get_required_pipe("main_sequence")

            # Run dry run - this should NOT fail
            # BUG: Currently fails with "Content of 'items' is of type 'Item', it should be 'ListContent'"
            dry_run_output = await dry_run_pipe(main_sequence, raise_on_failure=True)

            assert dry_run_output.status.name == "SUCCESS", f"Dry run failed: {dry_run_output.error_message}"

    async def test_standalone_pipe_llm_with_list_output(self):
        """Test that a standalone PipeLLM with output="Item[]" produces ListContent.

        This test verifies the basic case works - a PipeLLM with list output
        should produce ListContent when run standalone.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create the .mthds file
            mthds_file = temp_path / "test_bundle.mthds"
            mthds_file.write_text(TestData.MTHDS_BUNDLE)

            # Load the bundle
            await validate_bundle(
                mthds_file_path=mthds_file,
                library_dirs=[temp_path],
            )

            # Get the generate_items pipe (without domain prefix since it's loaded into the library)
            generate_items_pipe = get_required_pipe("generate_items")

            # Verify the pipe has the correct output multiplicity
            assert generate_items_pipe.output.multiplicity is True, (
                f"generate_items should have output multiplicity=True, got {generate_items_pipe.output.multiplicity}"
            )

            # Run dry run on the standalone pipe
            dry_run_output = await dry_run_pipe(generate_items_pipe, raise_on_failure=True)

            assert dry_run_output.status.name == "SUCCESS", f"Dry run of generate_items failed: {dry_run_output.error_message}"


class TestDataNested:
    """Test data for nested pipe_sequence list output bug."""

    MTHDS_BUNDLE: ClassVar[str] = """
domain = "test_nested_list_output"
description = "Test bundle for nested list output bug"

[concept.Employee]
description = "An employee"

[concept.Employee.structure]
name = { type = "text", description = "Employee name", required = true }

[concept.Expense]
description = "An expense"

[concept.Expense.structure]
description = { type = "text", description = "Expense description", required = true }
amount = { type = "number", description = "Amount", required = true }

[concept.ProcessedExpense]
description = "A processed expense"

[concept.ProcessedExpense.structure]
description = { type = "text", description = "Expense description", required = true }
status = { type = "text", description = "Processing status", required = true }

[concept.EmployeeReport]
description = "An employee report with processed expenses"

[concept.EmployeeReport.structure]
employee_name = { type = "text", description = "Employee name", required = true }
total_expenses = { type = "number", description = "Total expenses", required = true }

# Main pipeline - outer sequence
[pipe.generate_expense_dataset]
type = "PipeSequence"
description = "Main pipeline that generates expense data for multiple employees"
inputs = { nb_employees = "Number" }
output = "EmployeeReport[]"
steps = [
    { pipe = "generate_employees", result = "employees" },
    { pipe = "generate_employee_report", batch_over = "employees", batch_as = "employee", result = "reports" },
]

# Generate employees list
[pipe.generate_employees]
type = "PipeLLM"
description = "Generates employee profiles"
inputs = { nb_employees = "Number" }
output = "Employee[]"
model = "$testing-text"
prompt = "Generate $nb_employees employees"

# Inner sequence - THIS IS WHERE THE BUG OCCURS
[pipe.generate_employee_report]
type = "PipeSequence"
description = "Generates expenses with processing for a single employee"
inputs = { employee = "Employee" }
output = "EmployeeReport"
steps = [
    { pipe = "generate_expenses", result = "expenses" },
    { pipe = "process_expense", batch_over = "expenses", batch_as = "expense", result = "processed_expenses" },
    { pipe = "compose_report", result = "report" },
]

# PipeLLM that outputs Expense[] - THE KEY PIPE
[pipe.generate_expenses]
type = "PipeLLM"
description = "Generates multiple expenses for an employee"
inputs = { employee = "Employee" }
output = "Expense[]"
model = "$testing-text"
prompt = "Generate expenses for: $employee"

# Process single expense
[pipe.process_expense]
type = "PipeLLM"
description = "Process a single expense"
inputs = { expense = "Expense" }
output = "ProcessedExpense"
model = "$testing-text"
prompt = "Process expense: $expense"

# Compose final report
[pipe.compose_report]
type = "PipeLLM"
description = "Compose the final report"
inputs = { employee = "Employee", processed_expenses = "ProcessedExpense[]" }
output = "EmployeeReport"
model = "$testing-text"
prompt = "Create report for $employee with $processed_expenses"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestNestedPipeSequenceListOutputBug:
    """Test that PipeLLM with list output produces ListContent in nested PipeSequence."""

    async def test_nested_sequence_with_list_output_and_batch_over(self):
        """Test that a nested PipeSequence with PipeLLM list output and batch_over works.

        This test reproduces the user's exact scenario:
        1. Outer PipeSequence calls inner PipeSequence with batch_over
        2. Inner PipeSequence has a PipeLLM with output="Expense[]"
        3. Next step in inner sequence uses batch_over on the expenses
        4. Bug: "Content of 'expenses' is of type 'Expense', it should be 'ListContent'"
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create the .mthds file
            mthds_file = temp_path / "test_bundle.mthds"
            mthds_file.write_text(TestDataNested.MTHDS_BUNDLE)

            # Load the bundle
            result = await validate_bundle(
                mthds_file_path=mthds_file,
                library_dirs=[temp_path],
            )

            assert result is not None
            assert len(result.pipes) > 0

            # Get the main sequence pipe
            main_sequence = get_required_pipe("generate_expense_dataset")

            # Run dry run - this should NOT fail
            # BUG: Currently may fail with "Content of 'expenses' is of type 'Expense', it should be 'ListContent'"
            dry_run_output = await dry_run_pipe(main_sequence, raise_on_failure=True)

            assert dry_run_output.status.name == "SUCCESS", f"Dry run failed: {dry_run_output.error_message}"

    async def test_inner_sequence_directly(self):
        """Test the inner sequence directly to isolate the bug."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create the .mthds file
            mthds_file = temp_path / "test_bundle.mthds"
            mthds_file.write_text(TestDataNested.MTHDS_BUNDLE)

            # Load the bundle
            await validate_bundle(
                mthds_file_path=mthds_file,
                library_dirs=[temp_path],
            )

            # Get the inner sequence pipe
            inner_sequence = get_required_pipe("generate_employee_report")

            # Run dry run on the inner sequence
            dry_run_output = await dry_run_pipe(inner_sequence, raise_on_failure=True)

            assert dry_run_output.status.name == "SUCCESS", f"Dry run of inner sequence failed: {dry_run_output.error_message}"
