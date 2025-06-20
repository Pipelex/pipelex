from abc import abstractmethod
from typing import Optional

from typing_extensions import override

from pipelex import log
from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunMode, PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.hub import get_activity_manager
from pipelex.pipeline.activity.activity_models import ActivityReport
from pipelex.pipeline.job_metadata import JobMetadata


class PipeOperator(PipeAbstract):
    @override
    async def run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        pipe_run_params.push_pipe_to_stack(pipe_code=self.code)
        self.monitor_pipe_stack(pipe_run_params=pipe_run_params)

        updated_metadata = JobMetadata(
            pipe_job_ids=[self.code],
        )
        job_metadata.update(updated_metadata=updated_metadata)

        match pipe_run_params.run_mode:
            case PipeRunMode.LIVE:
                pipe_output = await self._run_operator_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                )
            case PipeRunMode.DRY:
                pipe_output = await self._dry_run_operator_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                )
        get_activity_manager().dispatch_activity(
            activity_report=ActivityReport(
                job_metadata=job_metadata,
                content=pipe_output.main_stuff,
            )
        )

        pipe_run_params.pop_pipe_from_stack(pipe_code=self.code)

        return pipe_output

    @abstractmethod
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        pass

    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        log.info(
            f"PipeOperator: dry run method called for operator pipe: {self.code}, but no dry run method is implemented for {self.__class__.__name__}"
        )
        return await self._run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
        )
