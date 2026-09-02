"""Every `ts_toolchain` resolver must hand back an absolute path.

The callers use what they are given from somewhere else: the wire round-trip launches node with
`cwd=tmp_path`, and it symlinks the zod package into a `node_modules` under that same tmp directory. A
relative path survives the resolver's own checks — which run from the repository root — and then means
something different at the point of use. Both failure modes were reproduced before these tests existed:
`shutil.which("node")` under a relative `PATH` entry returns `bin/node` and `subprocess.run(cwd=…)` raises
`FileNotFoundError`, while a relative `PIPELEX_ZOD_PACKAGE` passes its `package.json` check and then
produces a symlink read relative to the *link's* parent, i.e. a dangling one, which surfaces as node
reporting that it cannot find the `zod` module.

Nothing here needs a real node toolchain — the executables are stubs — so these run in the ordinary CI
shards rather than only under `make test-ts-gates`.
"""

import stat
from pathlib import Path

import pytest

from tests.helpers.ts_toolchain import resolve_node, resolve_prettier, resolve_zod_package


def _stub_executable(*, directory: Path, name: str, prints: str) -> Path:
    """A stand-in binary on PATH, so the contract can be tested without a node toolchain."""
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / name
    executable.write_text(f"#!/bin/sh\necho '{prints}'\n", encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return executable


class TestTsToolchainResolversReturnAbsolutePaths:
    def test_resolve_prettier_absolutizes_a_relative_path_entry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _stub_executable(directory=tmp_path / "bin", name="prettier", prints="3.9.6")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PATH", "bin")

        assert Path(resolve_prettier()).is_absolute()

    def test_resolve_node_absolutizes_a_relative_path_entry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _stub_executable(directory=tmp_path / "bin", name="node", prints="v24.17.0")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PATH", "bin")

        # The version gate has to clear on the stub's answer before the path contract can be read at all.
        assert Path(resolve_node()).is_absolute()

    def test_resolve_zod_package_absolutizes_a_relative_env_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        package = tmp_path / "vendor" / "zod"
        package.mkdir(parents=True)
        (package / "package.json").write_text("{}", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PIPELEX_ZOD_PACKAGE", "vendor/zod")

        resolved = resolve_zod_package()

        assert resolved.is_absolute()
        # The point of absolutizing: the path still names the package once it is read from elsewhere.
        assert (resolved / "package.json").is_file()
