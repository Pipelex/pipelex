import pytest

from tests.unit.builder.pipe.test_data_inputs import InputRequirementTestCases


class TestInputRequirementBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "input_spec", "expected_string"),
        InputRequirementTestCases.TEST_CASES,
    )
    def test_input_requirement_spec_to_string(
        self,
        test_name: str,  # noqa: ARG002
        input_spec: str,
        expected_string: str,
    ):
        # Now inputs are just strings, so we test that they match
        assert input_spec == expected_string
