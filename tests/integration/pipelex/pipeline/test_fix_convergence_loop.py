"""Integration tests for the fix convergence loop — validate → apply SAFE fixes → re-validate.

The loop reuses ``validate_bundle`` wholesale (no parallel validation pipeline). Cascades are
expected: fixing an inner sequence's output can surface the outer sequence's mismatch on the
next iteration — the loop is the design, not a fallback.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import tomlkit

from pipelex.pipeline.fixes.fix_loop import fix_bundle_file


def _pipes(bundle_path: Path) -> dict[str, Any]:
    """The fixed file's ``[pipe]`` table as plain data — asserting on parsed values, not raw
    whitespace, since the fix loop rewrites the whole file to canonical MTHDS (the formatter
    column-aligns single-line tables, so a hardcoded ``output = "x"`` spacing is not stable).
    """
    parsed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
    return cast("dict[str, Any]", parsed["pipe"])


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

_NATIVE_REDECL_MULTI_MTHDS = """domain = "nativefix_converge"
main_pipe = "greet"

[concept]
Greeting = "A greeting message."
# Both redeclare native concepts (illegal). The mode="before" validator raises on the first
# offending code per pass, so they converge one strip per iteration.
Text = "Redeclared native Text."
Number = "Redeclared native Number."

[pipe.greet]
type = "PipeLLM"
description = "Greet someone a number of times."
inputs = { name = "Text", count = "Number" }
output = "Greeting"
prompt = "Greet $name $count times"
"""

_STRIP_NAMESPACE_MTHDS = """domain = "nsfix_loop"
main_pipe = "nsfix_loop.run_seq"

# Over-qualified declaration key with the bundle's own domain (invalid); the qualified step ref
# below stays put (it still resolves to the bare pipe), so only the declaration and main_pipe strip.
[pipe."nsfix_loop.hello"]
type = "PipeLLM"
description = "Say hello."
output = "Text"
prompt = "Say hello"

[pipe.run_seq]
type = "PipeSequence"
description = "Run it."
output = "Text"
steps = [
  { pipe = "nsfix_loop.hello", result = "greeting" },
]
"""

# Cross-file collision pair: the target's dotted declaration would strip to a bare code already
# declared by a sibling bundle — the rename must not be applied. Same domain it would be a
# duplicate declaration; another domain it would be a bare-code ambiguity
# (``PipeLibrary.get_optional_pipe`` raises on a bare code declared by two domains). Either way
# the loop could never repair the state it would write.
_XFILE_TARGET_MTHDS = """domain = "nsfix_xfile"

[pipe."nsfix_xfile.hola"]
type = "PipeLLM"
description = "Say hola."
output = "Text"
prompt = "Say hola"
"""

_XFILE_SIBLING_SAME_DOMAIN_MTHDS = """domain = "nsfix_xfile"

[pipe.hola]
type = "PipeLLM"
description = "Bare hola, declared in a sibling bundle of the same domain."
output = "Text"
prompt = "Say hola"
"""

_XFILE_SIBLING_OTHER_DOMAIN_MTHDS = """domain = "nsfix_xfile_other"

[pipe.hola]
type = "PipeLLM"
description = "Bare hola in another domain."
output = "Text"
prompt = "Say hola"
"""

_XFILE_SIGNATURE_TARGET_MTHDS = """domain = "nsfix_xsig"

[pipe."nsfix_xsig.hello"]
type = "PipeLLM"
description = "Concrete hello whose same-domain prefix should be stripped."
inputs = { name = "Text" }
output = "Text"
prompt = "Say hello to $name"
"""

_XFILE_SIGNATURE_SIBLING_MTHDS = """domain = "nsfix_xsig"

[pipe.hello]
description = "Forward-declared hello signature."
inputs = { name = "Text" }
output = "Text"
"""

# Typo'd main_pipe tail: dotted, same-domain, valid snake tail — but NEITHER the dotted code nor
# the bare tail exists as a declaration key. The categorizer suppresses the enrichment, so the
# loop must apply nothing and leave the file byte-identical (checkpoint-C item 1, categorizer half).
_MAIN_PIPE_TYPO_TAIL_MTHDS = """domain = "nsfix_typo_loop"
main_pipe = "nsfix_typo_loop.helo"

