from pipelex.tools.environment import is_env_set
from pipelex.tools.runtime_manager import RunMode, runtime_manager


def test_testing():
    match runtime_manager.run_mode:
        case RunMode.CI_TEST:
            assert is_env_set("GITHUB_ACTIONS") or is_env_set("CI")
        case RunMode.UNIT_TEST:
            assert not is_env_set("GITHUB_ACTIONS") and not is_env_set("CI")
        case _:
            raise RuntimeError(f"Invalid run mode: {runtime_manager.run_mode}")
