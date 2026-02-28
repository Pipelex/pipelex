from typing import Callable

from pydantic import BaseModel


class SandboxManager(BaseModel):
    is_in_sandbox_callable: Callable[[], bool] | None = None

    def set_sandbox_callable(self, sandbox_callable: Callable[[], bool]):
        """Sets a callable function to determine if we're in a sandbox, which would prevent importing unsafe modules,
        and in particular prevent logging with default methods.

        Args:
            sandbox_callable: A function that returns a boolean indicating if it's safe to log using default methods.
        """
        self.is_in_sandbox_callable = sandbox_callable

    def is_in_sandbox(self) -> bool:
        """Returns:
        bool: True if we're in a sandbox, False otherwise.
        """
        if self.is_in_sandbox_callable is None:
            # by default, we are not in a sandbox
            return False
        else:
            return self.is_in_sandbox_callable()


sandbox_manager = SandboxManager()
