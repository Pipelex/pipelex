"""A backend file declares a second model of one handle with the `handle` key.

A root table's name is its handle unless it sets `handle`, and TOML forbids declaring one table twice, so
`handle` is how one file says that `gpt-6-luna` is an LLM and a judgment model at once.
"""

from pathlib import Path

import pytest

from pipelex.cogt.exceptions import InferenceBackendLibraryError, InferenceBackendLibraryValidationError
from pipelex.cogt.model_backends.model_spec_document import (
    list_declared_model_specs,
)
from pipelex.cogt.model_backends.model_type import ModelType
from tests.helpers.backend_library_loading import required_backend
from tests.unit.pipelex.cogt.model_backends.backend_file_handle_key_utils import (
    DUPLICATE_PAIR_FILE,
    HANDLE_IN_DEFAULTS_FILE,
    TWIN_FILE,
    TYPE_FROM_BLUEPRINT_FILE,
    TYPE_FROM_DEFAULTS_FILE,
    load_backend_file,
    read_backend_document,
)


class TestTheHandleKey:
    def test_a_twin_declared_through_handle_loads_both_specs(self, tmp_path: Path) -> None:
        backend = required_backend(load_backend_file(tmp_path, model_specs_toml=TWIN_FILE))

        llm_spec = backend.get_model_spec(model_type=ModelType.LLM, handle="gpt-6-luna")
        judgment_spec = backend.get_model_spec(model_type=ModelType.JUDGMENT, handle="gpt-6-luna")
        assert llm_spec is not None
        assert judgment_spec is not None
        assert llm_spec.sdk == "openai_responses"
        assert judgment_spec.sdk == "openai_decisions"
        # The model id defaults to the handle the table serves, never to the table's own name.
        assert judgment_spec.model_id == "gpt-6-luna"
        assert backend.model_specs.all_handles() == ["gpt-6-luna"]

    def test_handle_in_defaults_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            load_backend_file(tmp_path, model_specs_toml=HANDLE_IN_DEFAULTS_FILE)

        assert "'handle'" in str(exc_info.value)
        assert "[defaults]" in str(exc_info.value)

    def test_a_duplicate_pair_is_refused_naming_both_tables(self, tmp_path: Path) -> None:
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            load_backend_file(tmp_path, model_specs_toml=DUPLICATE_PAIR_FILE)

        message = str(exc_info.value)
        assert "'gpt-6-luna'" in message
        assert "'gpt-6-luna-again'" in message
        assert "model type 'judgment'" in message

    def test_a_placeholder_may_not_stand_in_for_a_handle(self, tmp_path: Path) -> None:
        """A handle describes the model, which a boot without inference must know without resolving anything."""
        templated_file = TWIN_FILE.replace('handle = "gpt-6-luna"', 'handle = "${LUNA_HANDLE}"')

        with pytest.raises(InferenceBackendLibraryValidationError, match="'handle' references LUNA_HANDLE"):
            load_backend_file(tmp_path, model_specs_toml=templated_file)

    @pytest.mark.parametrize(
        ("model_specs_toml", "expected_pairs"),
        [
            pytest.param(TYPE_FROM_DEFAULTS_FILE, [(ModelType.LLM, "gpt-6-luna"), (ModelType.JUDGMENT, "gpt-6-luna")], id="table_then_defaults"),
            pytest.param(TYPE_FROM_BLUEPRINT_FILE, [(ModelType.LLM, "gpt-6-luna")], id="blueprint_default"),
        ],
    )
    def test_the_type_comes_from_the_table_then_the_defaults_then_the_blueprint(
        self, tmp_path: Path, model_specs_toml: str, expected_pairs: list[tuple[ModelType, str]]
    ) -> None:
        backend = required_backend(load_backend_file(tmp_path, model_specs_toml=model_specs_toml))
        loaded_pairs = sorted((spec.model_type, spec.name) for spec in backend.model_specs.all_specs())
        declared_pairs = sorted(
            (ModelType(declared.model_type), declared.handle)
            for declared in list_declared_model_specs(document=read_backend_document(tmp_path, model_specs_toml=model_specs_toml))
        )

        assert loaded_pairs == sorted(expected_pairs)
        assert declared_pairs == loaded_pairs
