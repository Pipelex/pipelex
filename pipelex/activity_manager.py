# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import ClassVar, Dict, Optional

from pydantic import Field

from pipelex import log
from pipelex.activity_models import ActivityCallback, ActivityReport
from pipelex.tools.exceptions import RootException


class ActivityManagerError(RootException):
    pass


class ActivityManager:
    _shared_instance: ClassVar[Optional["ActivityManager"]] = None

    def __init__(self) -> None:
        if ActivityManager._shared_instance is not None:
            raise RuntimeError("ActivityManager is a singleton. Use get_instance() to access it.")
        super().__init__()
        ActivityManager._shared_instance = self
        self.activity_callbacks: Dict[str, ActivityCallback] = Field(default_factory=dict)
        log.debug("ActivityManager initialized")

    @classmethod
    def get_instance(cls) -> "ActivityManager":
        if cls._shared_instance is None:
            raise RuntimeError("Shared instance is not set. You must call ActivityManager.setup() once.")
        return cls._shared_instance

    @classmethod
    def setup(cls) -> "ActivityManager":
        cls._shared_instance = cls()
        cls._shared_instance.activity_callbacks = {}
        return cls._shared_instance

    @classmethod
    def teardown(cls) -> None:
        if cls._shared_instance is not None:
            cls._shared_instance.reset()
        cls._shared_instance = None
        log.debug("ActivityManager teardown done")

    def reset(self):
        self.activity_callbacks = {}

    def add_activity_callback(self, key: str, callback: ActivityCallback):
        if key in self.activity_callbacks:
            log.warning(f"Activity callback with key '{key}' already exists")
        self.activity_callbacks[key] = callback

    def dispatch_activity(self, activity_report: ActivityReport):
        for key, callback in self.activity_callbacks.items():
            log.dev(f"Dispatching activity to callback '{key}'")
            callback(activity_report)


def get_activity_manager() -> ActivityManager:
    return ActivityManager.get_instance()
