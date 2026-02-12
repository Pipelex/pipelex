from pathlib import Path

import pytest

from pipelex.cli.commands.validate_cmd import do_validate_all_libraries_and_dry_run
from pipelex.libraries.exceptions import LibraryLoadingError


class TestValidateCommand:
    @pytest.mark.xfail(
        reason="Package visibility enforcement picks up refactoring/test-package-fixtures/ which contains intentional visibility violations",
        raises=LibraryLoadingError,
    )
    def test_validate_all(self):
        do_validate_all_libraries_and_dry_run(library_dirs=[Path()])
