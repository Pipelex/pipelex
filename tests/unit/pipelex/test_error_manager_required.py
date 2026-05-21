import pytest

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_manager import ErrorManager
from pipelex.system.registries.singleton import MetaSingleton


class TestErrorManagerRequired:
    def test_type_uri_raises_runtime_error_when_manager_cleared(self):
        """``PipelexError.type_uri()`` must raise ``RuntimeError`` when the ``ErrorManager`` singleton is absent.

        Locks in the hard-stop contract: no silent fallback to a constant;
        bootstrap must run first. Restores via direct ``MetaSingleton.instances``
        assignment rather than ``ErrorManager(errors_config=...)`` because the
        metaclass silently no-ops re-construction.
        """
        saved = ErrorManager.get_required_instance()
        ErrorManager.clear_instance()
        try:
            assert ErrorManager.get_instance() is None
            with pytest.raises(RuntimeError, match="ErrorManager is not initialized"):
                PipelexError.type_uri()
        finally:
            MetaSingleton.instances[ErrorManager] = saved
