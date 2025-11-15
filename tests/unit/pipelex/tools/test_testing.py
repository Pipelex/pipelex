from pipelex.system.environment import is_env_var_set
from pipelex.system.runtime import RunMode, runtime_manager


def test_testing():
    match runtime_manager.run_mode:
        case RunMode.CI_TEST:
            assert is_env_var_set(key="GITHUB_ACTIONS") or is_env_var_set(key="CI")
        case RunMode.UNIT_TEST:
            assert not is_env_var_set(key="GITHUB_ACTIONS")
            assert not is_env_var_set(key="CI")
        case _:
            msg = f"Invalid run mode: {runtime_manager.run_mode}"
            raise RuntimeError(msg)
