"""The one rule of a run id, `validate_pipeline_run_id`, and `RunMetadata` applying it at construction.

A run id names the run's storage scope, its library, its URL and its workflow, so it holds the characters of a storage
scope segment alone, and never a reserved `SpecialPipelineId`, which would silently skip the run's cost report.
"""

import pytest
from pydantic import ValidationError

from pipelex.system.exceptions import RunParameterError
from pipelex.system.job_metadata import PIPELINE_RUN_ID_MAX_LENGTH, RunMetadata, SpecialPipelineId, validate_pipeline_run_id

# Fixed values, never minted at import: pytest-xdist workers must collect the same parametrized ids.
_A_UUID4 = "3f2b8c1e-9d4a-4e7b-8c5f-1a2b3c4d5e6f"

_GOOD_RUN_IDS = [
    _A_UUID4,  # the runtime's own minted id
    f"run_{_A_UUID4}",  # the hosted platform's id
    f"dry_run_{_A_UUID4}",  # a bundle validation's dry run
    f"dry_validate_{_A_UUID4}",
    "x" * PIPELINE_RUN_ID_MAX_LENGTH,  # at the limit
]

_MALFORMED_RUN_IDS = [
    "",  # empty
    "run/7",  # a slash, which splits a storage scope segment and a URL path
    "run.7",  # a dot
    "../escape",  # a traversal
    "run 7",  # a space
    "run\n7",  # a newline, which forges a log line
    "run_7\n",  # a final newline, which a `$` anchor would admit
    "rün_7",  # a non-ASCII letter
]


class TestPipelineRunIdRule:
    @pytest.mark.parametrize("run_id", _GOOD_RUN_IDS)
    def test_every_minted_shape_is_accepted(self, run_id: str) -> None:
        assert validate_pipeline_run_id(value=run_id) == run_id

    @pytest.mark.parametrize("run_id", _MALFORMED_RUN_IDS)
    def test_a_malformed_id_is_refused_naming_the_rule(self, run_id: str) -> None:
        with pytest.raises(RunParameterError, match="Invalid pipeline_run_id: expected one or more ASCII letters, digits"):
            validate_pipeline_run_id(value=run_id)

    def test_a_too_long_id_is_refused_naming_the_limit(self) -> None:
        with pytest.raises(RunParameterError, match=f"at most {PIPELINE_RUN_ID_MAX_LENGTH} are allowed"):
            validate_pipeline_run_id(value="x" * (PIPELINE_RUN_ID_MAX_LENGTH + 1))

    @pytest.mark.parametrize("reserved_id", list(SpecialPipelineId))
    def test_a_reserved_id_is_refused(self, reserved_id: SpecialPipelineId) -> None:
        with pytest.raises(RunParameterError, match="is reserved for runs that have no id of their own"):
            validate_pipeline_run_id(value=reserved_id)

    def test_the_refusal_is_a_value_error(self) -> None:
        """Pydantic turns only a `ValueError` into a validation error, and a host catches the same class."""
        with pytest.raises(ValueError, match="Invalid pipeline_run_id"):
            validate_pipeline_run_id(value="run/7")

    @pytest.mark.parametrize("run_id", _GOOD_RUN_IDS)
    def test_run_metadata_keeps_a_well_formed_id(self, run_id: str) -> None:
        run_metadata = RunMetadata(user_id="u", pipeline_run_id=run_id, storage_scope="test/scope", read_scope=None)
        assert run_metadata.pipeline_run_id == run_id

    @pytest.mark.parametrize("run_id", [*_MALFORMED_RUN_IDS, "x" * (PIPELINE_RUN_ID_MAX_LENGTH + 1), *list(SpecialPipelineId)])
    def test_run_metadata_refuses_a_malformed_id_at_construction(self, run_id: str) -> None:
        with pytest.raises(ValidationError, match="Invalid pipeline_run_id"):
            RunMetadata(user_id="u", pipeline_run_id=run_id, storage_scope="test/scope", read_scope=None)

    def test_run_metadata_refuses_it_again_on_deserialization(self) -> None:
        """A run's metadata crosses a process boundary as JSON: the rule holds on the other side too."""
        dumped = RunMetadata(user_id="u", pipeline_run_id="run_7", storage_scope="test/scope", read_scope=None).model_dump(mode="json")
        dumped["pipeline_run_id"] = "run/7"
        with pytest.raises(ValidationError, match="Invalid pipeline_run_id"):
            RunMetadata.model_validate(dumped)
