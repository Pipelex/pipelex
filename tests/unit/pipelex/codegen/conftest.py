import importlib.util
import sys
from datetime import date, datetime, time
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
def temporal_defaults_crate() -> LibraryCrate:
    """A normalized crate carrying valid date, datetime, and time defaults."""
    authored = LibraryCrate(
        concepts={
            "schedule.Event": ConceptBlueprint(
                description="A scheduled event",
                structure={
                    "starts_on": ConceptStructureBlueprint(
                        description="Start date", type=ConceptStructureBlueprintFieldType.DATE, default_value=date(2026, 7, 11)
                    ),
                    "recorded_at": ConceptStructureBlueprint(
                        description="Recorded timestamp",
                        type=ConceptStructureBlueprintFieldType.DATETIME,
                        default_value=datetime(2026, 7, 11, 9, 30),
                    ),
                    "starts_at": ConceptStructureBlueprint(
                        description="Start time", type=ConceptStructureBlueprintFieldType.TIME, default_value=time(9, 30)
                    ),
                },
            ),
        },
        domains={"schedule": DomainBlueprint(code="schedule", description="Schedule domain")},
    )
    return normalize_crate(authored, mthds_version=CRATE_TEST_VERSION)


@pytest.fixture
def reordered_dict_default_crates() -> tuple[LibraryCrate, LibraryCrate]:
    """Equivalent crates whose dictionary defaults differ only by insertion order."""

    def make_crate(default_value: dict[str, str]) -> LibraryCrate:
        return LibraryCrate(
            mthds_version=CRATE_TEST_VERSION,
            concepts={
                "settings.Options": ConceptBlueprint(
                    description="Options",
                    structure={
                        "labels": ConceptStructureBlueprint(
                            description="Labels by key",
                            type=ConceptStructureBlueprintFieldType.DICT,
                            key_type="text",
                            value_type="text",
                            default_value=default_value,
                        )
                    },
                )
            },
        )

    return make_crate({"zeta": "last", "alpha": "first"}), make_crate({"alpha": "first", "zeta": "last"})


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
def natives_only_crate() -> LibraryCrate:
    """A crate holding nothing but natives — what an ordinary method that declares no concepts of its
    own normalizes to (a `Text -> Text` pipe materializes `native.Text` and nothing else).

    `python-structures` skips natives, so this is the *reachable* route to an empty projection: the
    library is non-empty, yet that emitter has no class to write.
    """
    authored = LibraryCrate(concepts={"native.Text": ConceptBlueprint(description="A text")})
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


@pytest.fixture
def every_type_kind_crate() -> LibraryCrate:
    """A normalized crate whose fields cover **every** `ResolvedTypeKind`, plus an optional field and a
    structureless (opaque) concept.

    This is the single source of type-kind coverage for the lint-clean regression test:
    `test_emitted_artifacts_are_lint_clean` asserts the resolved trees reach every enum member, so a
    newly added `ResolvedTypeKind` that nobody wires in here fails loudly instead of going unlinted.
    """
    authored = LibraryCrate(
        concepts={
            "lintcheck.Detail": ConceptBlueprint(
                description="A nested detail",
                structure={"note": ConceptStructureBlueprint(description="A note", type=ConceptStructureBlueprintFieldType.TEXT, required=True)},
            ),
            # A structureless concept: emits the two-paragraph docstring (description + imprecision caveat).
            "lintcheck.Opaque": ConceptBlueprint(description="A structureless concept"),
            # Descriptions carrying characters the docstring renderer must not backslash-escape: a
            # double quote and a backslash both put a `\` in the docstring under naive escaping, which
            # ruff's D301 then auto-rewrites to an `r` prefix — changing the bytes and breaking the stamp.
            "lintcheck.Quoted": ConceptBlueprint(
                description='The "primary" thing',
                structure={
                    "pattern": ConceptStructureBlueprint(
                        description=r"Matches the \d regex", type=ConceptStructureBlueprintFieldType.TEXT, required=True
                    )
                },
            ),
            "lintcheck.Record": ConceptBlueprint(
                description="A record touching every resolved type kind",
                structure={
                    # scalars
                    "title": ConceptStructureBlueprint(description="Title", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
                    "ratio": ConceptStructureBlueprint(description="Ratio", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
                    "count": ConceptStructureBlueprint(description="Count", type=ConceptStructureBlueprintFieldType.INTEGER, required=True),
                    "is_active": ConceptStructureBlueprint(description="Active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=True),
                    "published_on": ConceptStructureBlueprint(description="Date", type=ConceptStructureBlueprintFieldType.DATE, required=True),
                    "recorded_at": ConceptStructureBlueprint(
                        description="Timestamp", type=ConceptStructureBlueprintFieldType.DATETIME, required=True
                    ),
                    "starts_at": ConceptStructureBlueprint(description="Start time", type=ConceptStructureBlueprintFieldType.TIME, required=True),
                    # literal — the double-quoting path
                    "status": ConceptStructureBlueprint(description="Status", choices=["draft", "final"], required=True),
                    # concept refs: one in-module, one native (exercises the native content-class import)
                    "detail": ConceptStructureBlueprint(
                        description="Detail", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Detail", required=True
                    ),
                    "label": ConceptStructureBlueprint(
                        description="Label", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Text", required=True
                    ),
                    # containers
                    "tags": ConceptStructureBlueprint(
                        description="Tags", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", required=True
                    ),
                    "counts": ConceptStructureBlueprint(
                        description="Counts", type=ConceptStructureBlueprintFieldType.DICT, key_type="text", value_type="integer", required=True
                    ),
                    # ANY — only reachable nested, from genuine source imprecision. An untyped list also
                    # emits the trailing `# imprecise:` comment, so that shape gets linted too.
                    "items": ConceptStructureBlueprint(description="Untyped items", type=ConceptStructureBlueprintFieldType.LIST, required=True),
                    # an optional field, so the `X | None` path is emitted too
                    "note": ConceptStructureBlueprint(description="Optional note", type=ConceptStructureBlueprintFieldType.TEXT, required=False),
                },
            ),
        },
        domains={"lintcheck": DomainBlueprint(code="lintcheck", description="Lint check domain")},
    )
    return normalize_crate(authored, mthds_version=CRATE_TEST_VERSION)


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
