"""Every reader of a backend file agrees on what it declares and whether it is refused.

The loader, the document validator and the declared-model reader the kit's guards use read one file's shape
through one function, so none of them can disagree with another on a file declaring a twin.
"""

from pathlib import Path

import pytest

from pipelex.cogt.exceptions import InferenceBackendLibraryError
from pipelex.cogt.model_backends.model_spec_document import (
    DeclaredModelSpec,
    describe_model_spec_document_rejection,
    list_declared_model_specs,
)
from tests.unit.pipelex.cogt.model_backends.backend_file_handle_key_utils import (
    DUPLICATE_PAIR_FILE,
    EMPTY_HANDLES_FILE,
    HANDLE_IN_DEFAULTS_FILE,
    NON_STRING_HANDLE_FILE,
    TWIN_FILE,
    TYPE_FROM_BLUEPRINT_FILE,
    TYPE_FROM_DEFAULTS_FILE,
    load_backend_file,
    read_backend_document,
)


class TestEveryReaderAgrees:
    def test_the_declared_reader_names_each_table_with_its_handle_and_type(self, tmp_path: Path) -> None:
        declared = list_declared_model_specs(document=read_backend_document(tmp_path, model_specs_toml=TWIN_FILE))

        assert declared == [
            DeclaredModelSpec(table_name="gpt-6-luna", handle="gpt-6-luna", model_type="llm"),
            DeclaredModelSpec(table_name="gpt-6-luna-judgment", handle="gpt-6-luna", model_type="judgment"),
        ]

    @pytest.mark.parametrize(
        ("model_specs_toml", "is_accepted"),
        [
            pytest.param(TWIN_FILE, True, id="twin"),
            pytest.param(TYPE_FROM_DEFAULTS_FILE, True, id="type_from_defaults"),
            pytest.param(TYPE_FROM_BLUEPRINT_FILE, True, id="type_from_blueprint"),
            pytest.param(HANDLE_IN_DEFAULTS_FILE, False, id="handle_in_defaults"),
            pytest.param(DUPLICATE_PAIR_FILE, False, id="duplicate_pair"),
        ],
    )
    def test_the_document_validator_agrees_with_the_loader(self, tmp_path: Path, model_specs_toml: str, is_accepted: bool) -> None:
        rejection = describe_model_spec_document_rejection(document=read_backend_document(tmp_path, model_specs_toml=model_specs_toml))
        loader_error: InferenceBackendLibraryError | None = None
        try:
            load_backend_file(tmp_path, model_specs_toml=model_specs_toml)
        except InferenceBackendLibraryError as exc:
            loader_error = exc

        assert (rejection is None) is is_accepted, rejection
        assert (loader_error is None) is is_accepted, loader_error

    @pytest.mark.parametrize(
        "model_specs_toml",
        [
            pytest.param(NON_STRING_HANDLE_FILE, id="non_string_handle"),
            pytest.param(EMPTY_HANDLES_FILE, id="empty_handles"),
        ],
    )
    def test_an_invalid_handle_is_refused_for_its_value_and_never_as_a_duplicate(self, tmp_path: Path, model_specs_toml: str) -> None:
        """A handle the validation refuses can read as another table's handle once coerced: both readers name the bad value instead."""
        rejection = describe_model_spec_document_rejection(document=read_backend_document(tmp_path, model_specs_toml=model_specs_toml))
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            load_backend_file(tmp_path, model_specs_toml=model_specs_toml)

        assert rejection is not None
        assert "'gpt-6-luna'" in rejection
        assert "handle" in rejection
        assert "both declare" not in rejection
        assert "'gpt-6-luna'" in str(exc_info.value)
        assert "handle" in str(exc_info.value)
        assert "both declare" not in str(exc_info.value)
