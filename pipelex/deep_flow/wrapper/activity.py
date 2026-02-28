from datetime import timedelta
from typing import Awaitable, Callable, ParamSpec, TypeVar

from pydantic import BaseModel
from temporalio import workflow

from pipelex.config import get_config

T = TypeVar("T")
P = ParamSpec("P")
B = TypeVar("B", bound=BaseModel)


def start_tprl_activity(
    activity: Callable[[B], Awaitable[T]],
    workflow_arg: B,
) -> Awaitable[T]:
    worker_config = get_config().deep_flow.worker_config
    max_timeout = timedelta(hours=24)

    return workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
        activity=activity,
        arg=workflow_arg,
        retry_policy=worker_config.retry_policy,
        schedule_to_close_timeout=max_timeout,
        schedule_to_start_timeout=max_timeout,
        start_to_close_timeout=max_timeout,
        heartbeat_timeout=max_timeout,
    )
