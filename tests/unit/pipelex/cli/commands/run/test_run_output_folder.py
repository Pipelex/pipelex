import json
from pathlib import Path

from mthds.method_tree.digest import tree_listing
from mthds.method_tree.lister import list_method_tree

from pipelex.cli.commands.run._run_output_folder import METHOD_TREE_RECORD_NAME, make_run_output_folder, write_method_tree_record


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
