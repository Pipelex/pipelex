from typing import Protocol

from typing_extensions import override

from pipelex.pipeline.activity.activity_models import ActivityCallback, ActivityReport


class ActivityManagerProtocol(Protocol):
    def setup(self) -> None:
        pass

    def teardown(self) -> None:
        pass

    def add_activity_callback(self, key: str, callback: ActivityCallback):
        pass

    def remove_activity_callback(self, key: str):
        pass

    def dispatch_activity(self, activity_report: ActivityReport):
        pass


class ActivityManagerNoOp(ActivityManagerProtocol):
    @override
    def setup(self) -> None:
        pass

    @override
    def teardown(self) -> None:
        pass

    @override
    def add_activity_callback(self, key: str, callback: ActivityCallback):
        pass

    @override
    def remove_activity_callback(self, key: str):
        pass

    @override
    def dispatch_activity(self, activity_report: ActivityReport):
        pass
