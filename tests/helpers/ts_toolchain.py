"""Resolving the node toolchain the TypeScript emission gates need — and refusing to skip when a run demands it.

The ts-zod emitter is calibrated against a *specific* formatter: it emits the bytes prettier would leave
alone, so that a consumer's own format run cannot change them and make `pipelex codegen check` report an
untouched artifact as hand-edited. The gate on that calibration is `prettier --check` over the emission,
and the gate on the schema's meaning is running it under a real zod. Both need node, which a Python repo's
CI does not have by default — so both were written to `pytest.skip`, and both skipped everywhere. Three
content defects reached review through that gap, each caught afterwards by a hand-written byte assertion.

The fix is not another assertion, it is making the skip impossible where it matters. `make test-ts-gates`
provisions a pinned prettier and zod, puts them where these resolvers look, and sets
`PIPELEX_REQUIRE_TS_GATES=1`; under that flag an absent toolchain is a **failure**, not a skip. CI runs
that same target, so the gates are mandatory there and stay opportunistic on a developer's machine.

**Every resolver returns an absolute path.** Its callers use the result from somewhere else — the wire
round-trip launches node with `cwd=tmp_path` and symlinks the zod package into a `node_modules` under that
same directory — so a relative path clears the checks here, which run from the repository root, and then
names something different at the point of use. `shutil.which` returns whatever the `PATH` entry was, and an
environment variable holds whatever a human typed, so neither source can be trusted to be absolute.
"""

import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path
from typing import NoReturn

import pytest

REQUIRE_TS_GATES_ENV = "PIPELEX_REQUIRE_TS_GATES"
"""Set by `make test-ts-gates` (and therefore by CI): a missing toolchain fails instead of skipping."""

ZOD_PACKAGE_ENV = "PIPELEX_ZOD_PACKAGE"
"""Path to the `zod` package directory to link against, when it is not a global npm install."""

NODE_TYPE_STRIPPING_MINIMUM = (22, 6)
"""`--experimental-strip-types` landed in node 22.6, which is what lets node run the emitted `.ts` directly."""

_FALSE_SPELLINGS = {"", "0", "false", "no"}


def ts_gates_are_required() -> bool:
    """Whether this run declared the node toolchain mandatory rather than opportunistic."""
    return os.environ.get(REQUIRE_TS_GATES_ENV, "").strip().lower() not in _FALSE_SPELLINGS


def _unavailable(what: str) -> NoReturn:
    """Skip — unless the run declared the toolchain mandatory, in which case its absence is the failure."""
    if ts_gates_are_required():
        pytest.fail(f"{what}, and {REQUIRE_TS_GATES_ENV} is set, so this gate may not skip. Provision it with `make test-ts-gates`.")
    pytest.skip(f"{what} (run `make test-ts-gates` to provision it)")


def _absolute_executable(found: str) -> str:
    """An executable path an absolute one, with its symlinks left alone.

    `Path.resolve()` is wrong here: a version manager (volta, asdf, nvm) puts a *shim* on PATH, and some
    shims dispatch on the path they were invoked by, so resolving one to its target can change what runs.
    Only the relative-`PATH`-entry case needs fixing, and `absolute()` is exactly that much.
    """
    return str(Path(found).absolute())


def resolve_prettier() -> str:
    """The `prettier` binary the formatting gate runs, from PATH, absolute."""
    prettier = shutil.which("prettier")
    if prettier is None:
        _unavailable("prettier is not on PATH")
    return _absolute_executable(prettier)


def resolve_node() -> str:
    """The `node` binary, when it is present and new enough to strip types off the emitted `.ts`."""
    node = shutil.which("node")
    if node is None:
        _unavailable("node is not on PATH")
    reported = subprocess.run([node, "--version"], capture_output=True, text=True, check=False)  # ruff: ignore[subprocess-without-shell-equals-true]
    if reported.returncode != 0:
        _unavailable(f"`node --version` failed: {reported.stderr.strip()}")
    parts = reported.stdout.strip().lstrip("v").split(".")
    version = tuple(int(part) for part in parts[:2] if part.isdigit())
    if len(version) != 2 or version < NODE_TYPE_STRIPPING_MINIMUM:
        minimum = ".".join(str(part) for part in NODE_TYPE_STRIPPING_MINIMUM)
        _unavailable(f"node {reported.stdout.strip()} cannot strip types (needs >= {minimum})")
    return _absolute_executable(node)


def resolve_zod_package() -> Path:
    """The `zod` package directory to symlink into a driver's `node_modules`.

    Two sources, in order: the path `make test-ts-gates` provisions and names in the environment, then a
    global npm install — which is what a developer who ran `npm install -g zod` already has.
    """
    provisioned = os.environ.get(ZOD_PACKAGE_ENV, "").strip()
    if provisioned:
        # Fully resolved rather than merely absolute: this becomes a symlink *target*, and a relative one
        # would be read from the link's own parent — a dangling link reported as a missing `zod` module.
        package = Path(provisioned).resolve()
        if not (package / "package.json").is_file():
            _unavailable(f"{ZOD_PACKAGE_ENV} points at {package}, which holds no package.json")
        return package
    npm = shutil.which("npm")
    if npm is None:
        _unavailable("npm is not on PATH, so there is no global zod to find")
    reported = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, check=False)  # ruff: ignore[subprocess-without-shell-equals-true]
    if reported.returncode != 0:
        _unavailable(f"`npm root -g` failed: {reported.stderr.strip()}")
    package = (Path(reported.stdout.strip()) / "zod").resolve()
    if not (package / "package.json").is_file():
        _unavailable("no globally installed zod to link against")
    return package
