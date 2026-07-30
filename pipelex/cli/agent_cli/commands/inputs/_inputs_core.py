"""Core logic for generating inputs templates in the agent CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from pipelex.builder.operations.inputs_ops import build_inputs_for_pipe
from pipelex.cli.agent_cli.commands.agent_output import agent_success
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat, serialize_inputs_template_to_toml

if TYPE_CHECKING:
    from pathlib import Path


async def inputs_core(
    *, pipe_code: str | None = None, bundle_path: Path | None = None, library_dirs: list[Path] | None = None, explicit: bool = False
) -> dict[str, Any]:
    """Core logic for generating input JSON for a pipe.

    Args:
        pipe_code: The pipe code to generate inputs for.
        bundle_path: Path to the bundle file (.mthds).
        library_dirs: List of library directories to search for pipe definitions.
        explicit: When True, emit the ceremonial envelope form; when False (default), the light shape.

    Returns:
        Dictionary with inputs suitable for JSON serialization.

    Raises:
        ValidateBundleError: If bundle validation fails.
        NoInputsRequiredError: If the pipe has no inputs.
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
    stdout, in the same spirit as the ``concept``/``pipe`` raw-TOML passthrough
    commands. The default light template needs the inline-table layout (``light=True``) so a
    bare scalar declared after a structured value stays valid TOML, and carries the declared
    concept as a ``# concept: ...`` comment per key (same hints the human ``build inputs --format
    toml`` writes); ``--explicit`` restores the all-tables envelope layout.

    ``concept_comments`` is internal plumbing: it is stripped here so the JSON envelope stays the
    plain ``success``/``pipe_code``/``inputs`` shape and is only consumed by the light-TOML path.

    Args:
        result: The inputs-generation result (``success``/``pipe_code``/``inputs`` + internal
            ``concept_comments``).
        template_format: The requested inputs template format.
        explicit: Whether ``result["inputs"]`` is the envelope form (True) or the light form (False).
    """
    concept_comments = cast("dict[str, str] | None", result.pop("concept_comments", None))
    match template_format:
        case InputsTemplateFormat.JSON:
            agent_success(result)
        case InputsTemplateFormat.TOML:
            toml_content = serialize_inputs_template_to_toml(result["inputs"], light=not explicit, concept_comments=concept_comments)
            print(toml_content, end="" if toml_content.endswith("\n") else "\n")


def emit_no_inputs_result(*, pipe_code: str | None, message: str, template_format: InputsTemplateFormat) -> None:
    """Emit the not-an-error result for a pipe that requires no inputs.

    JSON keeps the structured envelope with an empty ``inputs`` dict; TOML
    prints a comment line — valid TOML that loads back as an empty dict.

    Args:
        pipe_code: The pipe code the inputs were requested for, if known.
        message: The human-readable no-inputs-required message.
        template_format: The requested inputs template format.
    """
    match template_format:
        case InputsTemplateFormat.JSON:
            agent_success(
                {
                    "success": True,
                    "pipe_code": pipe_code,
                    "inputs": {},
                    "message": message,
                }
            )
        case InputsTemplateFormat.TOML:
            print(f"# {message}")