[pipe.hello]
type = "PipeLLM"
description = "Say hello."
output = "Text"
prompt = "Say hello"
"""

# Convergent dotted-declaration main_pipe: the declaration's own rename materializes the bare
# target, so the paired main_pipe strip is safe and both land in one round.
_MAIN_PIPE_DOTTED_DECL_MTHDS = """domain = "nsfix_conv_loop"
main_pipe = "nsfix_conv_loop.hello"

[pipe."nsfix_conv_loop.hello"]
type = "PipeLLM"
description = "Say hello."
output = "Text"
prompt = "Say hello"
"""

# Two-file main_pipe orphan hazard (checkpoint-C item 1, fix-loop half — the PR #1031 cubic P2
# gap): the target's dotted declaration strips to a bare code declared by a SAME-DOMAIN sibling.
# The declaration rename is dropped as cross-file colliding — and the paired root ``main_pipe``
# set_key must be dropped WITH it, else iteration 1 writes an orphaned ``main_pipe = "hello"``
# to a file that never declares ``hello``.
_XFILE_MAIN_PIPE_TARGET_MTHDS = """domain = "nsfix_xmain"
main_pipe = "nsfix_xmain.hello"

[pipe."nsfix_xmain.hello"]
type = "PipeLLM"
description = "Say hello."
output = "Text"
prompt = "Say hello"
"""

_XFILE_MAIN_PIPE_SIBLING_MTHDS = """domain = "nsfix_xmain"

[pipe.hello]
type = "PipeLLM"
description = "Bare hello, declared in a sibling bundle of the same domain."
output = "Text"
prompt = "Say hello"
"""

_LOCAL_MAIN_PIPE_WITH_SIBLING_SAME_CODE_MTHDS = """domain = "nsfix_localmain"
main_pipe = "nsfix_localmain.hello"

[pipe.hello]
type = "PipeLLM"
description = "Local bare hello, already declared in this bundle."
output = "Text"
prompt = "Say hello"
"""

_LOCAL_MAIN_PIPE_SIBLING_SAME_CODE_MTHDS = """domain = "nsfix_localmain_other"

[pipe.hello]
type = "PipeLLM"
description = "Same bare code in another domain; should not block local main_pipe strip."
output = "Text"
prompt = "Say hello"
"""

# A sibling declaring an unrelated pipe code: must NOT block the rename (no over-dropping).
_XFILE_SIBLING_UNRELATED_MTHDS = """domain = "nsfix_xfile_other"

[pipe.adios]
type = "PipeLLM"
description = "Unrelated sibling pipe."
output = "Text"
prompt = "Say adios"
"""

# Multi-file cascade pair: the entry and a sibling library file EACH carry their own sequence
# output mismatch. Validation aborts at the first error per pass, so the loop must fix the
# sibling in the sibling file, re-validate, then fix the entry in the entry file.
_MULTI_FILE_ENTRY_MTHDS = """domain = "multifix_entry"
main_pipe = "entry_seq"

[concept]
Idea = "An idea."

[pipe.entry_gen]
type = "PipeLLM"
description = "Generate ideas."
inputs = { topic = "Text" }
output = "Idea[]"
prompt = "Generate ideas about $topic"

# Wrong on purpose: single output declared, last step yields a list.
[pipe.entry_seq]
type = "PipeSequence"
description = "Entry sequence with the wrong output."
inputs = { topic = "Text" }
output = "Idea"
steps = [
  { pipe = "entry_gen", result = "ideas" },
]
"""

_MULTI_FILE_SIBLING_MTHDS = """domain = "multifix_sibling"

[concept]
Notion = "A notion."

[pipe.sibling_gen]
type = "PipeLLM"
description = "Generate notions."
inputs = { topic = "Text" }
output = "Notion[]"
prompt = "Generate notions about $topic"

# Wrong on purpose: single output declared, last step yields a list.
[pipe.sibling_seq]
type = "PipeSequence"
description = "Sibling sequence with the wrong output."
inputs = { topic = "Text" }
output = "Notion"
steps = [
  { pipe = "sibling_gen", result = "notions" },
]
"""

# Corruption-scenario pair: the SAME pipe code declared by two domains across two files. The
# entry's `list_ideas` is valid; the sibling's `list_ideas` is broken. The fix must patch the
# declaring sibling — never the entry file's same-named table (the spike-era corruption bug).
_SAME_CODE_ENTRY_MTHDS = """domain = "corruptfix_entry"
main_pipe = "list_ideas"

[concept]
Idea = "An idea."

