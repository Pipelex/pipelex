from typing import Optional

from pydantic import BaseModel

from pipelex.tools.environment import get_optional_env
from pipelex.types import StrEnum

RUN_MODE_ENV_VAR_KEY = "RUN_MODE"


class RunMode(StrEnum):
    NORMAL = "normal"
    UNIT_TEST = "unit_test"

    @classmethod
    def get_from_env_var(cls) -> "RunMode":
        if mode_str := get_optional_env(RUN_MODE_ENV_VAR_KEY):
            return RunMode(mode_str)
        else:
            return RunMode.NORMAL


class WorkerMode(StrEnum):
    """
    Used for external worker, note that it can be run "for unit tests" even if it's not a unit test.
    """

    NORMAL = "normal"
    UNIT_TEST = "unit_test"


class RunEnvironment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"

    @classmethod
    def get_from_env_var(cls) -> "RunEnvironment":
        return RunEnvironment(get_optional_env("ENV") or RunEnvironment.DEV)


class ProblemReaction(StrEnum):
    NONE = "none"
    LOG = "log"
    RAISE = "raise"


class ProblemReactions(BaseModel):
    template_inputs: ProblemReaction
    prompt_templates: ProblemReaction
    job: ProblemReaction


class RuntimeManager(BaseModel):
    _environment: RunEnvironment = RunEnvironment.get_from_env_var()
    _run_mode: RunMode = RunMode.get_from_env_var()
    _worker_mode: Optional[WorkerMode] = None

    problem_reactions: ProblemReactions = ProblemReactions(
        template_inputs=ProblemReaction.LOG,
        prompt_templates=ProblemReaction.LOG,
        job=ProblemReaction.LOG,
    )

    def set_run_mode(self, run_mode: RunMode):
        self._run_mode = run_mode
        # print(f"Set run mode to '{run_mode}'")

    def set_worker_mode(self, worker_mode: WorkerMode):
        self._worker_mode = worker_mode

    @property
    def environment(self) -> RunEnvironment:
        return self._environment

    @property
    def run_mode(self) -> RunMode:
        return self._run_mode

    @property
    def worker_mode(self) -> Optional[WorkerMode]:
        return self._worker_mode

    @property
    def is_unit_testing(self) -> bool:
        return self.run_mode == RunMode.UNIT_TEST

    @property
    def should_check_intermediate_configs(self) -> bool:
        return self.is_unit_testing


runtime_manager = RuntimeManager()
