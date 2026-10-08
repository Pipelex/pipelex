"""Backend files declaring twins through the `handle` key, and the two ways their tests read one: loaded, and as a document."""

from pathlib import Path
from typing import Any

from pipelex.cogt.model_backends.credential_resolution import CredentialResolution
from pipelex.tools.misc.toml_utils import load_toml_from_path
from tests.helpers.backend_library_loading import load_library
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

NON_STRING_HANDLE_FILE = """
[defaults]
sdk = "openai_responses"

["1"]

["gpt-6-luna"]
handle = 1
"""

EMPTY_HANDLES_FILE = """
[defaults]
sdk = "openai_responses"

["gpt-6-luna"]
handle = ""

["gpt-6-luna-again"]
handle = ""
"""

HANDLE_IN_DEFAULTS_FILE = """
[defaults]
sdk = "openai_responses"
handle = "everything"

["gpt-6-luna"]
"""

# A `defaults` holding a string or a number rather than a table, which no reader may read as a table.
DEFAULTS_A_STRING_FILE = """
defaults = "handle-everything"

["gpt-6-luna"]
sdk = "openai_responses"
"""

DEFAULTS_A_NUMBER_FILE = """
defaults = 1

["gpt-6-luna"]
sdk = "openai_responses"
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


def load_backend_file(tmp_path: Path, *, model_specs_toml: str) -> Any:
    return load_library(
        tmp_path, backends_toml=BackendLibraryTomls.BACKENDS_TOML, model_specs_toml=model_specs_toml, credentials=CredentialResolution.REQUIRE
    )


def read_backend_document(tmp_path: Path, *, model_specs_toml: str) -> dict[str, Any]:
    document_path = tmp_path / "document.toml"
    document_path.write_text(model_specs_toml, encoding="utf-8")
    return load_toml_from_path(str(document_path))
