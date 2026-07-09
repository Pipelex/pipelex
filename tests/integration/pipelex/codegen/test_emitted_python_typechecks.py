"""The D7 quality gate: emitted Python passes strict pyright and execs into real classes.

Per decision D7 (see `_codegen/TODOS.md`), the pyright gate on emitted Python lives in pipelex (the
toolchain is already present); the `tsc --strict` gate on emitted TypeScript lives in the
`conformance/` cross-repo harness. This module projects a rich crate — one exercising every
`ResolvedType` kind, a literal-with-default, an optional, a native reference, and a refines-native
concept — into `python-structures` and `python-pydantic`, then (1) runs strict pyright over the
generated files and asserts zero errors, and (2) imports them so the classes are actually built.
"""

import importlib.util
import json
import subprocess  # noqa: S404 -- runs the venv's own pyright on generated files with a fixed, trusted argv
import sys
from pathlib import Path

import pytest

from pipelex.codegen.emitters.python_pydantic import emit_python_pydantic
from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate

_CRATE_VERSION = "1.0.0-test"


def _rich_crate() -> LibraryCrate:
    """A crate exercising every resolved-type kind the Python emitters render."""
    field = ConceptStructureBlueprint
    kind = ConceptStructureBlueprintFieldType
    authored = LibraryCrate(
        concepts={
            "report.Report": ConceptBlueprint(
                description="A rich report",
                structure={
                    "title": field(description="the title", type=kind.TEXT),
                    "score": field(description="the score", type=kind.NUMBER),
                    "count": field(description="a count", type=kind.INTEGER),
                    "final": field(description="is final", type=kind.BOOLEAN),
                    "due": field(description="due date", type=kind.DATE, required=False),
                    "status": field(description="status", choices=["draft", "final"], default_value="draft"),
                    "tags": field(description="tags", type=kind.LIST, item_type="text"),
                    "meta": field(description="meta", type=kind.DICT, key_type="str", value_type="Any"),
                    "summary": field(description="the summary", type=kind.CONCEPT, concept_ref="Summary"),
                    "body": field(description="the body text", type=kind.CONCEPT, concept_ref="Text"),
                },
            ),
            "report.Summary": ConceptBlueprint(description="A short refined summary", refines="Text"),
        },
        domains={"report": DomainBlueprint(code="report", description="Report domain", main_pipe=None)},
    )
    return normalize_crate(authored, mthds_version=_CRATE_VERSION)


def _run_strict_pyright(*, directory: Path) -> tuple[int, str]:
    """Run strict pyright over `directory` using the test venv, returning (error_count, raw_json)."""
    (directory / "pyrightconfig.json").write_text(json.dumps({"typeCheckingMode": "strict", "reportMissingModuleSource": False}), encoding="utf-8")
    pyright = Path(sys.executable).parent / "pyright"
    completed = subprocess.run(  # noqa: S603 -- fixed, trusted argv (the venv's pyright over a tmp dir)
        [str(pyright), "--pythonpath", sys.executable, "--project", str(directory), "--outputjson"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    report = json.loads(completed.stdout)
    return report["summary"]["errorCount"], completed.stdout


class TestEmittedPythonTypechecks:
    """Strict-pyright gate (D7) plus a runtime import of the generated Python modules."""

    def test_emitted_python_passes_strict_pyright(self, tmp_path: Path) -> None:
        pyright = Path(sys.executable).parent / "pyright"
        if not pyright.exists():
            pytest.skip("pyright not available in this environment")
        crate = _rich_crate()
        library = resolve_concepts_from_crate(crate)
        files = [*emit_python_structures(library), *emit_python_pydantic(library)]
        for emitted in files:
            (tmp_path / emitted.filename).write_text(emitted.content, encoding="utf-8")

        error_count, raw = _run_strict_pyright(directory=tmp_path)
        assert error_count == 0, f"emitted Python failed strict pyright:\n{raw}"

    def test_emitted_python_execs_into_real_classes(self, tmp_path: Path) -> None:
        crate = _rich_crate()
        library = resolve_concepts_from_crate(crate)
        for emitted in [*emit_python_structures(library), *emit_python_pydantic(library)]:
            module_name = emitted.filename.removesuffix(".py")
            module_path = tmp_path / emitted.filename
            module_path.write_text(emitted.content, encoding="utf-8")
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            assert spec is not None
            assert spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            # The Summary concept refines the native Text — the emitted class must carry that base.
            summary_bases = [base.__name__ for base in module.Summary.__mro__]
            assert "TextContent" in summary_bases or "Text" in summary_bases
