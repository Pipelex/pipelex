"""Pin: a strippable same-domain over-qualified pipe code carries structured error data (autofix).

Writing a pipe declaration key or ``main_pipe`` as ``<own-domain>.<code>`` is invalid syntax
(pipe codes must be bare snake_case). The two snake_case-enforcing before-validators know both the
offending code and its bare form at detection time; these tests pin that the blueprint error data
carries ``INVALID_PIPE_CODE_SYNTAX`` with the ``stripped_pipe_code`` enrichment — and that
``pipe_code`` discriminates the two raise sites (the offending dotted key for a declaration rename,
``None`` for a ``main_pipe`` value strip). That enriched fact is what the ``strip-namespace`` planner
translates into a fix. Only *safely* strippable codes get enriched: a collision with an existing bare
declaration, a cross-package prefix, or a malformed bare tail all stay un-enriched (unfixable).
"""

from collections.abc import Callable

import pytest

from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle

# A same-domain over-qualified DECLARATION key; main_pipe is a valid bare pipe, so the only error is
# the dotted declaration. The qualified step ref survives (it resolves) — not an error.
_DOTTED_DECL_MTHDS = """
domain = "nsfix_decl"
main_pipe = "run_seq"

[pipe."nsfix_decl.hello"]
type = "PipeLLM"
description = "Say hello."
output = "Text"
prompt = "Say hello"

[pipe.run_seq]
type = "PipeSequence"
description = "Run it."
output = "Text"
steps = [
  { pipe = "nsfix_decl.hello", result = "greeting" },
]
"""

# A same-domain over-qualified MAIN_PIPE; all declarations are bare, so the only error is main_pipe.
_DOTTED_MAIN_PIPE_MTHDS = """
domain = "nsfix_main"
main_pipe = "nsfix_main.hello"

[pipe.hello]
type = "PipeLLM"
description = "Say hello."
output = "Text"
prompt = "Say hello"
"""

# Collision: a bare `hello` already occupies the key the dotted one would rename to → not strippable.
_COLLISION_MTHDS = """
domain = "nsfix_coll"
main_pipe = "hello"

[pipe.hello]
type = "PipeLLM"
description = "Bare hello."
output = "Text"
prompt = "Bare"

[pipe."nsfix_coll.hello"]
type = "PipeLLM"
description = "Dotted hello."
output = "Text"
prompt = "Dotted"
"""

# Cross-package prefix (not the bundle's own domain) → never stripped (would break a real qualified ref).
_CROSS_DOMAIN_MTHDS = """
domain = "nsfix_cross"
main_pipe = "run_seq"

[pipe."otherpkg.hello"]
type = "PipeLLM"
description = "From another package."
output = "Text"
prompt = "Hello"

[pipe.run_seq]
type = "PipeSequence"
description = "Run it."
output = "Text"
steps = [
  { pipe = "otherpkg.hello", result = "greeting" },
]
"""

# Dotted, same-domain, but the bare tail is itself invalid snake_case → not strippable.
_BAD_BARE_MTHDS = """
domain = "nsfix_bad"
main_pipe = "run_seq"

[pipe."nsfix_bad.Bad-Code"]
type = "PipeLLM"
description = "Bad bare tail."
output = "Text"
prompt = "Hello"

[pipe.run_seq]
type = "PipeSequence"
description = "Run it."
output = "Text"
steps = [
  { pipe = "run_seq", result = "greeting" },
]
"""


async def _syntax_errors(mthds_content: str) -> list[PipelexBundleBlueprintValidationErrorData]:
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=[mthds_content])
    return [
        error_data
        for error_data in exc_info.value.pipelex_bundle_blueprint_validation_errors
        if error_data.error_type == PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX
    ]


@pytest.mark.asyncio(loop_scope="class")
class TestStripNamespaceEnrichment:
    async def test_dotted_declaration_carries_rename_enrichment(self, load_empty_library: Callable[[], str]) -> None:
        """A same-domain dotted declaration key carries the offending code + its bare form."""
        load_empty_library()
        errors = await _syntax_errors(_DOTTED_DECL_MTHDS)
        strippable = [error for error in errors if error.stripped_pipe_code is not None]
        assert len(strippable) == 1
        assert strippable[0].pipe_code == "nsfix_decl.hello"
        assert strippable[0].stripped_pipe_code == "hello"

    async def test_dotted_main_pipe_carries_strip_enrichment_without_pipe_code(self, load_empty_library: Callable[[], str]) -> None:
        """A same-domain dotted ``main_pipe`` carries the bare form and NO ``pipe_code`` (root set_key)."""
        load_empty_library()
        errors = await _syntax_errors(_DOTTED_MAIN_PIPE_MTHDS)
        strippable = [error for error in errors if error.stripped_pipe_code is not None]
        assert len(strippable) == 1
        assert strippable[0].pipe_code is None
        assert strippable[0].stripped_pipe_code == "hello"

    @pytest.mark.parametrize(
        "mthds_content",
        [_COLLISION_MTHDS, _CROSS_DOMAIN_MTHDS, _BAD_BARE_MTHDS],
    )
    async def test_unstrippable_syntax_errors_are_not_enriched(
        self,
        load_empty_library: Callable[[], str],
        mthds_content: str,
    ) -> None:
        """Collision, cross-package prefix, and a malformed bare tail stay un-enriched (unfixable)."""
        load_empty_library()
        errors = await _syntax_errors(mthds_content)
        assert errors, "expected an INVALID_PIPE_CODE_SYNTAX error"
        assert all(error.stripped_pipe_code is None for error in errors)
