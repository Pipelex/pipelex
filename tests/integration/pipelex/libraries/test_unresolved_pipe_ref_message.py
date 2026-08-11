"""The message a user meets when a bare in-body pipe ref stops resolving.

This is the migration path for the whole owner-domain change, so it is worth a test of its own. The
hard part is that the ref named in the error is not the ref the author typed: they wrote a bare code
and the compiler qualified it to their own domain. A message that only names the qualified ref points
at a pipe that appears nowhere in their file, and reads like a compiler bug rather than a fix list.

Both branches matter — with a candidate elsewhere in the library, and with none — because the
suggestion arm is the one that comes from a crate-wide scan, and that scan must stay strictly on the
failure path. It suggests; it never resolves.
"""

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.exceptions import LibraryLoadingError

_SIBLING_DOMAIN_MTHDS = """
domain = "orchestrator"
description = "Calls a pipe that lives in another domain, by bare code."

[pipe.run_all]
type = "PipeSequence"
description = "Runs the presentation step."
inputs = { data = "Text" }
output = "Text"
steps = [{ pipe = "present_as_markdown", result = "presented" }]
"""

_PRESENTATION_MTHDS = """
domain = "presentation"
description = "Owns the presenter."

[pipe.present_as_markdown]
type = "PipeLLM"
description = "Present as markdown."
inputs = { data = "Text" }
output = "Text"
prompt = "Present $data as markdown"
"""

_NO_CANDIDATE_MTHDS = """
domain = "orchestrator"
description = "Calls a pipe that exists nowhere at all."

[pipe.run_all]
type = "PipeSequence"
description = "Runs a step that does not exist."
inputs = { data = "Text" }
output = "Text"
steps = [{ pipe = "nowhere_to_be_found", result = "presented" }]
"""


class TestUnresolvedPipeRefMessage:
    def _load_and_capture(self, *, sources: dict[str, str], load_test_library: Callable[[list[Path]], None]) -> str:
        with tempfile.TemporaryDirectory() as tmp_dir:
            for name, text in sources.items():
                (Path(tmp_dir) / name).write_text(text, encoding="utf-8")
            with pytest.raises(LibraryLoadingError) as exc_info:
                load_test_library([Path(tmp_dir)])
            return str(exc_info.value)

    def test_names_the_qualified_ref_and_explains_the_rule(self, load_test_library: Callable[[list[Path]], None]):
        """The author wrote `present_as_markdown`; the compiler tried `orchestrator.present_as_markdown`.

        Saying only the second is what makes this look like a compiler bug, so the message has to
        carry both plus the rule that connects them.
        """
        message = self._load_and_capture(
            sources={"orchestrator.mthds": _SIBLING_DOMAIN_MTHDS, "presentation.mthds": _PRESENTATION_MTHDS},
            load_test_library=load_test_library,
        )
        assert "orchestrator.present_as_markdown" in message
        assert "present_as_markdown" in message
        assert "own domain" in message

    def test_suggests_the_sibling_that_actually_declares_the_code(self, load_test_library: Callable[[list[Path]], None]):
        """The fix is one qualified spelling away, so the message says which one."""
        message = self._load_and_capture(
            sources={"orchestrator.mthds": _SIBLING_DOMAIN_MTHDS, "presentation.mthds": _PRESENTATION_MTHDS},
            load_test_library=load_test_library,
        )
        assert "presentation.present_as_markdown" in message

    def test_no_candidate_means_no_suggestion(self, load_test_library: Callable[[list[Path]], None]):
        """A plain typo gets the rule but no invented fix.

        The suggestion arm reads a crate-wide scan; with nothing to find it must stay silent rather
        than pad the message. This is also the branch that proves the scan is consulted per failure
        rather than assumed non-empty.
        """
        message = self._load_and_capture(
            sources={"orchestrator.mthds": _NO_CANDIDATE_MTHDS},
            load_test_library=load_test_library,
        )
        assert "orchestrator.nowhere_to_be_found" in message
        assert "did you mean" not in message.lower()

    def test_two_domains_declaring_the_same_code_each_bind_their_own(self, load_test_library: Callable[[list[Path]], None]):
        """The end-to-end payoff, through the real load path: same bare code, two domains, no ambiguity.

        Under the deleted crate-wide search this library did not load at all — the bare ref matched
        two pipes and the lookup raised. Now each domain's ref means that domain's pipe, so adding a
        `present_as_markdown` somewhere else cannot change what an existing method does.
        """
        second_presenter = _PRESENTATION_MTHDS.replace('domain = "presentation"', 'domain = "alt_presentation"')
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / "presentation.mthds").write_text(_PRESENTATION_MTHDS, encoding="utf-8")
            (Path(tmp_dir) / "alt_presentation.mthds").write_text(second_presenter, encoding="utf-8")
            (Path(tmp_dir) / "caller.mthds").write_text(
                _SIBLING_DOMAIN_MTHDS.replace('domain = "orchestrator"', 'domain = "presentation"').replace("[pipe.run_all]", "[pipe.run_all_here]"),
                encoding="utf-8",
            )
            load_test_library([Path(tmp_dir)])

            library = get_library_manager().get_current_library()
            sequence = library.pipe_library.get_required_pipe("presentation.run_all_here")
            assert sequence.pipe_dependencies() == {"presentation.present_as_markdown"}
