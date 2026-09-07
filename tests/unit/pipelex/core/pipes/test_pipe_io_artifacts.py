"""Pin `PipeIOArtifacts` and the rendering that turns it into the three sibling files.

The model is a grouping of the validate report's three artifacts under the report's own names;
the rendering is the projection corpus's byte discipline, so a results directory and the
committed fixture corpus hold byte-identical files for the same bundle. Pure unit test, no
Pipelex boot: the artifacts are hand-built. The builder itself needs a loaded library and is
pinned in the integration twin of this module.
"""

from __future__ import annotations

import json

import pytest
from mthds.protocol.input_form import PipeInputFormDescriptor, TextField
from mthds.protocol.output_form import PipeOutputFormDescriptor
from pydantic import ValidationError

from pipelex.core.pipes.pipe_io_artifacts import (
    INPUT_FORM_FILE_NAME,
    OUTPUT_FORM_FILE_NAME,
    PIPE_IO_CONTRACTS_FILE_NAME,
    PipeIOArtifacts,
    render_pipe_io_artifact_files,
)
from pipelex.core.pipes.variable_multiplicity import PresenceMarker
from pipelex.pipeline.pipe_io_contracts import IOMultiplicity, PipeIOContract, PipeOutputContract

_PIPE_REF = "alpha.do_it"


def _artifacts() -> PipeIOArtifacts:
    # A non-ASCII description proves `ensure_ascii=False` is honoured, not just claimed.
    slot = TextField(name="doc", required=True, presence=PresenceMarker.PLAIN, gating=False, description="Le résumé à traiter")
    output = TextField(name="doc", required=True, description="Le résumé traité")
    return PipeIOArtifacts(
        pipe_io_contracts={
            _PIPE_REF: PipeIOContract(
                inputs={},
                output=PipeOutputContract(
                    concept_ref="native.Text",
                    multiplicity=IOMultiplicity.SINGLE,
                    item_count=None,
                    optional=False,
                    json_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                ),
            ),
        },
        input_form={_PIPE_REF: PipeInputFormDescriptor(fields=[slot])},
        output_form={_PIPE_REF: PipeOutputFormDescriptor(field=output)},
    )


class TestPipeIOArtifactsModel:
    def test_forbids_extra_fields(self) -> None:
        """A fourth artifact is a model change, never a stowaway key."""
        with pytest.raises(ValidationError):
            PipeIOArtifacts.model_validate({"pipe_io_contracts": {}, "input_form": {}, "output_form": {}, "extra": {}})

    def test_round_trips_through_json_mode_dump(self) -> None:
        """The carrier survives the wire: `model_dump(mode="json")` validates back to an equal model."""
        artifacts = _artifacts()
        assert PipeIOArtifacts.model_validate(artifacts.model_dump(mode="json")) == artifacts


class TestRenderPipeIOArtifactFiles:
    def test_yields_exactly_the_three_sibling_files(self) -> None:
        files = render_pipe_io_artifact_files(_artifacts())
        assert set(files) == {PIPE_IO_CONTRACTS_FILE_NAME, INPUT_FORM_FILE_NAME, OUTPUT_FORM_FILE_NAME}
        assert (PIPE_IO_CONTRACTS_FILE_NAME, INPUT_FORM_FILE_NAME, OUTPUT_FORM_FILE_NAME) == (
            "pipe_io_contracts.json",
            "input_form.json",
            "output_form.json",
        )

    def test_each_file_is_the_corpus_byte_discipline_over_the_json_mode_dump(self) -> None:
        """Two-space indent, `ensure_ascii=False`, one trailing newline, keyed by `pipe_ref`."""
        artifacts = _artifacts()
        files = render_pipe_io_artifact_files(artifacts)
        expected = {
            PIPE_IO_CONTRACTS_FILE_NAME: {ref: contract.model_dump(mode="json") for ref, contract in artifacts.pipe_io_contracts.items()},
            INPUT_FORM_FILE_NAME: {ref: descriptor.model_dump(mode="json") for ref, descriptor in artifacts.input_form.items()},
            OUTPUT_FORM_FILE_NAME: {ref: descriptor.model_dump(mode="json") for ref, descriptor in artifacts.output_form.items()},
        }
        for file_name, payload in expected.items():
            text = files[file_name]
            assert text == json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
            assert text.endswith("}\n")
            assert not text.endswith("\n\n")
            assert json.loads(text) == payload
        for file_name in (INPUT_FORM_FILE_NAME, OUTPUT_FORM_FILE_NAME):
            assert "résumé" in files[file_name], "ensure_ascii=False: the non-ASCII description is written verbatim, not escaped"
