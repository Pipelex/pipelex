from typing import Any, Callable

WorkflowType = type[Any]
WorkflowList = list[WorkflowType]
ActivityType = Callable[[Any], Any]
ActivityList = list[ActivityType]