[pipe.list_ideas]
type = "PipeLLM"
description = "A VALID pipe whose code collides with a broken same-named pipe in another domain."
inputs = { topic = "Text" }
output = "Idea"
prompt = "Write one idea about $topic"
"""

_SAME_CODE_SIBLING_MTHDS = """domain = "corruptfix_sibling"

[concept]
Notion = "A notion."

[pipe.gen_notions]
type = "PipeLLM"
description = "Generate notions."
inputs = { topic = "Text" }
output = "Notion[]"
prompt = "Generate notions about $topic"

# Wrong on purpose: single output declared, last step yields a list — and the pipe code
# collides with the entry file's valid pipe.
[pipe.list_ideas]
type = "PipeSequence"
description = "Broken sibling sequence sharing the entry pipe's code."
inputs = { topic = "Text" }
output = "Notion"
steps = [
  { pipe = "gen_notions", result = "notions" },
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
        # Both sequences now declare the list output the last step yields.
        assert [Path(written) for written in result.files_written] == [bundle_path.resolve()]
        pipes = _pipes(bundle_path)
        assert pipes["inner"]["output"] == "Idea[]"
        assert pipes["outer"]["output"] == "Idea[]"

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
        make_summary = _pipes(bundle_path)["make_summary"]
        assert make_summary["inputs"] == {"text": "Text", "style": "Text"}
        assert "note" not in make_summary["inputs"]

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
        list_ideas = _pipes(bundle_path)["list_ideas"]
        assert list_ideas["inputs"] == {"topic": "Text"}
        assert list_ideas["output"] == "Idea[]"

    async def test_native_redeclarations_converge_error_by_error(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A bundle redeclaring two native concepts strips one per iteration until valid.

        The ``mode="before"`` concept validator raises on the first offending code, so the
        blueprint-channel ``strip-native-concept-redecl`` fix converges error-by-error — the same
        cascade shape as the pipe channel, now proven on the blueprint channel end-to-end.
        """
        load_empty_library()
        bundle_path = tmp_path / "native_redecl.mthds"
        bundle_path.write_text(_NATIVE_REDECL_MULTI_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path)

        assert result.is_valid is True
        assert result.iterations == 2
        assert [fix.fix_code for fix in result.fixes_applied] == [
            "strip-native-concept-redecl",
            "strip-native-concept-redecl",
        ]
        assert result.bail_reason is None
        parsed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        concept = cast("dict[str, Any]", parsed["concept"])
        assert "Text" not in concept
        assert "Number" not in concept
        # The real, non-native concept survives untouched.
        assert concept["Greeting"] == "A greeting message."

    async def test_strip_namespace_converges_leaving_qualified_refs(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A same-domain over-qualified declaration key and main_pipe are stripped in one iteration.

        Both syntax errors surface in the same validation pass (independent field validators), so
        the rename and the main_pipe set_key apply together. The qualified ``steps[].pipe`` reference
        is intentionally left in place — a same-domain qualified ref resolves to the bare pipe, so no
        reference rewrite is needed for validity (the array-of-tables addressing gap never opens).
        """
        load_empty_library()
        bundle_path = tmp_path / "strip_ns.mthds"
        bundle_path.write_text(_STRIP_NAMESPACE_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path)

        assert result.is_valid is True
        assert result.iterations == 1
        assert [fix.fix_code for fix in result.fixes_applied] == ["strip-namespace", "strip-namespace"]
        assert result.bail_reason is None
        parsed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        pipes = cast("dict[str, Any]", parsed["pipe"])
        assert "hello" in pipes
        assert "nsfix_loop.hello" not in pipes
        assert parsed["main_pipe"] == "run_seq"
        # The qualified step reference survives untouched (it resolves to the renamed bare pipe).
        assert pipes["run_seq"]["steps"][0]["pipe"] == "nsfix_loop.hello"

    @pytest.mark.parametrize(
        "sibling_mthds",
        [_XFILE_SIBLING_SAME_DOMAIN_MTHDS, _XFILE_SIBLING_OTHER_DOMAIN_MTHDS],
    )
    async def test_strip_namespace_bails_on_cross_file_collision(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
        sibling_mthds: str,
    ) -> None:
        """A rename whose bare code is declared by ANY sibling bundle is never applied.

        The raise-site collision gate only sees the target file, so the loop's cross-file guard
        must drop the fix — same domain (duplicate declaration) and other domain (bare-code
        ambiguity) alike. The loop bails loudly with the collision reason and the target file's
        bytes are untouched — no unrepairable state is ever written.
        """
        load_empty_library()
        bundle_path = tmp_path / "target.mthds"
        bundle_path.write_text(_XFILE_TARGET_MTHDS, encoding="utf-8")
        (tmp_path / "sibling.mthds").write_text(sibling_mthds, encoding="utf-8")

        result = await fix_bundle_file(bundle_path, library_dirs=[tmp_path])

        assert result.is_valid is False
        assert result.fixes_applied == []
        assert result.bail_reason is not None
        assert "cross-file collision" in result.bail_reason
        assert "'hola'" in result.bail_reason
        assert result.remaining_errors
        assert bundle_path.read_text(encoding="utf-8") == _XFILE_TARGET_MTHDS

    async def test_typoed_main_pipe_tail_is_never_stripped(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A dotted ``main_pipe`` whose tail matches no declaration gets NO fix: file untouched.

        Stripping would rewrite ``main_pipe`` to a nonexistent pipe — a SAFE-labeled fix mutating
        the file while leaving the bundle invalid with a different error. The categorizer's
        document-level gate suppresses the enrichment, so the loop has nothing to apply.
        """
        load_empty_library()
        bundle_path = tmp_path / "typo_tail.mthds"
        bundle_path.write_text(_MAIN_PIPE_TYPO_TAIL_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path)

        assert result.is_valid is False
        assert result.fixes_applied == []
        assert result.files_written == []
        assert bundle_path.read_text(encoding="utf-8") == _MAIN_PIPE_TYPO_TAIL_MTHDS

    async def test_dotted_declaration_main_pipe_still_converges(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """``main_pipe`` naming a dotted-only declaration converges: the rename materializes the
        bare target and the paired ``main_pipe`` strip applies in the same round.
        """
        load_empty_library()
        bundle_path = tmp_path / "dotted_conv.mthds"
        bundle_path.write_text(_MAIN_PIPE_DOTTED_DECL_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path)

        assert result.is_valid is True
        assert result.iterations == 1
        assert [fix.fix_code for fix in result.fixes_applied] == ["strip-namespace", "strip-namespace"]
        parsed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        pipes = cast("dict[str, Any]", parsed["pipe"])
        assert "hello" in pipes
        assert "nsfix_conv_loop.hello" not in pipes
        assert parsed["main_pipe"] == "hello"

    async def test_main_pipe_set_key_dropped_with_its_blocked_rename(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """When the declaration rename is dropped as cross-file colliding, the paired root
        ``main_pipe`` set_key is dropped WITH it — never an orphaned ``main_pipe`` write.

        The categorizer cannot see cross-file state (its second disjunct is satisfied here: the
        dotted declaration exists), so this suppression must live in the loop's collision split.
        """
        load_empty_library()
        bundle_path = tmp_path / "target.mthds"
        bundle_path.write_text(_XFILE_MAIN_PIPE_TARGET_MTHDS, encoding="utf-8")
        (tmp_path / "sibling.mthds").write_text(_XFILE_MAIN_PIPE_SIBLING_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path, library_dirs=[tmp_path])

        assert result.is_valid is False
        assert result.fixes_applied == []
        assert result.files_written == []
        assert result.bail_reason is not None
        assert "cross-file collision" in result.bail_reason
        assert "'hello'" in result.bail_reason
        # No orphaned main_pipe was ever written: the target is byte-identical.
        assert bundle_path.read_text(encoding="utf-8") == _XFILE_MAIN_PIPE_TARGET_MTHDS

    async def test_main_pipe_strip_kept_when_target_already_declares_bare_code(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A sibling's same bare code must not block stripping ``main_pipe`` when the target file
        already declares that bare pipe locally.

        The orphan guard exists for the dotted-declaration case where a blocked rename would leave
        ``main_pipe`` pointing to a pipe the target never declares. Here ``hello`` is already local,
        so dropping the root ``main_pipe`` set_key would be an over-conservative no-fix.
        """
        load_empty_library()
        bundle_path = tmp_path / "target.mthds"
        bundle_path.write_text(_LOCAL_MAIN_PIPE_WITH_SIBLING_SAME_CODE_MTHDS, encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()
        (libs_dir / "sibling.mthds").write_text(_LOCAL_MAIN_PIPE_SIBLING_SAME_CODE_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path, library_dirs=[libs_dir])

        assert result.is_valid is True
        assert [fix.fix_code for fix in result.fixes_applied] == ["strip-namespace"]
        assert [Path(written) for written in result.files_written] == [bundle_path.resolve()]
        parsed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
        assert parsed["main_pipe"] == "hello"
        assert "hello" in parsed["pipe"]

    async def test_strip_namespace_proceeds_past_unrelated_sibling(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A sibling declaring only unrelated pipe codes does not block the rename (no over-dropping)."""
        load_empty_library()
        bundle_path = tmp_path / "target.mthds"
        bundle_path.write_text(_XFILE_TARGET_MTHDS, encoding="utf-8")
        (tmp_path / "sibling.mthds").write_text(_XFILE_SIBLING_UNRELATED_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path, library_dirs=[tmp_path])

        assert result.is_valid is True
        assert [fix.fix_code for fix in result.fixes_applied] == ["strip-namespace"]
        assert result.bail_reason is None
        pipes = _pipes(bundle_path)
        assert "hola" in pipes
        assert "nsfix_xfile.hola" not in pipes

    async def test_strip_namespace_proceeds_past_sibling_signature_header(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A sibling ``PipeSignature`` header is not a hard collision.

        Additive multi-file loading allows a concrete definition to replace a matching signature.
        The cross-file guard must therefore ignore typeless contract-only sections when deciding
        whether a stripped concrete declaration would collide with a sibling file.
        """
        load_empty_library()
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_SINGLE_PASS_MTHDS.replace('output = "Idea"\n', 'output = "Idea[]"\n'), encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()
        concrete_path = libs_dir / "concrete.mthds"
        concrete_path.write_text(_XFILE_SIGNATURE_TARGET_MTHDS, encoding="utf-8")
        (libs_dir / "signature.mthds").write_text(_XFILE_SIGNATURE_SIBLING_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path, library_dirs=[libs_dir])

        assert result.is_valid is True
        assert result.bail_reason is None
        assert [fix.fix_code for fix in result.fixes_applied] == ["strip-namespace"]
        assert [Path(written) for written in result.files_written] == [concrete_path.resolve()]
        parsed = tomlkit.loads(concrete_path.read_text(encoding="utf-8")).unwrap()
        pipes = cast("dict[str, Any]", parsed["pipe"])
        assert "hello" in pipes
        assert "nsfix_xsig.hello" not in pipes

    async def test_multi_file_cascade_fixes_each_declaring_file(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Errors declared in the sibling and the entry are each fixed IN their declaring file.

        The sibling's error surfaces first (library dirs load before the entry file), so the loop
        must patch the sibling file, re-validate, then patch the entry — a cross-file cascade.
        Both files are written and reported in ``files_written``.
        """
        load_empty_library()
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_MULTI_FILE_ENTRY_MTHDS, encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()
        sibling_path = libs_dir / "sibling.mthds"
        sibling_path.write_text(_MULTI_FILE_SIBLING_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path, library_dirs=[libs_dir])

        assert result.is_valid is True
        assert [fix.fix_code for fix in result.fixes_applied] == ["match-sequence-output", "match-sequence-output"]
        assert result.bail_reason is None
        assert [Path(written) for written in result.files_written] == [sibling_path.resolve(), bundle_path.resolve()]
        assert _pipes(bundle_path)["entry_seq"]["output"] == "Idea[]"
        assert _pipes(sibling_path)["sibling_seq"]["output"] == "Notion[]"

    async def test_same_pipe_code_across_domains_patches_the_declaring_file_only(
        self,
        tmp_path: Path,
        load_empty_library: Callable[[], str],
    ) -> None:
        """REGRESSION (spike corruption scenario): the same pipe code in two domains across two
        files — the fix patches the sibling that declares the broken pipe, never the entry file's
        same-named, perfectly valid table.
        """
        load_empty_library()
        bundle_path = tmp_path / "entry.mthds"
        bundle_path.write_text(_SAME_CODE_ENTRY_MTHDS, encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()
        sibling_path = libs_dir / "sibling.mthds"
        sibling_path.write_text(_SAME_CODE_SIBLING_MTHDS, encoding="utf-8")

        result = await fix_bundle_file(bundle_path, library_dirs=[libs_dir])

        assert result.is_valid is True
        assert [fix.fix_code for fix in result.fixes_applied] == ["match-sequence-output"]
        assert [Path(written) for written in result.files_written] == [sibling_path.resolve()]
        # The sibling's broken sequence now matches its last step; the entry file is untouched.
        assert _pipes(sibling_path)["list_ideas"]["output"] == "Notion[]"
        assert bundle_path.read_text(encoding="utf-8") == _SAME_CODE_ENTRY_MTHDS

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
