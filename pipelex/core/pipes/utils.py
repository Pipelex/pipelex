from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.exceptions import PipeStackOverflowError


def monitor_pipe_stack(pipe_run_params: PipeRunParams):
    pipe_stack = pipe_run_params.pipe_stack
    limit = pipe_run_params.pipe_stack_limit
    if len(pipe_stack) > limit:
        msg = f"Exceeded pipe stack limit of {limit}. You can raise that limit in the config. Stack:\n{pipe_stack}"
        raise PipeStackOverflowError(message=msg, limit=limit, pipe_stack=pipe_stack)
