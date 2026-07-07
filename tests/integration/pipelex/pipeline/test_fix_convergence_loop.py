"""Integration tests for the fix convergence loop — validate → apply SAFE fixes → re-validate.

The loop reuses ``validate_bundle`` wholesale (no parallel validation pipeline). Cascades are
expected: fixing an inner sequence's output can surface the outer sequence's mismatch on the
next iteration — the loop is the design, not a fallback.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.pipeline.fixes.fix_loop import fix_bundle_file

_SINGLE_PASS_MTHDS = """domain = "seqfix_loop_single"
main_pipe = "list_ideas"

[concept]
Idea = "An idea."

[pipe.gen_ideas]
type = "PipeLLM"
description = "Generate ideas."
inputs = { topic = "Text" }
output = "Idea[]"
prompt = "Generate ideas about $topic"

# Wrong on purpose: the sequence declares a single Idea while the last step yields a list.
[pipe.list_ideas]
type = "PipeSequence"
description = "Sequence declaring a single output while the last step yields a list."
inputs = { topic = "Text" }
output = "Idea"
steps = [
  { pipe = "gen_ideas", result = "ideas" },
]
"""

_CASCADE_MTHDS = """domain = "seqfix_loop_cascade"
main_pipe = "outer"

[concept]
Idea = "An idea."

[pipe.gen_ideas]
type = "PipeLLM"
description = "Generate ideas."
inputs = { topic = "Text" }
output = "Idea[]"
prompt = "Generate ideas about $topic"

# Both sequences are wrong on purpose. The outer's declared output matches the inner's
# declared (wrong) output, so only the inner error surfaces on the first validation;
# fixing the inner surfaces the outer mismatch on the second iteration.
[pipe.inner]
type = "PipeSequence"
description = "Inner sequence with the wrong output."
inputs = { topic = "Text" }
output = "Idea"
steps = [
  { pipe = "gen_ideas", result = "ideas" },
]

[pipe.outer]
type = "PipeSequence"
description = "Outer sequence matching the inner's wrong declared output."
inputs = { topic = "Text" }
output = "Idea"
steps = [
  { pipe = "inner", result = "ideas" },
]
"""


_INPUTS_DRIFT_MTHDS = """domain = "inputsfix_loop"
main_pipe = "make_summary"

[concept]
Summary = "A summary of a text."

[pipe.write_summary]
type = "PipeLLM"
description = "Summarize the text."
inputs = { text = "Text", style = "Text" }
output = "Summary"
prompt = "Summarize $text in style $style"

# Drifted on purpose: wrong concept for text, extraneous note, missing style.
[pipe.make_summary]
type = "PipeSequence"
description = "Sequence with drifted inputs."
inputs = { text = "Number", note = "Text" }
output = "Summary"
steps = [
  { pipe = "write_summary", result = "summary" },
]
"""

_CROSS_RULE_CASCADE_MTHDS = """domain = "crossfix_loop"
main_pipe = "list_ideas"

[concept]
Idea = "An idea."

[pipe.gen_ideas]
type = "PipeLLM"
description = "Generate ideas."
inputs = { topic = "Text" }
output = "Idea[]"
prompt = "Generate ideas about $topic"

# Both wrong on purpose: the sequence misses its needed input AND declares the wrong
# output. Inputs are validated before outputs, so the input error masks the output error
# until the first fix lands — a natural cross-rule cascade on one pipe.
[pipe.list_ideas]
type = "PipeSequence"
description = "Sequence with drifted inputs and the wrong output."
output = "Idea"
steps = [
  { pipe = "gen_ideas", result = "ideas" },
]
"""


@pytest.mark.asyncio(loop_scope="class")
class TestFixConvergenceLoop:
    async def test_single_iteration_fixes_and_revalidates(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """One apply round fixes the sequence output; the re-validation verdict is valid."""
        load_empty_library()
        bundle_path = tmp_path / "single.mthds"
        bundle_path.write_text(_SINGLE_PASS_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path)

        assert result.is_valid is True
        assert result.iterations == 1
        assert [fix.fix_code for fix in result.fixes_applied] == ["match-sequence-output"]
        assert result.remaining_errors == []
        assert result.bail_reason is None
        assert 'output = "Idea[]"' in bundle_path.read_text(encoding="utf-8")

    async def test_cascade_needs_two_iterations(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Fixing the inner sequence surfaces the outer mismatch; two apply rounds converge."""
        load_empty_library()
        bundle_path = tmp_path / "cascade.mthds"
        bundle_path.write_text(_CASCADE_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path)

        assert result.is_valid is True
        assert result.iterations == 2
        assert [fix.fix_code for fix in result.fixes_applied] == ["match-sequence-output", "match-sequence-output"]
        assert result.bail_reason is None
        fixed_text = bundle_path.read_text(encoding="utf-8")
        # Both sequences now declare the list output.
        assert fixed_text.count('output = "Idea[]"') == 3  # gen_ideas + inner + outer

    async def test_controller_inputs_drift_fixed_in_one_iteration(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """One sync-controller-inputs fix repairs add + update + delete drift in one round."""
        load_empty_library()
        bundle_path = tmp_path / "inputs_drift.mthds"
        bundle_path.write_text(_INPUTS_DRIFT_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path)

        assert result.is_valid is True
        assert result.iterations == 1
        assert [fix.fix_code for fix in result.fixes_applied] == ["sync-controller-inputs"]
        assert result.remaining_errors == []
        assert result.bail_reason is None
        fixed_text = bundle_path.read_text(encoding="utf-8")
        assert 'inputs = { text = "Text", style = "Text" }' in fixed_text
        assert 'note = "Text"' not in fixed_text

    async def test_cross_rule_cascade_inputs_then_output(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """The input error masks the output error; two rounds apply the two different rules."""
        load_empty_library()
        bundle_path = tmp_path / "cross_rule.mthds"
        bundle_path.write_text(_CROSS_RULE_CASCADE_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path)

        assert result.is_valid is True
        assert result.iterations == 2
        assert [fix.fix_code for fix in result.fixes_applied] == ["sync-controller-inputs", "match-sequence-output"]
        assert result.bail_reason is None
        fixed_text = bundle_path.read_text(encoding="utf-8")
        assert 'inputs = { topic = "Text" }' in fixed_text
        assert fixed_text.count('output = "Idea[]"') == 2

    async def test_already_valid_bundle_is_a_no_op(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A valid bundle needs no apply round: zero iterations, zero fixes, bytes untouched."""
        load_empty_library()
        bundle_path = tmp_path / "valid.mthds"
        valid_text = _SINGLE_PASS_MTHDS.replace('output = "Idea"\n', 'output = "Idea[]"\n')
        bundle_path.write_text(valid_text, encoding="utf-8")

        result = await fix_bundle_file(bundle_path)

        assert result.is_valid is True
        assert result.iterations == 0
        assert result.fixes_applied == []
        assert bundle_path.read_text(encoding="utf-8") == valid_text
