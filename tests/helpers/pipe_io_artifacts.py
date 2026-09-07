"""A hand-built `PipeIOArtifacts` for writer tests that need one without a loaded library."""

from mthds.protocol.input_form import PipeInputFormDescriptor, TextField
from mthds.protocol.output_form import PipeOutputFormDescriptor

from pipelex.core.pipes.pipe_io_artifacts import PipeIOArtifacts
from pipelex.core.pipes.variable_multiplicity import PresenceMarker
from pipelex.pipeline.pipe_io_contracts import IOMultiplicity, PipeIOContract, PipeOutputContract


def make_pipe_io_artifacts(*, pipe_ref: str = "test_domain.my_sequence") -> PipeIOArtifacts:
    """One pipe, described three ways; a non-ASCII description proves the rendering keeps it verbatim."""
    slot = TextField(name="doc", required=True, presence=PresenceMarker.PLAIN, gating=False, description="Le résumé à traiter")
    output = TextField(name="doc", required=True, description="Le résumé traité")
    return PipeIOArtifacts(
        pipe_io_contracts={
            pipe_ref: PipeIOContract(
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
        input_form={pipe_ref: PipeInputFormDescriptor(fields=[slot])},
        output_form={pipe_ref: PipeOutputFormDescriptor(field=output)},
    )
