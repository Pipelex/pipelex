"""Shared setup for the InputShaper unit tests.

Registers the test concepts (and their structure classes) into the current library so every test
class in this directory can shape inputs against a known signature.
"""

from collections.abc import Generator
from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.hub import get_class_registry, get_concept_library
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from tests.unit.pipelex.core.memory.input_shaper.data import CONCEPT_DEFS, CONCEPT_REFS, REFINING_CLASSES, SHAPER_TEST_DOMAIN


@pytest.fixture(scope="class", autouse=True)
def shaper_library(load_test_library: Callable[[list[Path]], None]) -> Generator[None, None, None]:
    load_test_library([Path(__file__).parent])

    # Structured concepts' classes are picked up from data.py; the native refinements are not
    # StructuredContent subclasses, so register them explicitly (mirrors the generated subclass).
    ClassRegistryUtils.register_classes_in_file(
        file_path=Path(__file__).parent / "data.py",
        base_class=StructuredContent,
        is_include_imported=False,
    )
    class_registry = get_class_registry()
    for refining_class in REFINING_CLASSES:
        class_registry.register_class(class_type=refining_class)

    concept_library = get_concept_library()
    for concept_code, structure_class_name, refines in CONCEPT_DEFS:
        concept_library.add_new_concept(
            concept=ConceptFactory.make(
                concept_code=concept_code,
                domain_code=SHAPER_TEST_DOMAIN,
                description=f"Test concept {concept_code} for InputShaper unit tests",
                structure_class_name=structure_class_name,
                refines=refines,
            )
        )

    yield

    concept_library.remove_concepts_by_concept_refs(concept_refs=CONCEPT_REFS)
