import csv
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.llm.llm_report import LLMTokenCostReportField, LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.pipeline.pipeline_models import SpecialPipelineId


class TestCostRegistry:
    """Test CostRegistry methods without pandas dependency."""

    def test_to_records(self):
        """Test conversion from CostRegistry to list of flat dictionaries."""
        # Create a simple cost report
        job_metadata = JobMetadata(pipeline_run_id=SpecialPipelineId.UNTITLED)
        llm_tokens_usage = LLMTokensUsage(
            job_metadata=job_metadata,
            inference_model_name="test-model",
            inference_model_id="test-model-id",
            nb_tokens_by_category={
                TokenCategory.INPUT: 100,
                TokenCategory.OUTPUT: 50,
            },
            unit_costs={
                CostCategory.INPUT: 1000,  # $1 per million tokens
                CostCategory.OUTPUT: 2000,  # $2 per million tokens
            },
        )

        cost_report = CostRegistry.complete_cost_report(llm_tokens_usage=llm_tokens_usage)
        cost_registry = CostRegistry(root=[cost_report])

        # Convert to records
        records = cost_registry.to_records()

        # Verify result structure
        assert isinstance(records, list)
        assert len(records) == 1
        assert isinstance(records[0], dict)

        # Verify actual values in the record
        record = records[0]
        assert record[LLMTokenCostReportField.LLM_NAME] == "test-model"
        assert record[LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED] == 100
        assert record[LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED] == 0
        assert record[LLMTokenCostReportField.NB_TOKENS_INPUT_JOINED] == 100
        assert record[LLMTokenCostReportField.NB_TOKENS_OUTPUT] == 50
        assert record[LLMTokenCostReportField.COST_INPUT_NON_CACHED] == 0.1  # 100 * 0.001
        assert record[LLMTokenCostReportField.COST_INPUT_CACHED] == 0.0
        assert record[LLMTokenCostReportField.COST_INPUT_JOINED] == 0.1
        assert record[LLMTokenCostReportField.COST_OUTPUT] == 0.1  # 50 * 0.002

    def test_save_to_csv(self, tmp_path: Path):
        """Test CSV file creation with correct headers and data."""
        # Prepare test data
        records: list[dict[str, Any]] = [
            {
                LLMTokenCostReportField.LLM_NAME: "model-1",
                LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED: 50,
                LLMTokenCostReportField.COST_INPUT_CACHED: 0.05,
            },
            {
                LLMTokenCostReportField.LLM_NAME: "model-2",
                LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED: 100,
                LLMTokenCostReportField.COST_INPUT_CACHED: 0.10,
            },
        ]

        # Save to CSV
        csv_file = tmp_path / "test_report.csv"
        CostRegistry.save_to_csv(records, str(csv_file))

        # Verify file exists
        assert csv_file.exists()

        # Read and verify contents using csv module
        with open(csv_file, encoding="utf-8") as file:
            reader = csv.DictReader(file)
            rows = list(reader)

        # Verify we have 2 data rows
        assert len(rows) == 2

        # Check first row values
        assert rows[0][LLMTokenCostReportField.LLM_NAME] == "model-1"
        assert rows[0][LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED] == "50"
        assert rows[0][LLMTokenCostReportField.COST_INPUT_CACHED] == "0.05"

        # Check second row values
        assert rows[1][LLMTokenCostReportField.LLM_NAME] == "model-2"
        assert rows[1][LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED] == "100"
        assert rows[1][LLMTokenCostReportField.COST_INPUT_CACHED] == "0.1"

    def test_save_to_csv_empty_records(self, tmp_path: Path):
        """Test that save_to_csv handles empty records gracefully."""
        csv_file = tmp_path / "empty_report.csv"
        CostRegistry.save_to_csv([], str(csv_file))

        # File should not be created for empty records
        assert not csv_file.exists()

    def test_save_to_csv_with_varying_fields(self, tmp_path: Path):
        """Test that save_to_csv handles records with different fields correctly.

        This test ensures the bug where different records have different fields
        (e.g., some with output_audio, output_reasoning tokens) is caught.
        """
        # Prepare test data with varying fields across records
        records: list[dict[str, Any]] = [
            {
                LLMTokenCostReportField.LLM_NAME: "model-standard",
                LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED: 100,
                LLMTokenCostReportField.COST_INPUT_CACHED: 0.10,
            },
            {
                LLMTokenCostReportField.LLM_NAME: "model-with-audio",
                LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED: 50,
                LLMTokenCostReportField.COST_INPUT_CACHED: 0.05,
                "nb_tokens_output_audio": 200,  # Extra field not in first record
                "cost_output_audio": 0.20,  # Extra field not in first record
            },
            {
                LLMTokenCostReportField.LLM_NAME: "model-with-reasoning",
                LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED: 75,
                LLMTokenCostReportField.COST_INPUT_CACHED: 0.075,
                "nb_tokens_output_reasoning": 150,  # Extra field not in other records
                "cost_output_reasoning": 0.15,  # Extra field not in other records
            },
        ]

        # Save to CSV - should handle varying fields without errors
        csv_file = tmp_path / "varying_fields_report.csv"
        CostRegistry.save_to_csv(records, str(csv_file))

        # Verify file exists
        assert csv_file.exists()

        # Read and verify all fields are present in headers
        with open(csv_file, encoding="utf-8") as file:
            reader = csv.DictReader(file)
            rows = list(reader)

        # Should have 3 rows
        assert len(rows) == 3

        # Verify all fields are in the CSV (even if some rows have empty values)
        assert LLMTokenCostReportField.LLM_NAME in rows[0]
        assert LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED in rows[0]
        assert "nb_tokens_output_audio" in rows[0]
        assert "nb_tokens_output_reasoning" in rows[0]
        assert "cost_output_audio" in rows[0]
        assert "cost_output_reasoning" in rows[0]

        # Verify first row values (should have empty strings for missing fields)
        assert rows[0][LLMTokenCostReportField.LLM_NAME] == "model-standard"
        assert rows[0][LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED] == "100"
        assert rows[0]["nb_tokens_output_audio"] == ""  # Missing field = empty string
        assert rows[0]["nb_tokens_output_reasoning"] == ""  # Missing field = empty string

        # Verify second row has its extra field
        assert rows[1][LLMTokenCostReportField.LLM_NAME] == "model-with-audio"
        assert rows[1]["nb_tokens_output_audio"] == "200"
        assert rows[1]["cost_output_audio"] == "0.2"

        # Verify third row has its extra field
        assert rows[2][LLMTokenCostReportField.LLM_NAME] == "model-with-reasoning"
        assert rows[2]["nb_tokens_output_reasoning"] == "150"
        assert rows[2]["cost_output_reasoning"] == "0.15"

    def test_generate_report_aggregation(self, mocker: MockerFixture, tmp_path: Path):
        """Test groupby logic and cost calculations are correct."""
        # Mock console output to avoid printing during tests
        mock_console = mocker.patch("pipelex.cogt.usage.cost_registry.Console")

        # Create test data with multiple LLM usages
        job_metadata = JobMetadata(pipeline_run_id="test-pipeline")

        llm_tokens_usages = [
            # First usage of model-a: 100 input (20 cached), 50 output
            LLMTokensUsage(
                job_metadata=job_metadata,
                inference_model_name="model-a",
                inference_model_id="model-a-id",
                nb_tokens_by_category={
                    TokenCategory.INPUT: 100,
                    TokenCategory.OUTPUT: 50,
                    TokenCategory.INPUT_CACHED: 20,
                },
                unit_costs={
                    CostCategory.INPUT: 1000,  # $1 per million tokens
                    CostCategory.INPUT_CACHED: 500,  # $0.50 per million tokens
                    CostCategory.OUTPUT: 2000,  # $2 per million tokens
                },
            ),
            # Second usage of model-a: 200 input (50 cached), 100 output
            LLMTokensUsage(
                job_metadata=job_metadata,
                inference_model_name="model-a",
                inference_model_id="model-a-id",
                nb_tokens_by_category={
                    TokenCategory.INPUT: 200,
                    TokenCategory.OUTPUT: 100,
                    TokenCategory.INPUT_CACHED: 50,
                },
                unit_costs={
                    CostCategory.INPUT: 1000,  # $1 per million tokens
                    CostCategory.INPUT_CACHED: 500,  # $0.50 per million tokens
                    CostCategory.OUTPUT: 2000,  # $2 per million tokens
                },
            ),
            # First usage of model-b: 150 input (30 cached), 75 output
            LLMTokensUsage(
                job_metadata=job_metadata,
                inference_model_name="model-b",
                inference_model_id="model-b-id",
                nb_tokens_by_category={
                    TokenCategory.INPUT: 150,
                    TokenCategory.OUTPUT: 75,
                    TokenCategory.INPUT_CACHED: 30,
                },
                unit_costs={
                    CostCategory.INPUT: 1000,  # $1 per million tokens
                    CostCategory.INPUT_CACHED: 500,  # $0.50 per million tokens
                    CostCategory.OUTPUT: 2000,  # $2 per million tokens
                },
            ),
        ]

        # Save to CSV to verify aggregation logic
        csv_file = tmp_path / "aggregation_test.csv"
        CostRegistry.generate_report(
            pipeline_run_id="test-pipeline",
            llm_tokens_usages=llm_tokens_usages,
            unit_scale=1.0,
            cost_report_file_path=str(csv_file),
        )

        # Verify console was called to print table
        mock_console.assert_called_once()
        mock_instance = mock_console.return_value
        mock_instance.print.assert_called_once()

        # Read the CSV and verify aggregation
        with open(csv_file, encoding="utf-8") as file:
            reader = csv.DictReader(file)
            rows = list(reader)

        # Should have 3 rows (one per usage, before aggregation by model)
        assert len(rows) == 3

        # Manually calculate expected aggregations for model-a:
        # Usage 1: 80 non-cached (100-20), 20 cached, 50 output
        # Usage 2: 150 non-cached (200-50), 50 cached, 100 output
        # Total model-a: 230 non-cached, 70 cached, 300 joined, 150 output
        # Costs: 0.23 non-cached, 0.035 cached, 0.265 joined, 0.3 output

        # Manually calculate expected aggregations for model-b:
        # Usage 1: 120 non-cached (150-30), 30 cached, 75 output
        # Costs: 0.12 non-cached, 0.015 cached, 0.135 joined, 0.15 output

        # Verify individual records contain expected values
        model_a_rows = [row for row in rows if row[LLMTokenCostReportField.LLM_NAME] == "model-a"]
        model_b_rows = [row for row in rows if row[LLMTokenCostReportField.LLM_NAME] == "model-b"]

        assert len(model_a_rows) == 2
        assert len(model_b_rows) == 1

        # Verify first model-a record
        assert int(model_a_rows[0][LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED]) == 80
        assert int(model_a_rows[0][LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED]) == 20
        assert int(model_a_rows[0][LLMTokenCostReportField.NB_TOKENS_OUTPUT]) == 50
        assert float(model_a_rows[0][LLMTokenCostReportField.COST_INPUT_NON_CACHED]) == 0.08
        assert float(model_a_rows[0][LLMTokenCostReportField.COST_INPUT_CACHED]) == 0.01
        assert float(model_a_rows[0][LLMTokenCostReportField.COST_OUTPUT]) == 0.1

    def test_generate_report_with_empty_data(self, mocker: MockerFixture):
        """Test proper handling when no usage data."""
        # Mock logging
        mock_log_warning = mocker.patch("pipelex.cogt.usage.cost_registry.log.warning")
        mock_log_verbose = mocker.patch("pipelex.cogt.usage.cost_registry.log.verbose")

        # Test with non-untitled pipeline
        CostRegistry.generate_report(
            pipeline_run_id="test-pipeline",
            llm_tokens_usages=[],
            unit_scale=1.0,
            cost_report_file_path=None,
        )
        mock_log_warning.assert_called_once()

        # Test with untitled pipeline
        CostRegistry.generate_report(
            pipeline_run_id="untitled",
            llm_tokens_usages=[],
            unit_scale=1.0,
            cost_report_file_path=None,
        )
        mock_log_verbose.assert_called_once()

    def test_generate_report_with_file_output(self, tmp_path: Path, mocker: MockerFixture):
        """Test that CSV file is created when file path is provided."""
        # Mock console output
        mocker.patch("pipelex.cogt.usage.cost_registry.Console")

        # Create test data
        job_metadata = JobMetadata(pipeline_run_id="test-pipeline")
        llm_tokens_usage = LLMTokensUsage(
            job_metadata=job_metadata,
            inference_model_name="test-model",
            inference_model_id="test-model-id",
            nb_tokens_by_category={
                TokenCategory.INPUT: 100,
                TokenCategory.OUTPUT: 50,
                TokenCategory.INPUT_CACHED: 20,
            },
            unit_costs={
                CostCategory.INPUT: 1000,  # $1 per million tokens
                CostCategory.INPUT_CACHED: 500,  # $0.50 per million tokens
                CostCategory.OUTPUT: 2000,  # $2 per million tokens
            },
        )

        # Generate report with file output
        csv_file = tmp_path / "cost_report.csv"
        CostRegistry.generate_report(
            pipeline_run_id="test-pipeline",
            llm_tokens_usages=[llm_tokens_usage],
            unit_scale=1.0,
            cost_report_file_path=str(csv_file),
        )

        # Verify CSV file was created
        assert csv_file.exists()

        # Verify CSV has content with actual values
        with open(csv_file, encoding="utf-8") as file:
            reader = csv.DictReader(file)
            rows = list(reader)

        # Should have exactly 1 data row
        assert len(rows) == 1

        # Verify the actual values
        row = rows[0]
        assert row[LLMTokenCostReportField.LLM_NAME] == "test-model"
        assert int(row[LLMTokenCostReportField.NB_TOKENS_INPUT_NON_CACHED]) == 80  # 100 - 20
        assert int(row[LLMTokenCostReportField.NB_TOKENS_INPUT_CACHED]) == 20
        assert int(row[LLMTokenCostReportField.NB_TOKENS_INPUT_JOINED]) == 100
        assert int(row[LLMTokenCostReportField.NB_TOKENS_OUTPUT]) == 50
        assert float(row[LLMTokenCostReportField.COST_INPUT_NON_CACHED]) == 0.08  # 80 * 0.001
        assert float(row[LLMTokenCostReportField.COST_INPUT_CACHED]) == 0.01  # 20 * 0.0005
        assert float(row[LLMTokenCostReportField.COST_INPUT_JOINED]) == 0.09  # 0.08 + 0.01
        assert float(row[LLMTokenCostReportField.COST_OUTPUT]) == 0.1  # 50 * 0.002

    @pytest.mark.parametrize(
        ("unit_scale", "expected_scaled_cost"),
        [
            (1.0, 0.08),  # No scaling: 80 * (1000/1M) = 0.08
            (1000.0, 0.00008),  # Scale to thousands: 0.08 / 1000
            (0.01, 8.0),  # Scale by 0.01: 0.08 / 0.01
        ],
    )
    def test_generate_report_unit_scaling(self, unit_scale: float, expected_scaled_cost: float, mocker: MockerFixture):
        """Test that unit scaling is applied correctly to cost display."""
        # Mock console to avoid output during tests
        mocker.patch("pipelex.cogt.usage.cost_registry.Console")
        mock_table_class = mocker.patch("pipelex.cogt.usage.cost_registry.Table")
        mock_table = mock_table_class.return_value

        # Create test data
        job_metadata = JobMetadata(pipeline_run_id="test-pipeline")
        llm_tokens_usage = LLMTokensUsage(
            job_metadata=job_metadata,
            inference_model_name="test-model",
            inference_model_id="test-model-id",
            nb_tokens_by_category={
                TokenCategory.INPUT: 100,
                TokenCategory.OUTPUT: 50,
                TokenCategory.INPUT_CACHED: 20,
            },
            unit_costs={
                CostCategory.INPUT: 1000,  # $1 per million tokens
                CostCategory.INPUT_CACHED: 500,  # $0.50 per million tokens
                CostCategory.OUTPUT: 2000,  # $2 per million tokens
            },
        )

        # Generate report
        CostRegistry.generate_report(
            pipeline_run_id="test-pipeline",
            llm_tokens_usages=[llm_tokens_usage],
            unit_scale=unit_scale,
            cost_report_file_path=None,
        )

        # Verify table was created and printed
        mock_table_class.assert_called_once()

        # Check that add_row was called with scaled values
        # The actual cost for input_non_cached is 0.08 (80 tokens * 0.001)
        # It should be divided by unit_scale when displayed
        add_row_calls = mock_table.add_row.call_args_list

        # Find the data row (not the total row which has style="bold")
        data_row_call = None
        for call in add_row_calls:
            # Data row has no style keyword argument or style != "bold"
            kwargs: dict[str, Any] = call[1] if len(call) > 1 else {}
            if kwargs.get("style") != "bold":
                data_row_call = call
                break

        assert data_row_call is not None, "Could not find data row call"

        # Extract the cost value from the formatted string (6th argument, index 6)
        # Columns: Model, Input Cached tokens, Input Non Cached tokens, Input Joined tokens, Output tokens,
        #          Input Cached Cost (5), Input Non Cached Cost (6), Input Joined Cost (7), Output Cost (8), Total Cost (9)
        args: tuple[Any, ...] = data_row_call[0]
        cost_str: str = str(args[6])  # Input Non Cached Cost column

        # Extract the numeric value and verify it matches expected scaled cost
        actual_cost = float(cost_str)
        assert abs(actual_cost - expected_scaled_cost) < 0.0001

    def test_compute_total_cost(self):
        """Test total cost computation."""
        total = CostRegistry.compute_total_cost(
            input_non_cached_cost=1.0,
            input_cached_cost=0.5,
            output_cost=2.0,
        )
        assert total == 3.5
