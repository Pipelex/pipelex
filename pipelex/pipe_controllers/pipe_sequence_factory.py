# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, List

from typing_extensions import override

from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.pipe_controllers.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint


class PipeSequenceBlueprint(PipeBlueprint):
    steps: List[SubPipeBlueprint]


class PipeSequenceFactory(PipeSpecificFactoryProtocol[PipeSequenceBlueprint, PipeSequence]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeSequenceBlueprint,
    ) -> PipeSequence:
        pipe_steps = [step.make_sub_pipe() for step in pipe_blueprint.steps]
        return PipeSequence(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            input_concept_code=pipe_blueprint.input,
            output_concept_code=pipe_blueprint.output,
            pipe_steps=pipe_steps,
        )

    @classmethod
    @override
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeSequence:
        pipe_blueprint = PipeSequenceBlueprint.model_validate(details_dict)
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
