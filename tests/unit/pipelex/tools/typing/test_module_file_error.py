from pipelex.tools.typing.module_inspector import ModuleFileError


class TestModuleFileError:
    def test_exception_inheritance(self):
        """Test that ModuleFileError inherits from Exception."""
        error = ModuleFileError("test message")
        assert isinstance(error, Exception)
        assert str(error) == "test message"
