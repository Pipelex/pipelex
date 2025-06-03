from typing import Dict

from pydantic import Field
from typing_extensions import override

from pipelex import log
from pipelex.pipeline.activity.activity_manager_protocol import ActivityManagerProtocol
from pipelex.pipeline.activity.activity_models import ActivityCallback, ActivityReport
from pipelex.tools.exceptions import RootException


class ActivityManagerError(RootException):
    pass


class ActivityManager(ActivityManagerProtocol):
    def __init__(self) -> None:
        self.activity_callbacks: Dict[str, ActivityCallback] = Field(default_factory=dict)

    @override
    def setup(self) -> None:
        self._reset()

    @override
    def teardown(self) -> None:
        self._reset()
        log.debug("ActivityManager teardown done")

    def _reset(self):
        self.activity_callbacks = {}

    @override
    def add_activity_callback(self, key: str, callback: ActivityCallback):
        if key in self.activity_callbacks:
            log.warning(f"Activity callback with key '{key}' already exists")
        self.activity_callbacks[key] = callback

    @override
    def remove_activity_callback(self, key: str):
        self.activity_callbacks.pop(key, None)

    @override
    def dispatch_activity(self, activity_report: ActivityReport):
        for key, callback in self.activity_callbacks.items():
            log.dev(f"Dispatching activity to callback '{key}'")
            callback(activity_report)
