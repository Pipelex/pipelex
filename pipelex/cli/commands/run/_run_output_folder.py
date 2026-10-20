"""The folder a `pipelex run` writes its outputs to, kept out of every method tree, and the record of the tree it ran.

A run writes its outputs to a new numbered folder, `<label>_output_<NN>`, under `--output-dir` for `pipelex run`, and
under `results/` beside the bundle it ran for `pipelex-agent run`; `pipelex-agent validate bundle --graph` writes its
graph files to such a folder too, under `results/` beside the bundle it drew. That folder often
lies inside a method's folder, the working directory being the method's, so the run writes a `.gitignore` holding `*`
into it: the membership rule honours the tree's `.gitignore` files as git does (`mthds/docs/spec/method-tree.md`), so
none of a run's outputs, nor the `.gitignore` itself, ever joins the tree, and a second run of the method reads the
same tree, with the same digest, as the first.

A local run also records there the method tree it read, as `method_tree.json`: its digest, which names the exact files
the run read, and the files themselves, by tree path, hash and size.
"""

import json
from pathlib import Path

from mthds.method_tree.models import MethodTree

from pipelex.tools.misc.file_utils import get_incremental_directory_path

RUN_OUTPUT_GITIGNORE_NAME = ".gitignore"
RUN_OUTPUT_GITIGNORE_CONTENT = "# Written by pipelex: what a run or a validation writes here is never part of a method.\n*\n"
METHOD_TREE_RECORD_NAME = "method_tree.json"
#: The directory `pipelex-agent run` creates its output folders under, beside the bundle it ran, as `validate bundle --graph` does.
RUN_RESULTS_DIR_NAME = "results"


def run_output_label(*, pipe_ref: str) -> str:
    """The label a run's output folder takes from the pipe it ran: the pipe's own code, without its domain or alias.

    A pipe named as `domain.pipe_code`, or as `alias->domain.pipe_code` for a dependency's, labels its folder by
    `pipe_code`, as a pipe named by its bare code does.
    """
    return pipe_ref.rsplit("->", 1)[-1].rsplit(".", 1)[-1]


def make_run_output_folder(*, output_dir: Path, label: str) -> Path:
    """Create the next numbered output folder for a run under `output_dir`, holding a `.gitignore` that ignores it all."""
    output_path = get_incremental_directory_path(output_dir, base_name=f"{label}_output")
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / RUN_OUTPUT_GITIGNORE_NAME).write_text(RUN_OUTPUT_GITIGNORE_CONTENT, encoding="utf-8")
    return output_path


def method_tree_record(*, method_tree: MethodTree) -> dict[str, object]:
    """The record of the method tree a run read: its digest, its root on this host, its entry, and its files."""
    return {
        "digest": method_tree.digest,
        "root": str(method_tree.directory) if method_tree.directory is not None else None,
        "is_one_file": method_tree.is_one_file,
        "entry": method_tree.entry,
        "files": [{"path": tree_file.path, "sha256": tree_file.sha256, "size": tree_file.size} for tree_file in method_tree.files],
    }


def write_method_tree_record(*, output_path: Path, method_tree: MethodTree) -> Path:
    """Write `method_tree.json` into a run's output folder, and return its path."""
    record_path = output_path / METHOD_TREE_RECORD_NAME
    record_path.write_text(json.dumps(method_tree_record(method_tree=method_tree), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record_path
