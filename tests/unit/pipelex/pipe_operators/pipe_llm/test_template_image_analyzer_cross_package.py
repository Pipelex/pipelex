"""The image analyzer must ask the *library* about compatibility, not the bare `Concept` model.

Cross-package `refines` aliases (``dep->domain.Code``) only resolve when a concept resolver is in
hand, and the library is what holds it. A call site that compares two `Concept` values directly has
no resolver, so an aliased refinement silently fails to resolve there and the analyzer mis-answers
"is this an image?" — at authoring time, with no error to read.

The concept below refines native Image through an alias while carrying a structure class that has
nothing in common with `ImageContent`. That combination is the point: the class tier cannot possibly
establish the relationship, so the verdict is decided by the declaration tier *and only if the
resolver is consulted*.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, cast

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.interpreter_hub import get_concept_library
from pipelex.pipe_operators.shared.image_reference import ImageReferenceKind
from pipelex.pipe_operators.shared.template_image_analyzer import TemplateImageAnalyzer

if TYPE_CHECKING:
    from pipelex.libraries.concept.concept_library import ConceptLibrary

_ALIASED_REF = "imgdep->native.Image"


class TestTemplateImageAnalyzerCrossPackageRefines:
    def test_cross_package_refined_image_is_recognized_as_an_image(self, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        library = cast("ConceptLibrary", get_concept_library())
        native_image = library.get_native_concept(native_concept=NativeConceptCode.IMAGE)

        def resolver(concept_ref: str) -> Concept | None:
            return native_image if concept_ref == _ALIASED_REF else None

        library.set_concept_resolver(resolver)
        library.add_new_concept(
            concept=Concept(
                code="AliasedImage",
                domain_code="test_pipes",
                description="An image concept reached through a cross-package alias",
                structure_class_name="TextContent",
                refines=_ALIASED_REF,
            )
        )

        result = TemplateImageAnalyzer.analyze_template_for_images(
            template_source="Describe this image:\n@pic",
            input_specs={"pic": "AliasedImage"},
            domain_code="test_pipes",
        )

        assert len(result) == 1
        assert result[0].variable_path == "pic"
        assert result[0].kind == ImageReferenceKind.DIRECT
