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


def resolve_prettier() -> str:
    """The `prettier` binary the formatting gate runs, from PATH."""
    prettier = shutil.which("prettier")
    if prettier is None:
        _unavailable("prettier is not on PATH")
    return prettier


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
    return node


def resolve_zod_package() -> Path:
    """The `zod` package directory to symlink into a driver's `node_modules`.

    Two sources, in order: the path `make test-ts-gates` provisions and names in the environment, then a
    global npm install — which is what a developer who ran `npm install -g zod` already has.
    """
    provisioned = os.environ.get(ZOD_PACKAGE_ENV, "").strip()
    if provisioned:
        package = Path(provisioned)
        if not (package / "package.json").is_file():
            _unavailable(f"{ZOD_PACKAGE_ENV} points at {package}, which holds no package.json")
        return package
    npm = shutil.which("npm")
    if npm is None:
        _unavailable("npm is not on PATH, so there is no global zod to find")
    reported = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, check=False)  # ruff: ignore[subprocess-without-shell-equals-true]
    if reported.returncode != 0:
        _unavailable(f"`npm root -g` failed: {reported.stderr.strip()}")
    package = Path(reported.stdout.strip()) / "zod"
    if not (package / "package.json").is_file():
        _unavailable("no globally installed zod to link against")
    return package
