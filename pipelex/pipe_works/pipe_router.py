# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional, cast

from typing_extensions import override

from pipelex import log
from pipelex.core.pipe_output import PipeOutputType
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.hub import get_required_pipe
from pipelex.job_metadata import JobMetadata
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.pipe_works.pipe_router_protocol import PipeJob, PipeRouterProtocol


class PipeRouter(PipeRouterProtocol):
    @override
    async def run_pipe_job(
        self,
        pipe_job: PipeJob,
        wfid: Optional[str] = None,
    ) -> PipeOutputType:  # pyright: ignore[reportInvalidTypeVarUse]
        log.debug("PipeRouterSimple run_pipe_job")
        working_memory = pipe_job.working_memory

        pipe = pipe_job.pipe
        log.verbose(f"Routing {pipe.__class__.__name__} pipe '{pipe_job.pipe.code}': {pipe.definition}")

        pipe_output = await pipe.run_pipe(
            pipe_code=pipe_job.pipe.code,
            job_metadata=pipe_job.job_metadata,
            working_memory=working_memory,
            output_name=pipe_job.output_name,
            pipe_run_params=pipe_job.pipe_run_params,
        )

        log.debug("Workflow complete")
        return cast(PipeOutputType, pipe_output)

    @override
    async def run_pipe_code(
        self,
        pipe_code: str,
        pipe_run_params: Optional[PipeRunParams] = None,
        job_metadata: Optional[JobMetadata] = None,
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        wfid: Optional[str] = None,
    ) -> PipeOutputType:  # pyright: ignore[reportInvalidTypeVarUse]
        log.debug(f"run_pipe_direct: output_name={output_name}")
        pipe = get_required_pipe(pipe_code)
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=pipe_run_params,
            working_memory=working_memory,
            job_metadata=job_metadata,
            output_name=output_name,
        )
        pipe_output: PipeOutputType = await self.run_pipe_job(
            pipe_job=pipe_job,
            wfid=wfid,
        )
        return pipe_output
