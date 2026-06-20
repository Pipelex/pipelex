"""Regression: ``DispatchOptions`` (a frozen Pydantic dataclass) MUST be
importable AND constructible without ``temporalio`` installed.

``temporalio`` is in ``[project.optional-dependencies].temporal``;
``pipelex.system.configuration.configs`` imports ``config_temporal`` unconditionally.
The ``retry_policy`` field is annotated ``RetryPolicy`` (a ``temporalio`` type),
which is bound to ``Any`` at runtime via the ``else`` branch of the
``TYPE_CHECKING`` guard. Without that runtime binding the dataclass carries an
unresolved forward ref: it would still import (Pydantic defers the schema) but
raise ``PydanticUserError`` the moment a ``DispatchOptions`` is constructed on an
install lacking the ``temporal`` extra.

The sibling ``test_config_temporal_optional_dep.py`` AST-scans for module-level
``temporalio`` imports; it does NOT catch a regression to a bare forward ref
(which adds no import statement). This runtime check is the complement: it
exercises the actual class-definition + construction path with ``temporalio``
made unavailable, in a fresh subprocess so the block precedes any import.
"""

import subprocess  # noqa: S404
import sys
import textwrap

_NO_TEMPORALIO_SCRIPT = textwrap.dedent(
    """
    import sys
    import importlib.abc


    class _Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name == "temporalio" or name.startswith("temporalio."):
                raise ModuleNotFoundError(f"No module named {name!r} (blocked by test)")
            return None


    sys.meta_path.insert(0, _Blocker())

    # Sanity: the block is actually in force.
    try:
        import temporalio  # noqa: F401

        raise AssertionError("temporalio import was NOT blocked")
    except ModuleNotFoundError:
        pass

    from datetime import timedelta

    from pipelex.system.configuration.config_temporal import DispatchOptions

    # Construct + read back through to_execute_kwargs. retry_policy is Any at
    # runtime, so an arbitrary sentinel stands in for the temporalio RetryPolicy.
    dispatch = DispatchOptions(
        task_queue=None,
        start_to_close_timeout=timedelta(seconds=5),
        retry_policy=object(),
        heartbeat_timeout=timedelta(seconds=2),
    )
    kwargs = dispatch.to_execute_kwargs()
    assert "task_queue" not in kwargs, kwargs
    assert kwargs["start_to_close_timeout"] == timedelta(seconds=5), kwargs
    assert kwargs["heartbeat_timeout"] == timedelta(seconds=2), kwargs
    assert "retry_policy" in kwargs, kwargs

    print("NO_TEMPORALIO_OK")
    """
)


class TestDispatchOptionsNoTemporalio:
    def test_import_and_construct_without_temporalio(self) -> None:
        """Fresh interpreter with ``temporalio`` blocked: importing
        ``config_temporal`` and constructing a ``DispatchOptions`` must both
        succeed (the load-bearing optional-dependency invariant).
        """
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _NO_TEMPORALIO_SCRIPT],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"DispatchOptions could not be imported/constructed without temporalio.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "NO_TEMPORALIO_OK" in result.stdout, result.stdout
