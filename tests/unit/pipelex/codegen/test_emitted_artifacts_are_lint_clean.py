"""The emitted Python artifacts must be lint-clean on arrival.

A stamped artifact's hash is a raw SHA-256 over its body bytes, so any reformatting a consumer's own
`ruff check --fix` / `ruff format` would apply changes the bytes and makes `pipelex codegen check`
report the file as hand-edited — accusing the user of the one thing they did not do. The emitters are
therefore required to emit exactly what ruff wants; this test is the guard on that property.

Two rules are deliberately suppressed *in the invocation* rather than satisfied in the emitted bytes:

- `INP001` is an artifact of linting a loose directory (no `__init__.py`), not of file content.
- `TC003` wants `from datetime import date` moved into an `if TYPE_CHECKING:` block, which would
  **break** the generated code — pydantic resolves annotations at runtime to build validators. Ruff's
  `runtime-evaluated-base-classes` exists for exactly this, so the test passes it, exercising the
  configuration we tell consumers to use.

Imports are linted as a **consumer** would: in their tree `pipelex` is an installed dependency, so it
belongs in the third-party group. In this repo it is first-party and ruff wants the opposite order —
but no generated artifact is ever committed here, so the consumer's grouping is the one that matters.
See `render_import_block` in `pipelex/codegen/emitters/python_common.py`.
"""

import re
import shutil
import subprocess  # noqa: S404
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.codegen.emitters.python_pydantic import emit_python_pydantic
from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.emitters.target import EmittedFile
from pipelex.codegen.emitters.ts_zod import emit_ts_zod
from pipelex.codegen.resolved_concepts import ResolvedLibrary, resolve_concepts_from_crate
from pipelex.core.concepts.resolved_fields import ResolvedType, ResolvedTypeKind
from pipelex.libraries.library_crate import LibraryCrate

_REPO_ROOT = Path(__file__).parents[4]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

_RUNTIME_EVALUATED_BASES = "['pydantic.BaseModel','pipelex.core.stuffs.structured_content.StructuredContent']"

_CONSUMER_LINT_CONFIG = [
    "--config",
    str(_PYPROJECT),
    "--config",
    "lint.isort.known-third-party=['pipelex']",
    "--config",
    "lint.per-file-ignores={'*'=['INP001']}",
    "--config",
    f"lint.flake8-type-checking.runtime-evaluated-base-classes={_RUNTIME_EVALUATED_BASES}",
]

_EMITTERS: list[tuple[str, Callable[[ResolvedLibrary], list[EmittedFile]]]] = [
    ("python-structures", emit_python_structures),
    ("python-pydantic", emit_python_pydantic),
]


def _collect_kinds(resolved_type: ResolvedType) -> set[ResolvedTypeKind]:
    """Every kind reachable in a resolved-type tree, depth-first."""
    kinds = {resolved_type.kind}
    for child in (resolved_type.item, resolved_type.key, resolved_type.value):
        if child is not None:
            kinds |= _collect_kinds(child)
    return kinds


class TestEmittedArtifactsAreLintClean:
    def test_fixture_covers_every_resolved_type_kind(self, every_type_kind_crate: LibraryCrate):
        """The fixture is the single source of type-kind coverage — a new kind must be wired into it."""
        library = resolve_concepts_from_crate(every_type_kind_crate)
        covered: set[ResolvedTypeKind] = set()
        for concept in library.concepts:
            for concept_field in concept.fields:
                covered |= _collect_kinds(concept_field.resolved_type)

        missing = set(ResolvedTypeKind) - covered
        assert not missing, f"every_type_kind_crate no longer covers: {sorted(missing)} — wire them into the fixture"

    @pytest.mark.parametrize(("target", "emit"), _EMITTERS)
    def test_emitted_artifact_passes_ruff(
        self,
        every_type_kind_crate: LibraryCrate,
        tmp_path: Path,
        target: str,
        emit: Callable[[ResolvedLibrary], list[EmittedFile]],
    ):
        """`ruff check` and `ruff format --check` must both find nothing to change."""
        try:
            subprocess.run([sys.executable, "-m", "ruff", "--version"], check=True, capture_output=True)  # noqa: S603
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("ruff not available in current interpreter")

        for emitted_file in emit(resolve_concepts_from_crate(every_type_kind_crate)):
            (tmp_path / emitted_file.filename).write_text(emitted_file.content, encoding="utf-8")

        check = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "ruff", "check", str(tmp_path), *_CONSUMER_LINT_CONFIG],
            capture_output=True,
            text=True,
            check=False,
        )
        assert check.returncode == 0, f"[{target}] emitted artifact is not lint-clean:\n{check.stdout}{check.stderr}"

        formatted = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "ruff", "format", "--check", str(tmp_path), "--config", str(_PYPROJECT)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert formatted.returncode == 0, f"[{target}] emitted artifact is not `ruff format` clean:\n{formatted.stdout}{formatted.stderr}"

    def test_emitted_ts_has_no_collapsible_blank_runs(self, every_type_kind_crate: LibraryCrate):
        """Prettier collapses a run of blank lines to one under *every* config — so emitting two (the
        Python idiom) guarantees a reformat, and a broken stamp, for any TypeScript consumer.

        This invariant needs no prettier binary, so unlike `test_emitted_ts_is_prettier_clean` it always runs.
        """
        for emitted_file in emit_ts_zod(resolve_concepts_from_crate(every_type_kind_crate)):
            offenders = re.findall(r"\n[ \t]*\n[ \t]*\n", emitted_file.content)
            assert not offenders, f"{emitted_file.filename} contains {len(offenders)} collapsible blank-line run(s)"

    def test_emitted_ts_is_prettier_clean(self, every_type_kind_crate: LibraryCrate, tmp_path: Path):
        """`prettier --check` must find nothing to change in the emitted TypeScript.

        Skipped when prettier is not on PATH — this is a Python repo, so CI has no node toolchain. The
        always-on structural guard above is what holds the line there.
        """
        prettier = shutil.which("prettier")
        if prettier is None:
            pytest.skip("prettier not on PATH")

        for emitted_file in emit_ts_zod(resolve_concepts_from_crate(every_type_kind_crate)):
            (tmp_path / emitted_file.filename).write_text(emitted_file.content, encoding="utf-8")

        checked = subprocess.run(  # noqa: S603
            [prettier, "--check", str(tmp_path / "*.ts")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert checked.returncode == 0, f"emitted ts-zod artifact is not prettier-clean:\n{checked.stdout}{checked.stderr}"
