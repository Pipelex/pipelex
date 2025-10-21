from typing_extensions import override

from pipelex.observer.observer_protocol import ObserverProtocol, PayloadType


class MultiObserver(ObserverProtocol):
    def __init__(self, observers: dict[str, ObserverProtocol] | None = None) -> None:
        self.observers: dict[str, ObserverProtocol] = observers or {}

    def add_observer(self, name: str, observer: ObserverProtocol) -> None:
        """Add an observer with a given name."""
        self.observers[name] = observer

    def remove_observer(self, name: str) -> None:
        """Remove an observer by name."""
        self.observers.pop(name, None)

    @override
    async def observe_before_run(self, payload: PayloadType) -> None:
        for observer in self.observers.values():
            await observer.observe_before_run(payload)

    @override
    async def observe_after_successful_run(self, payload: PayloadType) -> None:
        for observer in self.observers.values():
            await observer.observe_after_successful_run(payload)

    @override
    async def observe_after_failing_run(self, payload: PayloadType) -> None:
        for observer in self.observers.values():
            await observer.observe_after_failing_run(payload)
