import json

import pytest
from mthds.package.manifest.package_reason import ManifestPackageReason
from mthds.protocol.problem.registry import MethodResourceMissingReason

from pipelex.pipeline.manifest_presentation import (
    ExampleInputSlot,
    example_inputs_fault,
    examples_faults,
    result_line_fault,
)

_INPUTS = {
    "nda": ExampleInputSlot(accepted_concepts=frozenset({"legal.Nda"}), required=True, is_variable_list=False),
    "counterparty": ExampleInputSlot(accepted_concepts=frozenset({"native.Text"}), required=True, is_variable_list=False),
    "notes": ExampleInputSlot(accepted_concepts=frozenset({"native.Text"}), required=True, is_variable_list=True),
    "hint": ExampleInputSlot(accepted_concepts=frozenset({"native.Text"}), required=False, is_variable_list=False),
}
_NDA = {"concept": "legal.Nda", "content": {"url": "mutual-nda.pdf"}}
_PARTY = {"concept": "native.Text", "content": {"text": "Acme Corp"}}


class TestManifestPresentation:
    @pytest.mark.parametrize(
        ("result_line", "has_main_pipe", "reason"),
        [
            ("{{ output.total }} due", True, None),
            ("{{ output.total }} due", False, ManifestPackageReason.RESULT_LINE_WITHOUT_MAIN_PIPE),
            ("{{ output.total ", True, ManifestPackageReason.RESULT_LINE_INVALID),
            ("{% for c in output.clauses %}{{ c.heading }} {% endfor %}", True, None),
            ("{{ counterparty }}", True, ManifestPackageReason.RESULT_LINE_INVALID),
            ("", True, ManifestPackageReason.RESULT_LINE_INVALID),
        ],
    )
    def test_result_line(self, result_line: str, has_main_pipe: bool, reason: ManifestPackageReason | None) -> None:
        """The verdicts of manifest-format.md's result-line table."""
        fault = result_line_fault(result_line=result_line, has_main_pipe=has_main_pipe)
        assert (fault.reason if fault is not None else None) == reason

    @pytest.mark.parametrize(
        ("examples", "has_main_pipe", "reasons"),
        [
            (["examples/mutual-nda.json"], True, []),
            (["examples/mutual-nda.json"], False, [ManifestPackageReason.EXAMPLES_WITHOUT_MAIN_PIPE]),
            (["examples/missing.json"], True, [MethodResourceMissingReason.NOT_IN_TREE]),
            (["inputs.json"], True, [MethodResourceMissingReason.NOT_IN_TREE]),
        ],
    )
    def test_examples_list(
        self, examples: list[str], has_main_pipe: bool, reasons: list[ManifestPackageReason | MethodResourceMissingReason]
    ) -> None:
        """The verdicts of manifest-format.md's examples table, `inputs.json` never being a file of the tree."""
        faults = examples_faults(examples=examples, has_main_pipe=has_main_pipe, tree_paths=frozenset({"examples/mutual-nda.json", "inputs.json"}))
        assert [fault.reason for fault in faults] == reasons

    @pytest.mark.parametrize(
        ("payload", "invalid"),
        [
            ({"nda": _NDA, "counterparty": _PARTY, "notes": []}, None),
            ({"nda": _NDA, "counterparty": _PARTY, "notes": [], "hint": _PARTY}, None),
            ({"nda": _NDA, "notes": []}, "lacks the required input(s) 'counterparty'"),
            ({"nda": _NDA, "counterparty": "Acme Corp", "notes": []}, "not a stuff in wire form"),
            ({"nda": _NDA, "counterparty": {"concept": "native.Number", "content": {"number": 1}}, "notes": []}, "does not accept"),
            ({"nda": _NDA, "counterparty": _PARTY, "notes": [], "stranger": _PARTY}, "not an input of the main pipe"),
        ],
    )
    def test_example_inputs(self, payload: dict[str, object], invalid: str | None) -> None:
        """Every required input present, a variable list present as `[]`, and every stuff in wire form of an accepted concept."""
        fault = example_inputs_fault(example_path="examples/mutual-nda.json", file_text=json.dumps(payload), inputs=_INPUTS)
        if invalid is None:
            assert fault is None
        else:
            assert fault is not None
            assert fault.reason == ManifestPackageReason.EXAMPLE_INVALID
            assert invalid in fault.message
