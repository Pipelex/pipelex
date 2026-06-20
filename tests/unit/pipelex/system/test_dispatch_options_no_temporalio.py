from datetime import timedelta
from typing import Any

from pipelex.system.configuration.config_temporal import DispatchOptions


class TestDispatchOptionsNoTemporalio:
    def test_construct_without_temporalio(self) -> None:
        """``DispatchOptions`` MUST be constructible without ``temporalio`` installed.

        Complement to ``test_config_temporal_optional_dep`` (the AST scan): that test
        proves ``config_temporal`` imports no ``temporalio`` at module level, but it
        CANNOT catch a regression of the ``RetryPolicy = Any`` runtime placeholder to a
        bare forward ref — that still imports fine (deferred pydantic schema) and only
        blows up with ``PydanticUserError`` the moment a ``DispatchOptions`` is
        constructed. Core config-load paths materialize ``DispatchOptions``, so this must
        hold on every core install (``temporalio`` ships only with ``pipelex-temporal``).
        """
        # At runtime ``DispatchOptions.retry_policy`` is ``Any`` (config_temporal binds
        # ``RetryPolicy = Any`` when temporalio is absent), so any object is accepted. The
        # type checker sees the real ``temporalio`` ``RetryPolicy`` under TYPE_CHECKING,
        # hence the explicit ``Any`` local.
        retry_policy: Any = None
        options = DispatchOptions(
            task_queue=None,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        kwargs = options.to_execute_kwargs()
        assert kwargs["start_to_close_timeout"] == timedelta(seconds=30)
        assert kwargs["retry_policy"] is None
        # ``task_queue=None`` is omitted so Temporal routes to the workflow's own queue.
        assert "task_queue" not in kwargs
