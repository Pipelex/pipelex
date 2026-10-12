"""A pipe job as an orchestrator outside this process receives it.

A job handed to an orchestrator other than the in-process one, such as Temporal, travels as that orchestrator's
payloads, which it bounds: Temporal refuses a payload over 2 MB. The files submitted with the job's bundles travel in
its crate, so before the job leaves, every file a step reads only when it runs, such as an office template, moves to the
run's storage and the crate carries a reference to it. The files read when the method loads, such as an HTML template,
stay inline, and their size is bounded when the bundle loads (`MAX_LOAD_STAGE_RESOURCES_BYTES`).

Every dispatcher calls `prepare_job_for_remote_dispatch` at the moment the job leaves the process:
`PipelexMTHDSProtocol.execute` when the hub's pipe run belongs to a boot orchestrator's plugin, and a host dispatching
through an orchestrator of the registry, such as the API server, for every mode but `direct`.
"""

from pipelex.libraries.bundle_resources import relocate_run_resources
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.runtime_hub import get_storage_provider
from pipelex.system.storage_scope import DRY_RUN_STORAGE_SCOPE


async def prepare_job_for_remote_dispatch(*, pipe_job: PipeJob) -> PipeJob:
    """The job with the files its steps read only when they run stored under the run's scope and carried by reference.

    A dry run's files move too, since a dry run hands its office templates to the engine's checker, which reads them
    back under the run's read scope as a print does. A run whose storage scope is the dry-run placeholder stores
    nothing, so its files stay inline. The job is returned unchanged when it carries no submitted file.
    """
    crate = pipe_job.library_crate
    if crate is None or not crate.bundle_resources:
        return pipe_job
    storage_scope = pipe_job.job_metadata.run_metadata.storage_scope
    if storage_scope == DRY_RUN_STORAGE_SCOPE:
        return pipe_job
    relocated_crate = await relocate_run_resources(crate=crate, storage_provider=get_storage_provider(), storage_scope=storage_scope)
    return pipe_job.model_copy(update={"library_crate": relocated_crate})
