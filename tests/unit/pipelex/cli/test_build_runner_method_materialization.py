"""Unit tests: `build runner method` on a fetched target embeds only paths that survive process exit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.cli.commands.build.runner.method_cmd import build_runner_method_cmd

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

RUNNER_METHOD_MODULE = "pipelex.cli.commands.build.runner.method_cmd"


class TestBuildRunnerMethodMaterialization:
    """The generated runner embeds its library dir — for a fetched target that dir must outlive the clone."""

    def _patch_method(self, mocker: MockerFixture, *, method_dir: Path, fetched: bool) -> Any:
        """Create a real method package at *method_dir*, patch resolution; return the execute_prepare_runner mock."""
        method_dir.mkdir(parents=True, exist_ok=True)
        bundle_file = method_dir / "core.mthds"
        bundle_file.write_text("# placeholder", encoding="utf-8")

        method_mock = mocker.MagicMock()
        method_mock.name = "remote_method"
        method_mock.path = method_dir
        method_mock.mthds_files = [bundle_file]
        method_mock.provenance = mocker.MagicMock() if fetched else None
        mocker.patch(
            f"{RUNNER_METHOD_MODULE}.resolve_method_target",
            return_value=("my_pipe", [str(method_dir)], method_mock),
        )
        return mocker.patch(f"{RUNNER_METHOD_MODULE}.execute_prepare_runner")

    def test_fetched_method_is_materialized_beside_the_script(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A fetched target's package is copied beside the generated runner, and only the copy is referenced."""
        clone_dir = tmp_path / "mthds_remote_clone"
        prepare_mock = self._patch_method(mocker, method_dir=clone_dir, fetched=True)
        output_file = tmp_path / "out" / "run_my_pipe.py"

        build_runner_method_cmd(name="github.com/test/remote-method", output_path=str(output_file))

        materialized_dir = output_file.parent / "remote_method"
        assert (materialized_dir / "core.mthds").is_file()
        kwargs = prepare_mock.call_args.kwargs
        assert kwargs["bundle_path"] == materialized_dir / "core.mthds"
        assert kwargs["library_dirs"] == [materialized_dir]
        assert not kwargs["bundle_path"].is_relative_to(clone_dir)
        assert not kwargs["library_dirs"][0].is_relative_to(clone_dir)

    def test_fetched_materialization_excludes_git_metadata(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The clone's .git directory is not copied into the materialized package."""
        clone_dir = tmp_path / "mthds_remote_clone"
        self._patch_method(mocker, method_dir=clone_dir, fetched=True)
        (clone_dir / ".git").mkdir()
        (clone_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        output_file = tmp_path / "out" / "run_my_pipe.py"

        build_runner_method_cmd(name="github.com/test/remote-method", output_path=str(output_file))

        materialized_dir = output_file.parent / "remote_method"
        assert (materialized_dir / "core.mthds").is_file()
        assert not (materialized_dir / ".git").exists()

    def test_installed_method_is_not_copied(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """An installed method (no provenance) is referenced in place — no copy is made."""
        method_dir = tmp_path / "installed-method"
        prepare_mock = self._patch_method(mocker, method_dir=method_dir, fetched=False)
        output_file = tmp_path / "out" / "run_my_pipe.py"

        build_runner_method_cmd(name="my-method", output_path=str(output_file))

        kwargs = prepare_mock.call_args.kwargs
        assert kwargs["bundle_path"] == method_dir / "core.mthds"
        assert kwargs["library_dirs"] == [method_dir]
        assert not (output_file.parent / "remote_method").exists()
