from pathlib import Path

import pytest

from pipelex.migration.exceptions import FunctionNamesMigrationError
from pipelex.migration.function_names import migrate_function_names, migrate_function_names_in_directory
from pipelex.pipe_operators.func.function_name import function_name_form_violation

_MARKED_TOTALS = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def compute_totals(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="total")


def helper() -> int:
    return 1
"""

_NAMED_MARKER = """\
from pipelex.system.registries import func_registry


@func_registry.pipe_func(name="invoice_summary")
def summarize(working_memory):
    return working_memory
"""

_BUNDLE = """\
domain = "invoicing"

# The totals, computed in Python
[pipe.totals]
type          = "PipeFunc"   # aligned on purpose
description   = "Compute the totals"
output        = "Text"
function_name = "compute_totals"

[pipe.summary]
type          = "PipeFunc"
description   = "Summarize the invoice"
output        = "Text"
function_name = "invoice_summary"

[pipe.already]
type          = "PipeFunc"
description   = "Already an import path"
output        = "Text"
function_name = "funcs.totals.compute_totals"

[pipe.write]
type        = "PipeLLM"
description = "Not a PipeFunc"
output      = "Text"
prompt      = "compute_totals"
"""


class TestFunctionNamesMigration:
    def test_flat_names_become_import_paths_and_markers_lose_their_name(self) -> None:
        migration = migrate_function_names(
            files={"invoicing.mthds": _BUNDLE, "funcs/totals.py": _MARKED_TOTALS, "funcs/summary/__init__.py": _NAMED_MARKER},
        )

        assert migration.is_complete
        assert [(rewrite.pipe_code, rewrite.flat_name, rewrite.import_path) for rewrite in migration.rewrites] == [
            ("totals", "compute_totals", "funcs.totals.compute_totals"),
            ("summary", "invoice_summary", "funcs.summary.summarize"),
        ]
        assert [(removal.module, removal.function, removal.registered_name) for removal in migration.marker_removals] == [
            ("funcs/summary/__init__.py", "summarize", "invoice_summary"),
        ]
        assert sorted(migration.changed_files) == ["funcs/summary/__init__.py", "invoicing.mthds"]
        rewritten_bundle = migration.changed_files["invoicing.mthds"]
        assert rewritten_bundle == _BUNDLE.replace('"compute_totals"\n', '"funcs.totals.compute_totals"\n', 1).replace(
            '"invoice_summary"', '"funcs.summary.summarize"'
        )
        assert "# The totals, computed in Python" in rewritten_bundle
        assert 'type          = "PipeFunc"   # aligned on purpose' in rewritten_bundle
        assert migration.changed_files["funcs/summary/__init__.py"] == _NAMED_MARKER.replace('(name="invoice_summary")', "()")
        for rewrite in migration.rewrites:
            assert function_name_form_violation(function_name=rewrite.import_path) is None

    @pytest.mark.parametrize(
        ("files", "expected_reason", "expected_candidates"),
        [
            pytest.param(
                {"funcs/totals.py": _MARKED_TOTALS.replace("@pipe_func()\n", "")},
                "No module of the method tree defines a @pipe_func function registered as 'compute_totals'",
                [],
                id="no-module-registers-the-name",
            ),
            pytest.param(
                {"funcs/totals.py": _MARKED_TOTALS, "funcs/other_totals.py": _MARKED_TOTALS},
                "More than one @pipe_func function of the method tree is registered as 'compute_totals'",
                ["funcs.other_totals.compute_totals", "funcs.totals.compute_totals"],
                id="two-modules-register-the-name",
            ),
            pytest.param(
                {"my-funcs/totals.py": _MARKED_TOTALS},
                "not an import path",
                [],
                id="the-module-has-no-import-path",
            ),
        ],
    )
    def test_a_name_that_cannot_be_resolved_is_left_and_reported(
        self, files: dict[str, str], expected_reason: str, expected_candidates: list[str]
    ) -> None:
        bundle = _BUNDLE.split("[pipe.summary]", maxsplit=1)[0]
        migration = migrate_function_names(files={"invoicing.mthds": bundle, **files})

        assert not migration.is_complete
        assert migration.rewrites == []
        assert "invoicing.mthds" not in migration.changed_files
        (unresolved,) = migration.unresolved
        assert unresolved.bundle == "invoicing.mthds"
        assert unresolved.pipe_code == "totals"
        assert unresolved.flat_name == "compute_totals"
        assert expected_reason in unresolved.reason
        assert unresolved.candidates == expected_candidates

    def test_a_bundle_that_does_not_parse_is_reported_without_a_step(self) -> None:
        broken_bundle = '[pipe.totals]\ntype = "PipeFunc"\nfunction_name = "compute_totals\n'
        migration = migrate_function_names(files={"broken.mthds": broken_bundle, "funcs/totals.py": _MARKED_TOTALS})

        assert not migration.is_complete
        (unresolved,) = migration.unresolved
        assert unresolved.bundle == "broken.mthds"
        assert unresolved.pipe_code is None
        assert unresolved.flat_name is None
        assert "does not parse as TOML" in unresolved.reason
        assert migration.changed_files == {}

    def test_a_bundle_that_does_not_parse_and_names_no_function_is_not_reported(self) -> None:
        migration = migrate_function_names(files={"broken.mthds": "domain = \n", "funcs/totals.py": _MARKED_TOTALS})

        assert migration.is_complete
        assert migration.unresolved == []

    def test_a_method_naming_only_import_paths_is_left_untouched(self) -> None:
        bundle = _BUNDLE.split("[pipe.already]")[1]
        migration = migrate_function_names(files={"invoicing.mthds": f"[pipe.already]{bundle}", "funcs/totals.py": _MARKED_TOTALS})

        assert migration.is_complete
        assert not migration.has_changes
        assert migration.changed_files == {}

    @pytest.mark.parametrize("is_dry_run", [True, False], ids=["dry-run", "write"])
    def test_a_method_folder_is_rewritten_unless_it_is_a_dry_run(self, tmp_path: Path, is_dry_run: bool) -> None:
        (tmp_path / "funcs").mkdir()
        (tmp_path / "invoicing.mthds").write_text(_BUNDLE, encoding="utf-8")
        (tmp_path / "funcs" / "totals.py").write_text(_MARKED_TOTALS, encoding="utf-8")
        (tmp_path / "funcs" / "summary.py").write_text(_NAMED_MARKER, encoding="utf-8")

        migration = migrate_function_names_in_directory(directory=tmp_path, is_dry_run=is_dry_run)

        assert migration.is_complete
        assert sorted(migration.changed_files) == ["funcs/summary.py", "invoicing.mthds"]
        on_disk = (tmp_path / "invoicing.mthds").read_text(encoding="utf-8")
        if is_dry_run:
            assert on_disk == _BUNDLE
        else:
            assert on_disk == migration.changed_files["invoicing.mthds"]
            assert (tmp_path / "funcs" / "summary.py").read_text(encoding="utf-8") == migration.changed_files["funcs/summary.py"]
        assert not list(tmp_path.rglob("__pycache__"))

    def test_a_folder_that_is_not_a_method_tree_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(FunctionNamesMigrationError):
            migrate_function_names_in_directory(directory=tmp_path / "missing", is_dry_run=True)
