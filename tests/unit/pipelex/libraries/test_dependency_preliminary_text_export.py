"""Tests that synthetic helpers from build-time elaboration are loaded alongside their parent
when a dependency manifest restricts exports.

Without this behavior, exporting a `preliminary_text` PipeLLM would let the parent pipe load
into the consumer library while its `__draft_text` and `__structure` helpers are filtered out,
producing a runtime resolution failure inside the wrapping PipeSequence.
"""

from pathlib import Path

from mthds.package.dependency_resolver import ResolvedDependency
from mthds.package.manifest.schema import MethodsManifest
from pytest_mock import MockerFixture

from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.library_manager import LibraryManager

# A dep package with a single `preliminary_text` PipeLLM. After elaboration the bundle holds
# three pipes: `make_review` (PipeSequence), `make_review__draft_text`, `make_review__structure`.
DEP_MTHDS = """\
domain = "review_dep"
description = "A dep package shipping a preliminary_text pipe"

[concept]
RestaurantReview = "A structured review concept"

[pipe.make_review]
type = "PipeLLM"
description = "Draft a restaurant review then structure it"
inputs = { topic = "Text" }
output = "RestaurantReview"
prompt = "Write a review about $topic"
structuring_method = "preliminary_text"
"""


class TestDependencyPreliminaryTextExport:
    def _build_resolved_dep(self, tmp_path: Path, exported: set[str] | None) -> ResolvedDependency:
        mthds_file = tmp_path / "review_dep.mthds"
        mthds_file.write_text(DEP_MTHDS, encoding="utf-8")

        manifest = MethodsManifest(
            address="github.com/org/review-dep",
            version="1.0.0",
            description="A dep package",
        )
        return ResolvedDependency(
            alias="review_dep",
            address="github.com/org/review-dep",
            manifest=manifest,
            package_root=tmp_path,
            mthds_files=[mthds_file],
            exported_pipe_codes=exported,
        )

    def test_synthetic_helpers_load_when_parent_is_exported(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When the manifest exports `make_review`, both synthetic helpers must also load.

        The parent is a PipeSequence post-elaboration; it references the helpers by bare code,
        so they must be present in the child library or the consumer crashes at run time.
        """
        # Hub interaction is required for PipeFactory to resolve concepts during the dep load.
        # We use the live hub but a fresh empty library to keep the test isolated.
        library_manager = get_library_manager()
        library = LibraryFactory.make_empty()
        # Avoid noise from the live hub; the side-effect register/unregister of temp concepts
        # already happens inside _load_single_dependency.
        mocker.patch.object(library_manager, "get_current_library", return_value=library)

        manager = LibraryManager()
        manager._load_single_dependency(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            library=library,
            resolved_dep=self._build_resolved_dep(tmp_path=tmp_path, exported={"make_review"}),
        )

        child_library = library.dependency_libraries["review_dep"]
        loaded_codes = {pipe.code for pipe in child_library.pipe_library.get_pipes()}

        assert "make_review" in loaded_codes, "Parent pipe should be loaded when listed in exports"
        assert "make_review__draft_text" in loaded_codes, (
            "Synthetic helper must travel with the exported parent — otherwise the wrapping "
            "PipeSequence references an unresolved pipe code at runtime."
        )
        assert "make_review__structure" in loaded_codes, "Synthetic helper must travel with the exported parent."

    def test_synthetic_helpers_are_filtered_when_parent_is_not_exported(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """When the manifest exports nothing, no synthetic helpers should leak in either."""
        library_manager = get_library_manager()
        library = LibraryFactory.make_empty()
        mocker.patch.object(library_manager, "get_current_library", return_value=library)

        manager = LibraryManager()
        manager._load_single_dependency(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            library=library,
            resolved_dep=self._build_resolved_dep(tmp_path=tmp_path, exported=set()),
        )

        child_library = library.dependency_libraries["review_dep"]
        loaded_codes = {pipe.code for pipe in child_library.pipe_library.get_pipes()}

        assert "make_review" not in loaded_codes
        assert "make_review__draft_text" not in loaded_codes
        assert "make_review__structure" not in loaded_codes
