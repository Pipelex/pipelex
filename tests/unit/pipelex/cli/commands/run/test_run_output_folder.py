import json
from pathlib import Path

import pytest
from mthds.method_tree.digest import tree_listing
from mthds.method_tree.lister import list_method_tree

from pipelex.cli.commands.run._run_output_folder import (
    METHOD_TREE_RECORD_NAME,
    bundle_run_outputs_dir,
    make_run_output_folder,
    run_output_label,
    write_method_tree_record,
)


class TestRunOutputFolder:
    def test_two_consecutive_runs_leave_the_method_tree_unchanged(self, tmp_path: Path) -> None:
        """A run writing its outputs inside the method's folder, as from the method's own directory, never adds to its tree."""
        (tmp_path / "main.mthds").write_text("domain = 'run_folder_tests'\n", encoding="utf-8")
        before = list_method_tree(tmp_path)

        for _ in range(2):
            output_path = make_run_output_folder(output_dir=tmp_path / "results", label="summarize")
            (output_path / "main_stuff.json").write_text("{}", encoding="utf-8")
            write_method_tree_record(output_path=output_path, method_tree=before)

        after = list_method_tree(tmp_path)
        assert sorted(path.name for path in (tmp_path / "results").iterdir()) == ["summarize_output_01", "summarize_output_02"]
        assert tree_listing(after.files) == tree_listing(before.files)
        assert after.digest == before.digest

    def test_the_record_names_the_tree_the_run_read(self, tmp_path: Path) -> None:
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        (method_dir / "main.mthds").write_text("domain = 'run_folder_tests'\n", encoding="utf-8")
        method_tree = list_method_tree(method_dir)
        output_path = make_run_output_folder(output_dir=tmp_path / "results", label="summarize")

        record_path = write_method_tree_record(output_path=output_path, method_tree=method_tree)

        assert record_path == output_path / METHOD_TREE_RECORD_NAME
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record["digest"] == method_tree.digest
        assert record["root"] == str(method_tree.directory)
        assert record["is_one_file"] is False
        assert record["files"] == [{"path": "main.mthds", "sha256": method_tree.files[0].sha256, "size": method_tree.files[0].size}]
        assert (output_path / ".gitignore").read_text(encoding="utf-8").splitlines()[-1] == "*"

    @pytest.mark.parametrize(
        ("pipe_ref", "expected_label"),
        [
            ("summarize", "summarize"),
            ("report.summarize", "summarize"),
            ("scoring->report.summarize", "summarize"),
            ("scoring->summarize", "summarize"),
        ],
    )
    def test_a_run_folder_is_labelled_by_the_pipe_s_own_code(self, pipe_ref: str, expected_label: str) -> None:
        """A pipe named with its domain, or through a dependency's alias, labels its folder as its bare code does, locally or hosted."""
        assert run_output_label(pipe_ref=pipe_ref) == expected_label

    @pytest.mark.parametrize(
        ("target", "pipe_override", "entry_bundle", "expected_outputs_dir"),
        [
            ("method/bundle.mthds", None, None, "method/results"),
            ("method/parts/extra.mthds", "wave", None, "method/parts/results"),
            ("method", None, "method/bundle.mthds", "method/results"),
            ("method", None, "method/parts/extra.mthds", "method/parts/results"),
            ("method", "graph_folder_probe.wave", "method/parts/extra.mthds", "method/results"),
            ("method", "wave", None, "method/results"),
        ],
    )
    def test_a_bundle_run_writes_beside_the_bundle_it_starts_in_else_in_the_folder_named(
        self,
        tmp_path: Path,
        target: str,
        pipe_override: str | None,
        entry_bundle: str | None,
        expected_outputs_dir: str,
    ) -> None:
        """A file writes beside itself, a folder beside its entry bundle, and a folder whose pipe is named in the folder itself."""
        (tmp_path / "method" / "parts").mkdir(parents=True)
        for bundle_name in ("method/bundle.mthds", "method/parts/extra.mthds"):
            (tmp_path / bundle_name).write_text("domain = 'run_folder_tests'\n", encoding="utf-8")

        outputs_dir = bundle_run_outputs_dir(
            target_path=tmp_path / target,
            pipe_override=pipe_override,
            entry_bundle_file=tmp_path / entry_bundle if entry_bundle else None,
        )

        assert outputs_dir == tmp_path / expected_outputs_dir
