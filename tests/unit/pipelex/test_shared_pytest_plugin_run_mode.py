from pipelex.system.runtime import runtime_manager

# Read while pytest imports this module to collect it, before any fixture has run: a boot here, such as a
# top-level `Pipelex.make()`, is exactly what the run mode must already cover.
IS_UNIT_TESTING_AT_COLLECTION = runtime_manager.is_unit_testing


class TestSharedPytestPluginRunMode:
    def test_the_run_mode_is_a_test_mode_before_any_fixture_runs(self) -> None:
        """The shared plugin sets the run mode at configure time, so a boot during collection keeps the Gateway stream off."""
        assert IS_UNIT_TESTING_AT_COLLECTION is True
