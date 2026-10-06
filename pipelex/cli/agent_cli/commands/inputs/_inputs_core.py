"""Core logic for generating inputs templates in the agent CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pipelex.cli.agent_cli.commands.agent_output import agent_success
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat, serialize_inputs_template_to_toml
from pipelex.pipeline.inputs_template import build_inputs_for_pipe

if TYPE_CHECKING:
    from pathlib import Path


async def inputs_core(
    *, pipe_code: str | None = None, bundle_path: Path | None = None, library_dirs: list[Path] | None = None, explicit: bool = False
) -> dict[str, Any]:
    """Core logic for generating input JSON for a pipe.

    Args:
        pipe_code: The pipe to generate inputs for, a bare code or a qualified ref.
        bundle_path: Path to the bundle file (.mthds).
        library_dirs: List of library directories to search for pipe definitions.
        explicit: When True, emit the ceremonial envelope form; when False (default), the light shape.

    Returns:
        The inputs-generation result: ``success``, the resolved ``pipe_ref``, ``inputs``, and the
        internal ``concept_comments`` and ``no_inputs_message``.

    Raises:
        ValidateBundleError: If bundle validation fails.
    """
    return await build_inputs_for_pipe(
        pipe_code=pipe_code,
        bundle_path=bundle_path,
        library_dirs=library_dirs,
        explicit=explicit,
    )


def emit_inputs_result(result: dict[str, Any], *, template_format: InputsTemplateFormat, explicit: bool = False) -> None:
    """Emit an inputs-generation result in the requested template format.

    JSON keeps the structured success envelope; TOML prints the raw template to
    stdout. The default light template needs the inline-table layout (``light=True``) so a
    bare scalar declared after a structured value stays valid TOML, and carries the declared
    concept as a ``# concept: ...`` comment per key (same hints the human ``build inputs --format
    toml`` writes); ``--explicit`` restores the all-tables envelope layout. A pipe that declares
    no inputs prints its ``no_inputs_message`` as a comment line, valid TOML that loads back as an
    empty dict.

    ``concept_comments`` and ``no_inputs_message`` are internal plumbing: they are stripped here so
    the JSON envelope stays the plain ``success``/``pipe_ref``/``inputs`` shape, the same on every
    runner, and are only consumed by the TOML path.

    Args:
        result: The inputs-generation result (``success``/``pipe_ref``/``inputs`` + internal
            ``concept_comments`` and ``no_inputs_message``).
        template_format: The requested inputs template format.
        explicit: Whether ``result["inputs"]`` is the envelope form (True) or the light form (False).
    """
    concept_comments = cast("dict[str, str] | None", result.pop("concept_comments", None))
    no_inputs_message = cast("str | None", result.pop("no_inputs_message", None))
    match template_format:
        case InputsTemplateFormat.JSON:
            agent_success(result)
        case InputsTemplateFormat.TOML:
            if no_inputs_message is not None:
                print(f"# {no_inputs_message}")
                return
            toml_content = serialize_inputs_template_to_toml(result["inputs"], light=not explicit, concept_comments=concept_comments)
            print(toml_content, end="" if toml_content.endswith("\n") else "\n")
