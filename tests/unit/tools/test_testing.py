from pipelex.tools.runtime_manager import runtime_manager


def test_testing():
    assert runtime_manager.run_mode == "unit_test"
