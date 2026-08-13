"""A hand-typed bare pipe code still works at the CLI, end to end.

A perfectly-tested affordance can still be perfectly mis-called. The unit tests around
`get_optional_entry_pipe` prove the affordance behaves; these prove the commands actually reach it,
against a real loaded library rather than a mock. `pipelex which summarize_it` is precisely the
invocation the affordance exists to preserve while in-body resolution became strict, so if a command
were left on the strict lookup, the affordance would be right and the product still broken.

The sibling-domain case is the discriminating one: it is where the entry affordance and in-body
resolution genuinely disagree, so it fails if a command is wired to the wrong door.
"""

import tempfile
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from pipelex.cli.commands.show_cmd import do_show_pipe
from pipelex.cli.commands.which_cmd import do_which_pipe
from pipelex.libraries.pipe.exceptions import PipeNotFoundError

_TWO_DOMAIN_MTHDS = """
domain = "reporting"
description = "Owns the summarizer."

[pipe.summarize_it]
type = "PipeLLM"
description = "Summarize the input."
inputs = { doc = "Text" }
output = "Text"
prompt = "Summarize $doc"
"""

_CALLER_MTHDS = """
domain = "orchestration"
description = "A second domain, so a bare code is not trivially unique to one."

[pipe.kick_off]
type = "PipeLLM"
description = "Does its own thing."
inputs = { doc = "Text" }
output = "Text"
prompt = "Do something with $doc"
"""


@pytest.fixture
def two_domain_dir(load_test_library: Callable[[list[Path]], None]) -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        library_dir = Path(tmp_dir)
        (library_dir / "reporting.mthds").write_text(_TWO_DOMAIN_MTHDS, encoding="utf-8")
        (library_dir / "orchestration.mthds").write_text(_CALLER_MTHDS, encoding="utf-8")
        load_test_library([library_dir])
        yield library_dir


class TestEntryBareCodeCommands:
    def test_which_resolves_a_bare_code_from_another_domain(self, two_domain_dir: Path):
        """`pipelex which summarize_it` — the user is pointing at a pipe, not writing a reference."""
        assert do_which_pipe(pipe_code="summarize_it", library_dirs=[two_domain_dir], source_label="test")

    @pytest.mark.usefixtures("two_domain_dir")
    def test_show_resolves_a_bare_code_from_another_domain(self):
        do_show_pipe(pipe_code="summarize_it")

    @pytest.mark.usefixtures("two_domain_dir")
    def test_qualified_code_still_works(self):
        do_show_pipe(pipe_code="reporting.summarize_it")

    @pytest.mark.usefixtures("two_domain_dir")
    def test_unknown_bare_code_still_reports_not_found(self):
        with pytest.raises(PipeNotFoundError):
            do_show_pipe(pipe_code="no_such_pipe_anywhere")
