import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate

CRATE_TEST_VERSION = "1.0.0-test"


@pytest.fixture
def pipeline_crate() -> LibraryCrate:
    """A realistic normalized crate: cross-concept ref, native ref, list, literal-with-default, refines-native."""
    authored = LibraryCrate(
        concepts={
            "pipeline.Report": ConceptBlueprint(
                description="A report with a score and a label",
                structure={
                    "score": ConceptStructureBlueprint(description="the score", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Score"),
                    "label": ConceptStructureBlueprint(description="a label", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Text"),
                    "tags": ConceptStructureBlueprint(description="free-form tags", type=ConceptStructureBlueprintFieldType.LIST, item_type="text"),
                    "status": ConceptStructureBlueprint(description="review status", choices=["draft", "final"], default_value="draft"),
                },
            ),
            "pipeline.Score": ConceptBlueprint(
                description="A score",
                structure={
                    "value": ConceptStructureBlueprint(description="the value", type=ConceptStructureBlueprintFieldType.NUMBER),
                    "rationale": ConceptStructureBlueprint(description="why", type=ConceptStructureBlueprintFieldType.TEXT, required=False),
                },
            ),
            "pipeline.Summary": ConceptBlueprint(description="A short summary of a report", refines="Text"),
        },
        domains={"pipeline": DomainBlueprint(code="pipeline", description="Pipeline domain")},
    )
    return normalize_crate(authored, mthds_version=CRATE_TEST_VERSION)


@pytest.fixture
def edge_crate() -> LibraryCrate:
    """A crate exercising the honest edges: cross-domain code collision, an imprecise (untyped) list, a
    multi-word field (snake<->camel), a structureless concept, and a Python-class-backed opaque concept.
    """
    return LibraryCrate(
        mthds_version=CRATE_TEST_VERSION,
        concepts={
            "alpha.Result": ConceptBlueprint(
                description="alpha result",
                structure={
                    "items": ConceptStructureBlueprint(description="untyped list", type=ConceptStructureBlueprintFieldType.LIST),
                    "item_count": ConceptStructureBlueprint(description="how many", type=ConceptStructureBlueprintFieldType.INTEGER, required=True),
                },
            ),
            "beta.Result": ConceptBlueprint(
                description="beta result",
                structure={"n": ConceptStructureBlueprint(description="a count", type=ConceptStructureBlueprintFieldType.INTEGER, required=True)},
            ),
            "alpha.Blob": ConceptBlueprint(description="an opaque thing"),
            "alpha.Legacy": ConceptBlueprint(description="python-backed", structure="MyLegacyClass"),
        },
    )


@pytest.fixture
def materialized_image_crate() -> LibraryCrate:
    """A normalized crate that references the `Image` native, so normalization actually materializes it
    (from the pinned definitions — flat `width`/`height`), plus authored dict fields covering the DICT
    path for every emitter: a typed dict and an unspecified-values dict (the `Any` sentinel, surfaced
    as declared imprecision).
    """
    authored = LibraryCrate(
        concepts={
            "media.Photo": ConceptBlueprint(description="A photo", refines="Image"),
            "media.Gallery": ConceptBlueprint(
                description="A gallery",
                structure={
                    "captions": ConceptStructureBlueprint(
                        description="caption per photo code",
                        type=ConceptStructureBlueprintFieldType.DICT,
                        key_type="str",
                        value_type="text",
                        required=True,
                    ),
                    "metadata": ConceptStructureBlueprint(
                        description="free-form metadata",
                        type=ConceptStructureBlueprintFieldType.DICT,
                        key_type="str",
                        value_type="Any",
                        required=False,
                    ),
                },
            ),
        },
        domains={"media": DomainBlueprint(code="media", description="Media domain")},
    )
    return normalize_crate(authored, mthds_version=CRATE_TEST_VERSION)


@pytest.fixture
def refines_crate() -> LibraryCrate:
    """A concept refining a structureless native keeps its refines link, so the emitter renders inheritance."""
    return LibraryCrate(
        mthds_version=CRATE_TEST_VERSION,
        concepts={
            "native.Image": ConceptBlueprint(description="An image"),
            "media.Thumbnail": ConceptBlueprint(description="A small image", refines="native.Image"),
        },
    )


def load_generated_module(content: str, *, tmp_path: Path, name: str) -> Any:
    """Write generated Python to disk, import it, and return it (proves compile + exec).

    Returns `Any`: the generated classes exist only at runtime, so their members are deliberately
    opaque to the type checker.
    """
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(content, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
