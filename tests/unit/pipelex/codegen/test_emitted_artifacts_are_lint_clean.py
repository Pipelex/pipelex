"""The emitted Python artifacts must be lint-clean on arrival.

A stamped artifact's hash is a raw SHA-256 over its body bytes, so any reformatting a consumer's own
`ruff check --fix` / `ruff format` would apply changes the bytes and makes `pipelex codegen check`
report the file as hand-edited — accusing the user of the one thing they did not do. The emitters are
therefore required to emit exactly what ruff wants; this test is the guard on that property.

Three rules are deliberately suppressed *in the invocation* rather than satisfied in the emitted bytes.
The test for whether a rule may be suppressed here is whether ruff can **auto-apply** its fix: only an
applied fix rewrites bytes, and only rewritten bytes break a stamp. A rule that merely reports is a
config-level caveat for the consumer to make, not a defect in what we emit.

- `INP001` is an artifact of linting a loose directory (no `__init__.py`), not of file content.
- `E501` fires on a single long string literal — an authored description or choice value that has no
  wrappable form, because you cannot break a string without altering the author's text. It has no fix,
  and it is not in ruff's default rule set, so it neither breaks a stamp nor affects most consumers.
  The *surrounding* call is a different matter, and is wrapped: see `PY_EXPLODE_WIDTH`.
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
from typing import cast

import pytest

from pipelex.codegen.emitters.python_common import PY_EXPLODE_WIDTH, python_header, render_import_block
from pipelex.codegen.emitters.python_pydantic import emit_python_pydantic
from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.emitters.target import EmittedFile
from pipelex.codegen.emitters.ts_zod import TS_PRINT_WIDTH, emit_ts_zod
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
    "lint.per-file-ignores={'*'=['INP001','E501']}",
    "--config",
    f"lint.flake8-type-checking.runtime-evaluated-base-classes={_RUNTIME_EVALUATED_BASES}",
]

_EMITTERS: list[tuple[str, Callable[[ResolvedLibrary], list[EmittedFile]]]] = [
    ("python-structures", emit_python_structures),
    ("python-pydantic", emit_python_pydantic),
]


_EMPTY_LIBRARY = ResolvedLibrary(mthds_version="1.0.0-test", concepts=[])
"""A crate with no concepts at all — reachable from a bundle that declares only a domain."""


def _collect_kinds(resolved_type: ResolvedType) -> set[ResolvedTypeKind]:
    """Every kind reachable in a resolved-type tree, depth-first."""
    kinds = {resolved_type.kind}
    for child in (resolved_type.item, resolved_type.key, resolved_type.value):
        if child is not None:
            kinds |= _collect_kinds(child)
    return kinds


def _write_artifacts(*, emitted: list[EmittedFile], tmp_path: Path) -> None:
    """Write the artifacts out, skipping the test when the current interpreter has no ruff."""
    try:
        subprocess.run([sys.executable, "-m", "ruff", "--version"], check=True, capture_output=True)  # noqa: S603
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("ruff not available in current interpreter")

    for emitted_file in emitted:
        (tmp_path / emitted_file.filename).write_text(emitted_file.content, encoding="utf-8")


def _width_config(line_length: int | None) -> list[str]:
    return ["--config", f"line-length={line_length}"] if line_length is not None else []


def _label(*, target: str, line_length: int | None) -> str:
    return f"[{target}]" if line_length is None else f"[{target} @ line-length={line_length}]"


def _assert_ruff_format_stable(*, tmp_path: Path, target: str, line_length: int | None = None) -> None:
    """Require `ruff format --check` to find nothing — the property byte-reproducibility rests on."""
    formatted = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ruff", "format", "--check", str(tmp_path), "--config", str(_PYPROJECT), *_width_config(line_length)],
        capture_output=True,
        text=True,
        check=False,
    )
    label = _label(target=target, line_length=line_length)
    assert formatted.returncode == 0, f"{label} emitted artifact is not `ruff format` clean:\n{formatted.stdout}{formatted.stderr}"


def _assert_ruff_clean(*, emitted: list[EmittedFile], tmp_path: Path, target: str, line_length: int | None = None) -> None:
    """Write the artifacts out and require both `ruff check` and `ruff format --check` to find nothing."""
    _write_artifacts(emitted=emitted, tmp_path=tmp_path)

    check = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ruff", "check", str(tmp_path), *_CONSUMER_LINT_CONFIG, *_width_config(line_length)],
        capture_output=True,
        text=True,
        check=False,
    )
    label = _label(target=target, line_length=line_length)
    assert check.returncode == 0, f"{label} emitted artifact is not lint-clean:\n{check.stdout}{check.stderr}"

    _assert_ruff_format_stable(tmp_path=tmp_path, target=target, line_length=line_length)


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
        _assert_ruff_clean(emitted=emit(resolve_concepts_from_crate(every_type_kind_crate)), tmp_path=tmp_path, target=target)

    @pytest.mark.parametrize(("target", "emit"), _EMITTERS)
    def test_empty_projection_is_lint_clean(
        self,
        tmp_path: Path,
        target: str,
        emit: Callable[[ResolvedLibrary], list[EmittedFile]],
    ):
        """A projection with nothing to emit still has to arrive lint-clean.

        Emitting the import block with no class to use it is an `F401`, and the block separator leaves a
        trailing blank-line run `ruff format` collapses — either one rewrites the body bytes and breaks
        the stamp, which is exactly the accusation this module exists to prevent.
        """
        _assert_ruff_clean(emitted=emit(_EMPTY_LIBRARY), tmp_path=tmp_path, target=target)

    @pytest.mark.parametrize("line_length", [88, 100, 120, 150, 200])
    @pytest.mark.parametrize(("target", "emit"), _EMITTERS)
    def test_emitted_artifact_is_stable_at_every_consumer_line_length(
        self,
        every_type_kind_crate: LibraryCrate,
        tmp_path: Path,
        target: str,
        emit: Callable[[ResolvedLibrary], list[EmittedFile]],
        line_length: int,
    ):
        """The consumer's `line-length` is theirs, not ours, and it decides what their formatter rewrites.

        A long authored description or choice list has no flat form that survives every width, so the
        emitter hands over an already-exploded call carrying a magic trailing comma — the one construct
        Black and ruff both refuse to rejoin at any width. `PY_EXPLODE_WIDTH` is the floor of the range
        guarded here: ruff's own default, and so the tightest setting a consumer is likely to lint at.
        """
        _assert_ruff_clean(
            emitted=emit(resolve_concepts_from_crate(every_type_kind_crate)), tmp_path=tmp_path, target=target, line_length=line_length
        )

    @pytest.mark.parametrize("crate_fixture", ["all_opaque_crate", "refines_native_only_crate"])
    @pytest.mark.parametrize(("target", "emit"), _EMITTERS)
    def test_crates_that_use_no_seeded_import_are_lint_clean(
        self,
        request: pytest.FixtureRequest,
        tmp_path: Path,
        target: str,
        emit: Callable[[ResolvedLibrary], list[EmittedFile]],
        crate_fixture: str,
    ):
        """Every import has to be registered by whoever writes the name, not seeded up front.

        Both crate shapes are ordinary — a `Question -> Answer` method declares only structureless
        concepts, and a summarizer may declare only refinements of a native — and each leaves one of the
        formerly-seeded imports unused. `F401` is a *safe* fix, so `ruff check --fix` deletes the line,
        rewrites the body, and `codegen check` then reports a file nobody touched as hand-edited.
        """
        crate = cast("LibraryCrate", request.getfixturevalue(crate_fixture))
        _assert_ruff_clean(emitted=emit(resolve_concepts_from_crate(crate)), tmp_path=tmp_path, target=target)

    @pytest.mark.parametrize(
        "imports",
        [
            pytest.param(
                {f"from a.deeply.nested.consumer.module import Alpha{index}Content" for index in range(6)},
                id="merged-names-cross-the-width",
            ),
            pytest.param(
                {"from a.deeply.nested.consumer.module import ASingleNameLongEnoughToCrossTheThresholdOnItsOwn"},
                id="one-name-crosses-the-width",
            ),
        ],
    )
    def test_import_block_is_format_stable_past_the_explode_width(self, imports: set[str], tmp_path: Path):
        """The import block is emitted bytes like any other, so it has to be a formatter fixed point too.

        Every *other* renderer pre-explodes past `PY_EXPLODE_WIDTH`; a flat import line that crosses it is
        rewritten into the parenthesized form by the consumer's first `ruff format`, which changes the body
        bytes and makes `codegen check` report the file as hand-edited. No crate shape reaches the width
        today — each native content class lives in its own module, so nothing merges far enough — which is
        exactly why the property needs a direct test rather than a crate fixture that happens to cover it.

        Format-stable only, not lint-clean: an import block on its own has nothing to *use* the names it
        imports, so `F401` fires on a shape no emitter ever writes. The whole-artifact tests above cover
        lint-cleanliness; what is under test here is the formatter fixed point.
        """
        emitted = [EmittedFile(filename="structures.py", content=f"{python_header(target='python-structures')}{render_import_block(imports)}\n")]
        _write_artifacts(emitted=emitted, tmp_path=tmp_path)
        _assert_ruff_format_stable(tmp_path=tmp_path, target="import-block", line_length=PY_EXPLODE_WIDTH)

    def test_natives_only_crate_emits_a_lint_clean_structures_module(self, natives_only_crate: LibraryCrate, tmp_path: Path):
        """The reachable route to an empty projection, and the reason the case is not academic.

        `python-structures` skips natives (they already exist in the runtime), so an ordinary method that
        declares no concepts of its own — a `Text -> Text` pipe — leaves that emitter with nothing to
        write, even though the library itself is not empty.
        """
        emitted = emit_python_structures(resolve_concepts_from_crate(natives_only_crate))
        assert [emitted_file.content for emitted_file in emitted] == [python_header(target="python-structures")]
        _assert_ruff_clean(emitted=emitted, tmp_path=tmp_path, target="python-structures")

    def test_empty_ts_projection_is_a_bare_header(self):
        """Both TypeScript artifacts collapse to their header alone when there is nothing to project.

        The alternative — keeping the import line — emits `import {  } from "./types";` (which prettier
        rewrites to `import {} …`) above a trailing blank-line run (which it collapses). Needs no prettier
        binary, so like the invariant above it always runs.
        """
        for emitted_file in emit_ts_zod(_EMPTY_LIBRARY):
            body = emitted_file.content
            # Comments and nothing else: no import to go unused, and no blank line to collapse (a blank
            # line does not start with `//`, so this rules out the trailing run too).
            assert all(line.startswith("//") for line in body.splitlines()), f"{emitted_file.filename} is not a bare header:\n{body}"
            assert body.endswith("\n")

    def test_emitted_ts_has_no_collapsible_blank_runs(self, every_type_kind_crate: LibraryCrate):
        """Prettier collapses a run of blank lines to one under *every* config — so emitting two (the
        Python idiom) guarantees a reformat, and a broken stamp, for any TypeScript consumer.

        This invariant needs no prettier binary, so unlike `test_emitted_ts_is_prettier_clean` it always runs.
        """
        for emitted_file in emit_ts_zod(resolve_concepts_from_crate(every_type_kind_crate)):
            offenders = re.findall(r"\n[ \t]*\n[ \t]*\n", emitted_file.content)
            assert not offenders, f"{emitted_file.filename} contains {len(offenders)} collapsible blank-line run(s)"

    def test_emitted_ts_lines_fit_the_print_width(self, every_type_kind_crate: LibraryCrate):
        """No emitted code line may exceed prettier's print width — it would be wrapped, breaking the stamp.

        This is the guard that actually holds the TypeScript line in CI, where there is no node toolchain
        for `test_emitted_ts_is_prettier_clean` to use. It needs no prettier binary, and it is what turns
        an unmodelled overflow (a long concept name, a long choice list) into a failing test.

        Comment lines are exempt on purpose: prettier reflows code, never the contents of a `//` line or a
        `/** … */` block, so a long JSDoc line is stable at any width.
        """
        for emitted_file in emit_ts_zod(resolve_concepts_from_crate(every_type_kind_crate)):
            overlong = [
                line for line in emitted_file.content.splitlines() if len(line) > TS_PRINT_WIDTH and not line.lstrip().startswith(("//", "/*", "*"))
            ]
            assert not overlong, f"{emitted_file.filename} has lines past prettier's print width:\n" + "\n".join(overlong)

    def test_emitted_ts_has_no_trailing_whitespace(self, every_type_kind_crate: LibraryCrate):
        """No emitted line may carry trailing whitespace — prettier strips it under *every* config.

        The shape that motivated this: a blank JSDoc line was emitted as `" * "`, which prettier rewrites
        to `" *"`. Any multi-line concept description reaches it, so a consumer running prettier over the
        generated `types.ts` changed the bytes and got the artifact reported as `[hand-edited]` — the exact
        false report these emitters exist to prevent.

        Like the two invariants above, this needs no prettier binary, so it is what holds the line in CI
        where `test_emitted_ts_is_prettier_clean` skips for want of a node toolchain.
        """
        for emitted_file in emit_ts_zod(resolve_concepts_from_crate(every_type_kind_crate)):
            offenders = [line for line in emitted_file.content.splitlines() if line != line.rstrip()]
            assert not offenders, f"{emitted_file.filename} has lines with trailing whitespace:\n" + "\n".join(repr(line) for line in offenders)

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
