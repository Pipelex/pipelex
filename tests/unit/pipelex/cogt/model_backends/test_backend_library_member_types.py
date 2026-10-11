"""A model or backend member written as a value of the wrong type is a validation error naming the model, the backend and the file.

Each of these used to crash the load with a bare `AttributeError` or `TypeError` that named nothing, or to
be accepted silently, because the members were converted by hand before pydantic had checked their type.
"""

from pathlib import Path

import pytest

from pipelex.cogt.exceptions import InferenceBackendLibraryError, InferenceBackendLibraryValidationError
from pipelex.cogt.img_gen.img_gen_model_rules import ImgGenArgTopic
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from tests.helpers.backend_library_loading import BOTH_MODES, load_library, required_backend
from tests.unit.pipelex.cogt.model_backends.test_data import BackendLibraryTomls


class TestAMemberOfTheWrongTypeIsRefusedCleanly:
    @pytest.mark.parametrize("credentials", BOTH_MODES)
    @pytest.mark.parametrize(
        ("member_line", "field_name", "expected_fragment"),
        [
            pytest.param('costs = "free"', "costs", "Input should be a valid dictionary", id="costs_as_a_string"),
            pytest.param("costs = 1979-05-27", "costs", "Input should be a valid dictionary", id="costs_as_a_date"),
            pytest.param('costs = { input = "free" }', "costs.input", "Input should be a valid number", id="costs_with_a_string_price"),
            pytest.param("costs = { input = nan }", "costs", "must be finite and not negative", id="costs_with_a_nan_price"),
            pytest.param("costs = { input = inf }", "costs", "must be finite and not negative", id="costs_with_an_infinite_price"),
            pytest.param("costs = { input = -1.5 }", "costs", "must be finite and not negative", id="costs_with_a_negative_price"),
            pytest.param(
                "costs = { inptu = 1.5 }",
                "costs.inptu",
                "invalid enum value 'inptu', expected 'input', 'input_cached',",
                id="costs_with_an_unknown_category",
            ),
            pytest.param("listed_constraints = 1979-05-27", "listed_constraints", "Input should be a valid list", id="listed_constraints_as_a_date"),
            pytest.param('listed_constraints = "abc"', "listed_constraints", "Input should be a valid list", id="listed_constraints_as_a_string"),
            pytest.param(
                "listed_constraints = { temperature_unsupported = true }",
                "listed_constraints",
                "Input should be a valid list",
                id="listed_constraints_as_a_table",
            ),
            pytest.param('valued_constraints = "x"', "valued_constraints", "Input should be a valid dictionary", id="valued_constraints_as_a_string"),
            pytest.param("valued_constraints = []", "valued_constraints", "Input should be a valid dictionary", id="valued_constraints_as_an_array"),
            pytest.param("rules = 1979-05-27", "rules", "Input should be a valid dictionary", id="rules_as_a_date"),
            pytest.param('rules = "x"', "rules", "Input should be a valid dictionary", id="rules_as_a_string"),
        ],
    )
    def test_a_model_member_of_the_wrong_type_is_refused_naming_the_model(
        self, tmp_path: Path, credentials: CredentialResolution, member_line: str, field_name: str, expected_fragment: str
    ) -> None:
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            load_library(
                tmp_path,
                backends_toml=BackendLibraryTomls.BACKENDS_TOML,
                model_specs_toml=BackendLibraryTomls.model_specs_toml_with_member(member_line=member_line),
                credentials=credentials,
            )

        message = str(exc_info.value)
        assert "Invalid inference model spec 'acme-one' for backend 'acme'" in message
        assert "acme.toml" in message
        assert field_name in message
        assert expected_fragment in message

    def test_members_written_as_the_kit_files_write_them_still_load_as_enums(self, tmp_path: Path) -> None:
        """The control: strings naming enum members are converted to the enums, and a model may leave `costs` out."""
        library = load_library(
            tmp_path,
            backends_toml=BackendLibraryTomls.backends_toml_with_member(member_line="valued_constraints = { min_thinking_budget = 1024 }"),
            model_specs_toml=BackendLibraryTomls.model_specs_toml_with_member(
                member_line=(
                    'listed_constraints = ["temperature_unsupported"]\n'
                    "valued_constraints = { fixed_temperature = 1 }\n"
                    "costs = { input = 1.5, output = 0 }\n"
                    'rules = { prompt = "positive_only" }'
                )
            ),
            credentials=CredentialResolution.REQUIRE,
        )

        model_spec = required_backend(library).get_model_spec(model_type=ModelType.LLM, handle="acme-one")
        assert model_spec is not None
        assert model_spec.listed_constraints == [ListedConstraint.TEMPERATURE_UNSUPPORTED]
        assert model_spec.valued_constraints == {ValuedConstraint.MIN_THINKING_BUDGET: 1024, ValuedConstraint.FIXED_TEMPERATURE: 1}
        assert model_spec.costs == {CostCategory.INPUT: 1.5, CostCategory.OUTPUT: 0}
        assert model_spec.rules == {ImgGenArgTopic.PROMPT: "positive_only"}
        assert all(type(key) is ValuedConstraint for key in model_spec.valued_constraints)
        assert all(type(key) is CostCategory for key in model_spec.costs)
        assert model_spec.rules is not None
        assert all(type(key) is ImgGenArgTopic for key in model_spec.rules)

    def test_a_model_may_leave_costs_out(self, tmp_path: Path) -> None:
        library = load_library(
            tmp_path,
            backends_toml=BackendLibraryTomls.BACKENDS_TOML,
            model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML,
            credentials=CredentialResolution.REQUIRE,
        )

        model_spec = required_backend(library).get_model_spec(model_type=ModelType.LLM, handle="acme-one")
        assert model_spec is not None
        assert model_spec.costs == {}

    @pytest.mark.parametrize("credentials", BOTH_MODES)
    @pytest.mark.parametrize(
        ("member_line", "field_name", "expected_fragment"),
        [
            pytest.param("listed_constraints = 1979-05-27", "listed_constraints", "Input should be a valid list", id="listed_constraints_as_a_date"),
            pytest.param(
                "listed_constraints = { temperature_unsupported = true }",
                "listed_constraints",
                "Input should be a valid list",
                id="listed_constraints_as_a_table",
            ),
            pytest.param('valued_constraints = "x"', "valued_constraints", "Input should be a valid dictionary", id="valued_constraints_as_a_string"),
        ],
    )
    def test_a_backend_member_of_the_wrong_type_is_refused_naming_the_backend(
        self, tmp_path: Path, credentials: CredentialResolution, member_line: str, field_name: str, expected_fragment: str
    ) -> None:
        with pytest.raises(InferenceBackendLibraryValidationError) as exc_info:
            load_library(
                tmp_path,
                backends_toml=BackendLibraryTomls.backends_toml_with_member(member_line=member_line),
                model_specs_toml=BackendLibraryTomls.MODEL_SPECS_TOML,
                credentials=credentials,
            )

        message = str(exc_info.value)
        assert "Invalid inference backend 'acme'" in message
        assert field_name in message
        assert expected_fragment in message
