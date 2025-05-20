# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional, Tuple

from pipelex import pretty_print
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeOutputMultiplicity, PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.hub import get_mission_manager, get_pipe_router, get_required_pipe
from pipelex.mission.job_metadata import JobMetadata
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory


async def execute_mission(
    pipe_code: str,
    working_memory: Optional[WorkingMemory] = None,
    output_name: Optional[str] = None,
    output_multiplicity: Optional[PipeOutputMultiplicity] = None,
    dynamic_output_concept_code: Optional[str] = None,
) -> Tuple[PipeOutput, str]:
    mission = get_mission_manager().add_new_mission()
    pipe = get_required_pipe(pipe_code=pipe_code)

    job_metadata = JobMetadata(
        mission_id=mission.mission_id,
    )

    pipe_run_params = PipeRunParams(
        output_multiplicity=output_multiplicity,
        dynamic_output_concept_code=dynamic_output_concept_code,
    )

    pretty_print(pipe, title=f"Running pipe '{pipe_code}'")
    if working_memory:
        working_memory.pretty_print_summary()

    pipe_job = PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=pipe_run_params,
        job_metadata=job_metadata,
        working_memory=working_memory,
        output_name=output_name,
    )

    return await get_pipe_router().run_pipe_job(pipe_job), mission.mission_id
