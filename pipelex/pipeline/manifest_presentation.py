"""The validation rules of a manifest's `result_line` and `examples` (spec: manifest-format.md, "Result Line" and "Example
Inputs") that only a runtime holding the method's tree and library can apply.

`mthds`'s `MethodsManifest` checks the rules a manifest breaks on its own: an empty `result_line`, and either key without
the manifest's `main_pipe`. This module adds the rest. `result_line` must parse as a Jinja2 template whose free variables
are all rooted at `output`; each entry of `examples` must name a file of the method's tree, never `inputs.json`, else it
is `method.resource_missing`; and each example file must hold a complete set of flat inputs in stuff wire form for the
main pipe, else it is `method.package_invalid` with the reason `example_invalid` and the file's path. A refusal carries
the `ManifestPackageReason` the format names. `check_manifest_presentation` applies them all where a method is validated.
"""

import json
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any, NamedTuple, cast

from mthds.method_tree.models import MethodTree
from mthds.package.manifest.package_reason import ManifestPackageReason
from mthds.package.manifest.schema import MethodsManifest
from mthds.protocol.problem.registry import CoreCode, MethodResourceMissingReason

from pipelex.interpreter_hub import get_concept_library
from pipelex.libraries.method_trees import read_tree_file_as_listed
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

RESULT_LINE_ROOT = "output"
"""The one variable a result line reads: the content of the main pipe's output as a stuff carries it on the wire."""

RUN_INPUTS_FILE_NAME = "inputs.json"
"""The run inputs file, which is never a member of a method's tree, so never an example."""


class ManifestPresentationFault(NamedTuple):
    """One fault of a manifest's presentation keys: why, the tree path of the example file it is about, and a sentence.

    `reason` is the `method.package_invalid` reason the format names, or `NOT_IN_TREE` for an example naming no file of
    the tree, which is `method.resource_missing` (`code`).
    """

    reason: ManifestPackageReason | MethodResourceMissingReason
    path: str | None
    message: str

    @property
    def code(self) -> CoreCode:
        if isinstance(self.reason, MethodResourceMissingReason):
            return CoreCode.METHOD_RESOURCE_MISSING
        return CoreCode.METHOD_PACKAGE_INVALID

    def problem_params(self) -> dict[str, str]:
        """The parameters of the fault's code: the file and why for `resource_missing`, the reason and path for `package_invalid`."""
        if isinstance(self.reason, MethodResourceMissingReason):
            return {"file": self.path or "", "reason": self.reason}
        params: dict[str, str] = {"reason": self.reason}
        if self.path is not None:
            params["path"] = self.path
        return params


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
            ManifestPackageReason.RESULT_LINE_WITHOUT_MAIN_PIPE, None, "`result_line` requires the manifest's `main_pipe`, whose output it reads"
        )
    if not result_line.strip():
        return ManifestPresentationFault(ManifestPackageReason.RESULT_LINE_INVALID, None, "`result_line` must not be empty")
    try:
        variable_paths = detect_jinja2_required_variables(template_category=TemplateCategory.BASIC, template_source=result_line)
    except Jinja2DetectVariablesError:
        return ManifestPresentationFault(ManifestPackageReason.RESULT_LINE_INVALID, None, "`result_line` does not parse as a Jinja2 template")
    stray_roots = sorted({get_root_from_dotted_path(path) for path in variable_paths} - {RESULT_LINE_ROOT})
    if stray_roots:
        names = ", ".join(f"'{root}'" for root in stray_roots)
        return ManifestPresentationFault(
            ManifestPackageReason.RESULT_LINE_INVALID, None, f"`result_line` reads {names}: it reads only `output`, the main pipe's output"
        )
    return None


def examples_faults(*, examples: list[str], has_main_pipe: bool, tree_paths: frozenset[str]) -> list[ManifestPresentationFault]:
    """The faults of a manifest's `examples` list that the tree alone decides: no main pipe, and files the tree does not hold."""
    if not has_main_pipe:
        return [
            ManifestPresentationFault(
                ManifestPackageReason.EXAMPLES_WITHOUT_MAIN_PIPE, None, "`examples` requires the manifest's `main_pipe`, whose inputs they fill"
            )
        ]
    faults: list[ManifestPresentationFault] = []
    for example_path in examples:
        normalized = str(PurePosixPath(example_path))
        if PurePosixPath(normalized).name == RUN_INPUTS_FILE_NAME or normalized not in tree_paths:
            faults.append(
                ManifestPresentationFault(
                    MethodResourceMissingReason.NOT_IN_TREE, example_path, f"the example '{example_path}' names no file of the method's tree"
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
        return ManifestPresentationFault(ManifestPackageReason.EXAMPLE_INVALID, example_path, f"the example '{example_path}' {message}")

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


def example_input_slots(*, pipe: PipeAbstract) -> dict[str, ExampleInputSlot]:
    """What an example must honour about each input of the main pipe: the concepts it may name, and its presence."""
    concept_library = get_concept_library()
    slots: dict[str, ExampleInputSlot] = {}
    for input_name, stuff_spec in pipe.inputs.items:
        declared = stuff_spec.concept
        accepted = {declared.concept_ref, declared.simple_concept_ref}
        for candidate in concept_library.list_concepts():
            if concept_library.is_compatible(tested_concept=candidate, wanted_concept=declared):
                accepted.update({candidate.concept_ref, candidate.simple_concept_ref})
        slots[input_name] = ExampleInputSlot(
            accepted_concepts=frozenset(accepted),
            required=not stuff_spec.presence.is_optional,
            is_variable_list=stuff_spec.multiplicity is True,
        )
    return slots


def manifest_presentation_faults(*, manifest: MethodsManifest, tree: MethodTree, main_pipe: PipeAbstract | None) -> list[ManifestPresentationFault]:
    """Every fault of a manifest's `result_line` and `examples` against the method's listed tree and its main pipe.

    The rules `MethodsManifest` checks itself never reach here, since a manifest breaking them does not parse. An example
    file is read as listed, so a file that changed since the listing is refused as the tree's change.
    """
    has_main_pipe = manifest.main_pipe is not None
    faults: list[ManifestPresentationFault] = []
    if manifest.result_line is not None:
        line_fault = result_line_fault(result_line=manifest.result_line, has_main_pipe=has_main_pipe)
        if line_fault is not None:
            faults.append(line_fault)
    if not manifest.examples:
        return faults
    missing = examples_faults(examples=manifest.examples, has_main_pipe=has_main_pipe, tree_paths=frozenset(tree.tree_paths))
    faults.extend(missing)
    if main_pipe is None:
        return faults
    missing_paths = {fault.path for fault in missing}
    slots = example_input_slots(pipe=main_pipe)
    for example_path in manifest.examples:
        if example_path in missing_paths:
            continue
        tree_path = str(PurePosixPath(example_path))
        try:
            file_text = read_tree_file_as_listed(tree=tree, tree_path=tree_path).decode("utf-8")
        except UnicodeDecodeError:
            faults.append(
                ManifestPresentationFault(ManifestPackageReason.EXAMPLE_INVALID, example_path, f"the example '{example_path}' is not UTF-8 text")
            )
            continue
        inputs_fault = example_inputs_fault(example_path=example_path, file_text=file_text, inputs=slots)
        if inputs_fault is not None:
            faults.append(inputs_fault)
    return faults
