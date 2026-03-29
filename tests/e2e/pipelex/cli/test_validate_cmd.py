from pathlib import Path

from pipelex.cli.commands.validate._validate_core import do_validate_all_libraries_and_dry_run  # noqa: PLC2701


class TestValidateCommand:
    def test_validate_all(self):
        # Scan from the pipelex package directory, not CWD, to avoid picking up
        # test fixture .mthds files that conflict with each other (e.g. phase1
        # hierarchical domain fixtures with cross-domain refs but no METHODS.toml)
        do_validate_all_libraries_and_dry_run(library_dirs=[Path("pipelex")])
