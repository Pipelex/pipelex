from pipelex.temporal.task_manager import TaskManager


class DeepFlowHub:
    """DeepFlowHub serves as a central dependency manager to break cyclic imports between components.
    It provides access to core providers and factories through a singleton instance,
    allowing components to retrieve dependencies based on protocols without direct imports that could create cycles.
    """

    def __init__(self):
        self._task_manager: TaskManager | None = None

    # Setters

    def set_task_manager(self, task_manager: TaskManager):
        self._task_manager = task_manager

    def reset(self):
        self._task_manager = None

    # Getters

    def get_required_task_manager(self) -> TaskManager:
        if self._task_manager is None:
            msg = "TaskManager instance is not set. You must initialize Pipelex first."
            raise RuntimeError(msg)
        return self._task_manager


deep_flow_hub = DeepFlowHub()

# root convenience functions


def get_task_manager() -> TaskManager:
    return deep_flow_hub.get_required_task_manager()
