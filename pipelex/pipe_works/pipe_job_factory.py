# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pipelex.config import get_config
from pipelex.core.pipe import PipeAbstract
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.job_metadata import JobMetadata
from pipelex.pipe_works.pipe_job import PipeJob


class PipeJobFactory:
    @classmethod
    def make_pipe_job(
        cls,
        pipe: PipeAbstract,
        pipe_run_params: Optional[PipeRunParams] = None,
        working_memory: Optional[WorkingMemory] = None,
        job_metadata: Optional[JobMetadata] = None,
        output_name: Optional[str] = None,
    ) -> PipeJob:
        job_metadata = job_metadata or JobMetadata(session_id=get_config().session_id)
        working_memory = working_memory or WorkingMemory()
        if not pipe_run_params:
            pipe_run_params = PipeRunParams()
        return PipeJob(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            pipe=pipe,
            output_name=output_name,
        )
