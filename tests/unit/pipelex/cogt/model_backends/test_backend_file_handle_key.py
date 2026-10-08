"""A backend file declares a second model of one handle with the `handle` key, and every reader of the file agrees.

A root table's name is its handle unless it sets `handle`, and TOML forbids declaring one table twice, so
`handle` is how one file says that `gpt-6-luna` is an LLM and a judgment model at once. The loader, the
document validator and the declared-model reader the kit's guards use must give the same answer on every
such file: what it declares, and whether it is refused.
"""

from pathlib import Path
from typing import Any

import pytest

from pipelex.cogt.exceptions import InferenceBackendLibraryError, InferenceBackendLibraryValidationError
from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.cogt.model_backends.model_spec_document import (
    DeclaredModelSpec,
    describe_model_spec_document_rejection,
    list_declared_model_specs,
)
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.tools.misc.toml_utils import load_toml_from_path
from tests.helpers.backend_library_loading import load_library, required_backend
from tests.unit.pipelex.cogt.model_backends.test_data import BackendLibraryTomls

TWIN_FILE = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["gpt-6-luna"]
inputs = ["text"]
outputs = ["text"]

["gpt-6-luna-judgment"]
handle = "gpt-6-luna"
model_type = "judgment"
sdk = "openai_decisions"
inputs = ["text"]
outputs = ["judgments"]
"""

HANDLE_IN_DEFAULTS_FILE = """
[defaults]
sdk = "openai_responses"
handle = "everything"

["gpt-6-luna"]
"""

DUPLICATE_PAIR_FILE = """
[defaults]
sdk = "openai_responses"

["gpt-6-luna"]
model_type = "judgment"

["gpt-6-luna-again"]
handle = "gpt-6-luna"
model_type = "judgment"
"""

# The table leaves its type to `[defaults]`, the twin sets its own, and a file setting none at all gets the default type.
TYPE_FROM_DEFAULTS_FILE = """
[defaults]
model_type = "judgment"
sdk = "openai_decisions"

["gpt-6-luna"]

["gpt-6-luna-llm"]
handle = "gpt-6-luna"
model_type = "llm"
sdk = "openai_responses"
"""

TYPE_FROM_BLUEPRINT_FILE = """
[defaults]
sdk = "openai_responses"

["gpt-6-luna"]
"""


def _load(tmp_path: Path, *, model_specs_toml: str) -> Any:
    return load_library(
        tmp_path, backends_toml=BackendLibraryTomls.BACKENDS_TOML, model_specs_toml=model_specs_toml, credentials=CredentialResolution.REQUIRE
    )


def _document(tmp_path: Path, *, model_specs_toml: str) -> dict[str, Any]:
    document_path = tmp_path / "document.toml"
    document_path.write_text(model_specs_toml, encoding="utf-8")
    return load_toml_from_path(str(document_path))


class TestTheHandleKey:
    def test_a_twin_declared_through_handle_loads_both_specs(self, tmp_path: Path) -> None:
        backend = required_backend(_load(tmp_path, model_specs_toml=TWIN_FILE))

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
            _load(tmp_path, model_specs_toml=HANDLE_IN_DEFAULTS_FILE)

        assert "'handle'" in str(exc_info.value)
        assert "[defaults]" in str(exc_info.value)

    def test_a_duplicate_pair_is_refused_naming_both_tables(self, tmp_path: Path) -> None:
        with pytest.raises(InferenceBackendLibraryError) as exc_info:
            _load(tmp_path, model_specs_toml=DUPLICATE_PAIR_FILE)

        message = str(exc_info.value)
        assert "'gpt-6-luna'" in message
        assert "'gpt-6-luna-again'" in message
        assert "model type 'judgment'" in message

    def test_a_placeholder_may_not_stand_in_for_a_handle(self, tmp_path: Path) -> None:
        """A handle describes the model, which a boot without inference must know without resolving anything."""
        templated_file = TWIN_FILE.replace('handle = "gpt-6-luna"', 'handle = "${LUNA_HANDLE}"')

        with pytest.raises(InferenceBackendLibraryValidationError, match="'handle' references LUNA_HANDLE"):
            _load(tmp_path, model_specs_toml=templated_file)

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
        backend = required_backend(_load(tmp_path, model_specs_toml=model_specs_toml))
        loaded_pairs = sorted((spec.model_type, spec.name) for spec in backend.model_specs.all_specs())
        declared_pairs = sorted(
            (ModelType(declared.model_type), declared.handle)
            for declared in list_declared_model_specs(document=_document(tmp_path, model_specs_toml=model_specs_toml))
        )

        assert loaded_pairs == sorted(expected_pairs)
        assert declared_pairs == loaded_pairs


class TestEveryReaderAgrees:
    def test_the_declared_reader_names_each_table_with_its_handle_and_type(self, tmp_path: Path) -> None:
        declared = list_declared_model_specs(document=_document(tmp_path, model_specs_toml=TWIN_FILE))

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
        rejection = describe_model_spec_document_rejection(document=_document(tmp_path, model_specs_toml=model_specs_toml))
        loader_error: InferenceBackendLibraryError | None = None
        try:
            _load(tmp_path, model_specs_toml=model_specs_toml)
        except InferenceBackendLibraryError as exc:
            loader_error = exc

        assert (rejection is None) is is_accepted, rejection
        assert (loader_error is None) is is_accepted, loader_error
