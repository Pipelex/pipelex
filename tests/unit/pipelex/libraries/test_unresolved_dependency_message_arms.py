"""The guarded arms of ``_describe_unresolved_pipe_dependency`` that the integration pins skip.

``test_unresolved_pipe_ref_message.py`` covers the bare-qualified, suggestion, no-candidate, and
malformed arms through real library loads. Two arms remained unpinned, and both exist to STOP the
message from telling a fiction:

- a lookup failure that is not a miss (an ambiguous cross-package code) must hand back the real
  cause, not a well-written "does not exist";
- a ref the author explicitly qualified to ANOTHER domain was never rewritten, so the
  qualification-rule explanation and the candidate suggestion must both stay silent for it.
"""

from pipelex.libraries.library import (
    _describe_unresolved_pipe_dependency,  # pyright: ignore[reportPrivateUsage]
)
from pipelex.libraries.pipe.exceptions import PipeLibraryError, PipeNotFoundError


class TestUnresolvedDependencyMessageArms:
    def test_non_miss_cause_hands_back_the_real_reason(self):
        """An ambiguity is not a miss: no 'does not exist', no qualification story — the cause verbatim."""
        cause = PipeLibraryError(
            "Pipe code 'helper' is ambiguous — it is declared by ['dep->a.helper', 'dep->b.helper']. Name one of them explicitly."
        )
        msg = _describe_unresolved_pipe_dependency(
            referring_pipe_ref="orchestrator.run_all",
            missing_ref="dep->helper",
            candidates={"helper": ["orchestrator.helper"]},
            cause=cause,
        )
        assert "does not exist" not in msg
        assert "resolves inside its own domain" not in msg
        assert "could not resolve its dependency 'dep->helper'" in msg
        assert "is ambiguous" in msg

    def test_author_qualified_other_domain_gets_no_rewrite_story(self):
        """A ref explicitly written to another domain was never rewritten — no rule text, no suggestion."""
        cause = PipeNotFoundError("Pipe 'beta.typo_pipe' not found")
        msg = _describe_unresolved_pipe_dependency(
            referring_pipe_ref="alpha.run_all",
            missing_ref="beta.typo_pipe",
            candidates={"typo_pipe": ["gamma.typo_pipe"]},
            cause=cause,
        )
        assert msg.startswith("Pipe 'alpha.run_all' references 'beta.typo_pipe', which does not exist.")
        assert "resolves inside its own domain" not in msg
        assert "did you mean" not in msg

    def test_cross_package_ref_gets_the_plain_sentence_only(self):
        """An `alias->…` ref is untouched by the pass, so the message must not explain a rewrite."""
        cause = PipeNotFoundError("Pipe 'dep->beta.helper' not found")
        msg = _describe_unresolved_pipe_dependency(
            referring_pipe_ref="alpha.run_all",
            missing_ref="dep->beta.helper",
            candidates={"helper": ["alpha.helper"]},
            cause=cause,
        )
        assert msg == "Pipe 'alpha.run_all' references 'dep->beta.helper', which does not exist."
