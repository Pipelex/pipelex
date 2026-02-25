from pydantic import BaseModel

from pipelex.system.environment import get_optional_env, is_env_var_truthy
from pipelex.types import StrEnum

RUN_MODE_ENV_VAR_KEY = "RUN_MODE"
CODEX_CLOUD_ENV_VAR_KEY = "CODEX_CLOUD"


class IntegrationMode(StrEnum):
    CI = "ci"
    CLI = "cli"
    DOCKER = "docker"
    FASTAPI = "fastapi"
    MCP = "mcp"
    N8N = "n8n"
    PYTEST = "pytest"
    PYTHON = "python"

    @property
    def requires_terms_acceptance(self) -> bool:
        match self:
            case IntegrationMode.CI:
                return False
            case IntegrationMode.CLI:
                return True
            case IntegrationMode.DOCKER:
                return True
            case IntegrationMode.FASTAPI:
                return True
            case IntegrationMode.MCP:
                return True
            case IntegrationMode.N8N:
                return True
            case IntegrationMode.PYTEST:
                return True
            case IntegrationMode.PYTHON:
                return True


class RunMode(StrEnum):
    NORMAL = "normal"
    UNIT_TEST = "unit_test"
    CI_TEST = "ci_test"
    CODEX_CLOUD = "codex_cloud"
    CODEX_CLOUD_TEST = "codex_cloud_test"

    @classmethod
    def get_from_env_var(cls) -> "RunMode":
        if mode_str := get_optional_env(RUN_MODE_ENV_VAR_KEY):
            return RunMode(mode_str)
        elif is_env_var_truthy(key=CODEX_CLOUD_ENV_VAR_KEY):
            return RunMode.CODEX_CLOUD
        else:
            return RunMode.NORMAL


class WorkerMode(StrEnum):
    """Used for external worker, note that it can be run "for unit tests" even if it's not a unit test."""

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
    _worker_mode: WorkerMode | None = None

    problem_reactions: ProblemReactions = ProblemReactions(
        template_inputs=ProblemReaction.LOG,
        prompt_templates=ProblemReaction.LOG,
        job=ProblemReaction.LOG,
    )

    def set_run_mode(self, run_mode: RunMode):
        self._run_mode = run_mode

    def set_worker_mode(self, worker_mode: WorkerMode):
        self._worker_mode = worker_mode

    @property
    def environment(self) -> RunEnvironment:
        return self._environment

    @property
    def run_mode(self) -> RunMode:
        return self._run_mode

    @property
    def worker_mode(self) -> WorkerMode | None:
        return self._worker_mode

    @property
    def is_unit_testing(self) -> bool:
        match self.run_mode:
            case RunMode.NORMAL:
                return False
            case RunMode.CODEX_CLOUD:
                return False
            case RunMode.UNIT_TEST:
                return True
            case RunMode.CI_TEST:
                return True
            case RunMode.CODEX_CLOUD_TEST:
                return True

    @property
    def is_ci_testing(self) -> bool:
        match self.run_mode:
            case RunMode.NORMAL:
                return False
            case RunMode.CODEX_CLOUD:
                return False
            case RunMode.UNIT_TEST:
                return False
            case RunMode.CI_TEST:
                return True
            case RunMode.CODEX_CLOUD_TEST:
                return True

    @property
    def is_in_codex_cloud(self) -> bool:
        return self.run_mode in {RunMode.CODEX_CLOUD, RunMode.CODEX_CLOUD_TEST}


runtime_manager = RuntimeManager()
