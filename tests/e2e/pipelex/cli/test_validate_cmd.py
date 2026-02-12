from pathlib import Path

from pipelex.cli.commands.validate_cmd import do_validate_all_libraries_and_dry_run


class TestValidateCommand:
    def test_validate_all(self):
        do_validate_all_libraries_and_dry_run(library_dirs=[Path()])
