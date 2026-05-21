import pytest
from pydantic import ValidationError

from pipelex.system.configuration.configs import ReportingConfig


class TestReportingConfigValidation:
    @pytest.mark.parametrize("invalid_scale", [0.0, -1.0, -0.0001])
    def test_cost_report_unit_scale_must_be_positive(self, invalid_scale: float):
        """cost_report_unit_scale must be > 0 to prevent ZeroDivisionError in cost formatting."""
        with pytest.raises(ValidationError):
            ReportingConfig(
                is_log_costs_to_console=False,
                is_generate_cost_report_file_enabled=False,
                cost_report_dir_path="reports",
                cost_report_base_name="cost_report",
                cost_report_extension="csv",
                cost_report_unit_scale=invalid_scale,
            )

    def test_cost_report_unit_scale_positive_value_accepted(self):
        config = ReportingConfig(
            is_log_costs_to_console=False,
            is_generate_cost_report_file_enabled=False,
            cost_report_dir_path="reports",
            cost_report_base_name="cost_report",
            cost_report_extension="csv",
            cost_report_unit_scale=1.0,
        )
        assert config.cost_report_unit_scale == 1.0
