from pathlib import Path

from pipelex.cli.commands.validate._validate_core import do_validate_all_libraries_and_dry_run  # noqa: PLC2701


class TestValidateCommand:
    def test_validate_all(self):
        do_validate_all_libraries_and_dry_run(library_dirs=[Path()])
