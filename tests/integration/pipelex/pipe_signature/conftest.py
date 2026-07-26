from typing import Callable

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.method_hub import get_concept_library
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint

SIGNATURES_DOMAIN_CODE = "sigtests"


@pytest.fixture
def setup_signature_library(load_empty_library: Callable[[], str]) -> Callable[[], None]:
    """Open an empty library and register the `Document`/`Summary` concepts used across signature tests.

    The library is torn down by the underlying `load_empty_library` fixture; this fixture only adds setup.
    """

    def _setup() -> None:
        load_empty_library()
        concept_library = get_concept_library()

        concept_document = ConceptFactory.make_from_blueprint(
            concept_code="SigTestDoc",
            domain_code=SIGNATURES_DOMAIN_CODE,
            blueprint_or_string_description=ConceptBlueprint(description="A document concept for signature tests."),
        )
        concept_summary = ConceptFactory.make_from_blueprint(
            concept_code="SigTestSummary",
            domain_code=SIGNATURES_DOMAIN_CODE,
            blueprint_or_string_description=ConceptBlueprint(description="A summary concept for signature tests."),
        )
        concept_library.add_concepts([concept_document, concept_summary])

    return _setup


@pytest.fixture
def make_signature_blueprint() -> Callable[..., PipeSignatureBlueprint]:
    """Return a factory that builds `PipeSignatureBlueprint` with sensible defaults."""

    def _make(
        description: str = "A signature for testing.",
        inputs: dict[str, str] | None = None,
        output: str = "Text",
        signature_for: str | None = None,
    ) -> PipeSignatureBlueprint:
        kwargs: dict[str, object] = {
            "description": description,
            "inputs": inputs,
            "output": output,
        }
        if signature_for is not None:
            kwargs["signature_for"] = signature_for
        return PipeSignatureBlueprint(**kwargs)  # type: ignore[arg-type]

    return _make
