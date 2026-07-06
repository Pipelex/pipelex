"""Core logic for generating inputs templates in the agent CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.builder.operations.inputs_ops import build_inputs_for_pipe
from pipelex.cli.agent_cli.commands.agent_output import agent_success
from pipelex.core.pipes.inputs.input_renderer import InputsTemplateFormat, serialize_inputs_template_to_toml

if TYPE_CHECKING:
    from pathlib import Path


async def inputs_core(
    pipe_code: str | None = None,
    *,
    bundle_path: Path | None = None,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Core logic for generating input JSON for a pipe.

    Args:
        pipe_code: The pipe code to generate inputs for.
        bundle_path: Path to the bundle file (.mthds).
        library_dirs: List of library directories to search for pipe definitions.

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
    )


def emit_inputs_result(result: dict[str, Any], *, template_format: InputsTemplateFormat) -> None:
    """Emit an inputs-generation result in the requested template format.

    JSON keeps the structured success envelope; TOML prints the raw template to
    stdout, in the same spirit as the ``concept``/``pipe`` raw-TOML passthrough
    commands.

    Args:
        result: The inputs-generation result (``success``/``pipe_code``/``inputs``).
        template_format: The requested inputs template format.
    """
    match template_format:
        case InputsTemplateFormat.JSON:
            agent_success(result)
        case InputsTemplateFormat.TOML:
            toml_content = serialize_inputs_template_to_toml(result["inputs"])
            print(toml_content, end="" if toml_content.endswith("\n") else "\n")


def emit_no_inputs_result(pipe_code: str | None, *, message: str, template_format: InputsTemplateFormat) -> None:
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
