"""The validation rules of a manifest's `result_line` and `examples` (spec: manifest-format.md, "Result Line" and "Example
Inputs").

Both require the manifest's own `main_pipe`. `result_line` is a Jinja2 template whose free variables are all rooted at
`output`; `examples` name files of the method's tree, never `inputs.json`, each holding a complete set of flat inputs in
stuff wire form for the main pipe.

These judgments are stated here, apart from the manifest model, because the manifest is parsed by the `mthds` package: its
`MethodsManifest` closes its keys, so a manifest writing either key is refused there until a release of `mthds` carries
them. When one does, the manifest load calls `result_line_fault` and `examples_faults`, and `example_inputs_fault` for each
file once the main pipe's inputs are known; evaluating the line and offering the examples belong to the runtime's run and
API surfaces, beyond this module.
"""

import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, NamedTuple, cast

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

RESULT_LINE_ROOT = "output"
"""The one variable a result line reads: the content of the main pipe's output as a stuff carries it on the wire."""

RUN_INPUTS_FILE_NAME = "inputs.json"
"""The run inputs file, which is never a member of a method's tree, so never an example."""


class ManifestPresentationReason(StrEnum):
    """The reasons of `method.package_invalid` a manifest's `result_line` or `examples` gives."""

    RESULT_LINE_WITHOUT_MAIN_PIPE = "result_line_without_main_pipe"
    RESULT_LINE_INVALID = "result_line_invalid"
    EXAMPLES_WITHOUT_MAIN_PIPE = "examples_without_main_pipe"
    EXAMPLE_INVALID = "example_invalid"
    # Not a `package_invalid` reason: an example naming no file of the tree is `method.resource_missing`.
    EXAMPLE_FILE_MISSING = "example_file_missing"


class ManifestPresentationFault(NamedTuple):
    """One fault of a manifest's presentation keys: why, the tree path of the example file it is about, and a sentence."""

    reason: ManifestPresentationReason
    path: str | None
    message: str


class ExampleInputSlot(NamedTuple):
    """What an example input set must honour about one input of the main pipe."""

    accepted_concepts: frozenset[str]
    """The crate keys a stuff of this input may name: its declared concept's and those of the concepts refining it."""
    required: bool
    """Whether its presence is not marked optional with `?`, so an example must hold it."""
    is_variable_list: bool
    """Whether it is of variable multiplicity (`Foo[]`), which an empty list `[]` makes present."""


def result_line_fault(*, result_line: str, has_main_pipe: bool) -> ManifestPresentationFault | None:
    """Why a manifest's `result_line` is refused, or `None` when it is accepted."""
    if not has_main_pipe:
        return ManifestPresentationFault(
            ManifestPresentationReason.RESULT_LINE_WITHOUT_MAIN_PIPE, None, "`result_line` requires the manifest's `main_pipe`, whose output it reads"
        )
    if not result_line.strip():
        return ManifestPresentationFault(ManifestPresentationReason.RESULT_LINE_INVALID, None, "`result_line` must not be empty")
    try:
        variable_paths = detect_jinja2_required_variables(template_category=TemplateCategory.BASIC, template_source=result_line)
    except Jinja2DetectVariablesError:
        return ManifestPresentationFault(ManifestPresentationReason.RESULT_LINE_INVALID, None, "`result_line` does not parse as a Jinja2 template")
    stray_roots = sorted({get_root_from_dotted_path(path) for path in variable_paths} - {RESULT_LINE_ROOT})
    if stray_roots:
        names = ", ".join(f"'{root}'" for root in stray_roots)
        return ManifestPresentationFault(
            ManifestPresentationReason.RESULT_LINE_INVALID, None, f"`result_line` reads {names}: it reads only `output`, the main pipe's output"
        )
    return None


def examples_faults(*, examples: list[str], has_main_pipe: bool, tree_paths: frozenset[str]) -> list[ManifestPresentationFault]:
    """The faults of a manifest's `examples` list that the tree alone decides: no main pipe, and files the tree does not hold."""
    if not has_main_pipe:
        return [
            ManifestPresentationFault(
                ManifestPresentationReason.EXAMPLES_WITHOUT_MAIN_PIPE, None, "`examples` requires the manifest's `main_pipe`, whose inputs they fill"
            )
        ]
    faults: list[ManifestPresentationFault] = []
    for example_path in examples:
        normalized = str(PurePosixPath(example_path))
        if PurePosixPath(normalized).name == RUN_INPUTS_FILE_NAME or normalized not in tree_paths:
            faults.append(
                ManifestPresentationFault(
                    ManifestPresentationReason.EXAMPLE_FILE_MISSING, example_path, f"the example '{example_path}' names no file of the method's tree"
                )
            )
    return faults


def example_inputs_fault(*, example_path: str, file_text: str, inputs: Mapping[str, ExampleInputSlot]) -> ManifestPresentationFault | None:
    """Why an example file is not a valid set of flat inputs for the main pipe, or `None` when it is.

    Checked here: a JSON object whose keys each name an input, each value a stuff in wire form whose `concept` the input
    accepts, and every required input present. Whether each content satisfies its input's JSON Schema, contract facts
    included, is the input gate's judgment, applied when the example is run.
    """

    def invalid(*, message: str) -> ManifestPresentationFault:
        return ManifestPresentationFault(ManifestPresentationReason.EXAMPLE_INVALID, example_path, f"the example '{example_path}' {message}")

    try:
        payload: Any = json.loads(file_text)
    except json.JSONDecodeError:
        return invalid(message="is not JSON")
    if not isinstance(payload, dict):
        return invalid(message="does not hold a JSON object of flat inputs")
    flat_inputs = cast("dict[str, Any]", payload)
    for input_name, stuff in flat_inputs.items():
        slot = inputs.get(input_name)
        if slot is None:
            return invalid(message=f"names '{input_name}', which is not an input of the main pipe")
        if stuff == [] and slot.is_variable_list:
            # A required list of variable multiplicity is present when it holds an empty list.
            continue
        if not isinstance(stuff, dict) or "concept" not in stuff or "content" not in stuff:
            return invalid(message=f"gives '{input_name}' a value that is not a stuff in wire form, with its `concept` and `content`")
        stuff_table = cast("dict[str, Any]", stuff)
        if stuff_table["concept"] not in slot.accepted_concepts:
            return invalid(message=f"gives '{input_name}' the concept '{stuff_table['concept']}', which its input does not accept")
    missing = sorted(input_name for input_name, slot in inputs.items() if slot.required and input_name not in flat_inputs)
    if missing:
        return invalid(message=f"lacks the required input(s) {', '.join(repr(name) for name in missing)}")
    return None
