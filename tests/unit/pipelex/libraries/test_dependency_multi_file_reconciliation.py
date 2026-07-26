"""Tests that a multi-file dependency package reconciles like the main additive load path.

A dependency can be authored across files: a header file declaring a `PipeSignature` forward
declaration plus a concrete sibling that implements it. The dependency loader must merge those
files into a crate (so the signature and concrete collapse to a single concrete pipe) instead of
adding each blueprint's pipes directly — which would collide in `add_new_pipe` and silently drop a
declaration. A genuine duplicate (two concrete definitions of the same pipe) must still raise.
"""

from pathlib import Path

import pytest
from mthds.package.dependency_resolver import ResolvedDependency
from mthds.package.manifest.schema import MethodsManifest
from pytest_mock import MockerFixture

from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.library_manager import LibraryManager
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.method_hub import get_library_manager

# Header file: a PipeSignature forward-declaration of `summarize`.
DEP_HEADER_MTHDS = """\
domain = "summary_dep"
description = "Dependency header declaring a summarize signature"

[pipe.summarize]
description = "Summarize a document (contract only)."
inputs = { doc = "Text" }
output = "Text"
"""

# Concrete sibling: the real `summarize` implementation, contract matching the header.
DEP_CONCRETE_MTHDS = """\
domain = "summary_dep"
description = "Dependency definition implementing summarize"

[pipe.summarize]
type = "PipeLLM"
description = "Summarize a document."
inputs = { doc = "Text" }
output = "Text"
prompt = "Summarize $doc."
"""

# Typeless header: the same forward-declaration of `summarize`, written WITHOUT the `type` tag.
# The before-validator normalizes it to a PipeSignature, so the new surface must reconcile
# identically to the explicit-tag header above.
DEP_TYPELESS_HEADER_MTHDS = """\
domain = "summary_dep"
description = "Dependency header declaring a summarize signature without a type tag"

[pipe.summarize]
description = "Summarize a document (contract only)."
inputs = { doc = "Text" }
output = "Text"
"""

# A second concrete `summarize` (genuine duplicate) for the negative case.
DEP_CONCRETE_DUP_MTHDS = """\
domain = "summary_dep"
description = "Dependency definition with a duplicate concrete summarize"

[pipe.summarize]
type = "PipeLLM"
description = "Another summarize implementation."
inputs = { doc = "Text" }
output = "Text"
prompt = "Briefly summarize $doc."
"""


class TestDependencyMultiFileReconciliation:
    def _build_resolved_dep(self, tmp_path: Path, file_contents: list[tuple[str, str]]) -> ResolvedDependency:
        mthds_files: list[Path] = []
        for file_name, content in file_contents:
            mthds_file = tmp_path / file_name
            mthds_file.write_text(content, encoding="utf-8")
            mthds_files.append(mthds_file)

        manifest = MethodsManifest(
            address="github.com/org/summary-dep",
            version="1.0.0",
            description="A multi-file dep package",
        )
        return ResolvedDependency(
            alias="summary_dep",
            address="github.com/org/summary-dep",
            manifest=manifest,
            package_root=tmp_path,
            mthds_files=mthds_files,
            # None => no export filter, every pipe is public.
            exported_pipe_codes=None,
        )

    def test_signature_and_concrete_sibling_reconcile_to_concrete(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """A header signature + concrete sibling collapse to a single concrete pipe (concrete wins).

        The header file is listed first, so the broken per-blueprint loader would add the signature
        and then drop the concrete as a duplicate, leaving `summarize` as a non-executable signature.
        Routing through the crate merge reconciles them: the concrete must win.
        """
        library_manager = get_library_manager()
        library = LibraryFactory.make_empty()
        mocker.patch.object(library_manager, "get_current_library", return_value=library)

        manager = LibraryManager()
        manager._load_single_dependency(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            library=library,
            resolved_dep=self._build_resolved_dep(
                tmp_path=tmp_path,
                file_contents=[("header.mthds", DEP_HEADER_MTHDS), ("definition.mthds", DEP_CONCRETE_MTHDS)],
            ),
        )

        child_library = library.dependency_libraries["summary_dep"]
        summarize_pipes = [pipe for pipe in child_library.pipe_library.get_pipes() if pipe.code == "summarize"]
        assert len(summarize_pipes) == 1, "Signature and concrete must reconcile to exactly one pipe"
        assert not summarize_pipes[0].is_signature, "The concrete definition must win over the forward signature"

    def test_typeless_header_and_concrete_sibling_reconcile_to_concrete(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """A TYPELESS header (no `type`) + concrete sibling collapse to a single concrete pipe.

        Confirms the new typeless-signature surface reconciles exactly like the explicit-tag header:
        the before-validator normalizes the typeless section to a PipeSignature, and the concrete wins.
        """
        library_manager = get_library_manager()
        library = LibraryFactory.make_empty()
        mocker.patch.object(library_manager, "get_current_library", return_value=library)

        manager = LibraryManager()
        manager._load_single_dependency(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            library=library,
            resolved_dep=self._build_resolved_dep(
                tmp_path=tmp_path,
                file_contents=[("header.mthds", DEP_TYPELESS_HEADER_MTHDS), ("definition.mthds", DEP_CONCRETE_MTHDS)],
            ),
        )

        child_library = library.dependency_libraries["summary_dep"]
        summarize_pipes = [pipe for pipe in child_library.pipe_library.get_pipes() if pipe.code == "summarize"]
        assert len(summarize_pipes) == 1, "Typeless signature and concrete must reconcile to exactly one pipe"
        assert not summarize_pipes[0].is_signature, "The concrete definition must win over the typeless forward signature"

    def test_two_concrete_definitions_raise(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Two concrete definitions of the same pipe in a dependency are a genuine duplicate and must raise."""
        library_manager = get_library_manager()
        library = LibraryFactory.make_empty()
        mocker.patch.object(library_manager, "get_current_library", return_value=library)

        manager = LibraryManager()
        with pytest.raises(PipeLibraryError):
            manager._load_single_dependency(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                library=library,
                resolved_dep=self._build_resolved_dep(
                    tmp_path=tmp_path,
                    file_contents=[("def_a.mthds", DEP_CONCRETE_MTHDS), ("def_b.mthds", DEP_CONCRETE_DUP_MTHDS)],
                ),
            )
