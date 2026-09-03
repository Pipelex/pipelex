from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from pipelex.cogt.config_cogt import InferenceConfig
from pipelex.graph.graph_config import GraphConfig
from pipelex.language.mthds_config import MthdsConfig
from pipelex.methods.methods_config import MethodsConfig
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.system.configuration.pipe_func_config import PipeFuncConfig
from pipelex.tools.aws.aws_config import AwsConfig
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.secrets.secrets_config import SecretsProviderConfig
from pipelex.tools.storage.storage_config import StorageConfig


class ConfigPaths:
    # Dev-only config (not synced with kit)
    DEV_CONFIG_DIR_PATH = "./.pipelex-dev"


class ValidationErrorReaction(StrEnum):
    RAISE = "raise"
    LOG = "log"
    IGNORE = "ignore"


class AgentTarget(StrEnum):
    CURSOR = "cursor"
    AGENTS = "agents"
    CLAUDE = "claude"


class KitConfig(ConfigModel):
    preferred_agent_targets: list[AgentTarget] = Field(strict=False)

    @field_validator("preferred_agent_targets", mode="before")
    @classmethod
    def _coerce_targets(cls, value: object) -> object:
        if isinstance(value, list):
            return [AgentTarget(item) if isinstance(item, str) else item for item in value]  # pyright: ignore[reportUnknownVariableType]
        return value

    @model_validator(mode="after")
    def _validate_targets(self) -> Self:
        if not self.preferred_agent_targets:
            msg = "preferred_agent_targets must contain at least one target"
            raise ValueError(msg)
        if AgentTarget.CURSOR in self.preferred_agent_targets and len(self.preferred_agent_targets) > 1:
            msg = "preferred_agent_targets cannot mix 'cursor' with other targets (cursor uses a separate mechanism)"
            raise ValueError(msg)
        return self


class PipeRunConfig(ConfigModel):
    pipe_stack_limit: int


class ReportingConfig(ConfigModel):
    is_log_costs_to_console: bool
    is_generate_cost_report_file_enabled: bool
    cost_report_dir_path: str
    cost_report_base_name: str
    cost_report_extension: str
    cost_report_unit_scale: Annotated[float, Field(gt=0)]


class TracingBackend(StrEnum):
    NDJSON = "ndjson"
    DYNAMODB = "dynamodb"


class NdjsonTracingConfig(ConfigModel):
    traces_dir: str


class DynamoDBTracingConfig(ConfigModel):
    table_name: str
    region: str


class TracingConfig(ConfigModel):
    is_enabled: bool
    backend: TracingBackend = Field(strict=False)
    ndjson: NdjsonTracingConfig | None = None
    dynamodb: DynamoDBTracingConfig | None = None


class ObserverConfig(ConfigModel):
    observer_dir: str


class ScanConfig(ConfigModel):
    excluded_dirs: frozenset[str]

    @field_validator("excluded_dirs", mode="before")
    @classmethod
    def validate_excluded_dirs(cls, value: list[str] | frozenset[str]) -> frozenset[str]:
        if isinstance(value, frozenset):
            return value
        return frozenset(value)


class BuilderConfig(ConfigModel):
    fix_loop_max_attempts: int
    default_output_dir: str
    default_bundle_file_name: str
    default_directory_base_name: str


class PipelineExecutionConfig(ConfigModel):
    is_normalize_data_urls_to_storage: bool
    is_mock_inputs: bool
    is_generate_graph: bool
    is_generate_usage: bool
    graph: GraphConfig

    # Bounded fan-out concurrency for PipeBatch (the in-process backpressure pillar, short of a durable execution backend).
    # An integer caps the number of branches executed at once; the literal "unbounded" disables the bound.
    max_concurrency: Annotated[int, Field(ge=1)] | Literal["unbounded"]

    def with_execution_overrides(
        self,
        *,
        generate_graph: bool | None = None,
        generate_usage: bool | None = None,
        force_include_full_data: bool | None = None,
        mock_inputs: bool | None = None,
    ) -> Self:
        """Create a copy of this config with optional overrides.

        Args:
            generate_graph: If not None, overrides is_generate_graph (graph node/edge events + GraphSpec assembly).
            generate_usage: If not None, overrides is_generate_usage (emit usage/cost tracing events).
            force_include_full_data: If not None, overrides all graph.data_inclusion flags
                (stuff_json_content, stuff_text_content, stuff_html_content, error_stack_traces).
            mock_inputs: If not None, overrides is_mock_inputs. When True, generates mock
                data for missing required inputs (for dry-run validation).

        Returns:
            A new PipelineExecutionConfig with the specified overrides applied.
        """
        updates: dict[str, bool | GraphConfig] = {}

        if generate_graph is not None:
            updates["is_generate_graph"] = generate_graph

        if generate_usage is not None:
            updates["is_generate_usage"] = generate_usage

        if mock_inputs is not None:
            updates["is_mock_inputs"] = mock_inputs

        if force_include_full_data is not None:
            new_data_inclusion = self.graph.data_inclusion.model_copy(
                update={
                    "stuff_json_content": force_include_full_data,
                    "stuff_text_content": force_include_full_data,
                    "stuff_html_content": force_include_full_data,
                    "error_stack_traces": force_include_full_data,
                }
            )
            updates["graph"] = self.graph.model_copy(update={"data_inclusion": new_data_inclusion})

        if updates:
            return self.model_copy(update=updates)
        return self


class PluginsConfig(ConfigModel):
    # Names of discovered plugins to skip at startup (a denylist; discovery is the
    # source of truth for presence). Denylisting a plugin core requires
    # unconditionally is a startup error. There is intentionally no allowlist.
    disabled: list[str]


class RuntimeConfig(ConfigModel):
    """Kernel-layer, process-scoped infrastructure — what ``runtime_hub`` brokers.

    The machinery present at execution time whatever is loaded, per
    ``docs/contribute/hub-layering.md``: storage, secrets, logging, cloud credentials,
    reporting, tracing, observation, and the plugin system's own denylist.
    """

    storage: StorageConfig
    secrets: SecretsProviderConfig
    log: LogConfig
    aws: AwsConfig
    reporting: ReportingConfig
    tracing: TracingConfig
    observer: ObserverConfig
    plugins: PluginsConfig


class InterpreterConfig(ConfigModel):
    """Library-scoped method machinery — what ``interpreter_hub`` brokers.

    Everything that only means something once ``.mthds`` content is loaded: parsing,
    pipe execution parameters, pipeline orchestration, source discovery and authoring.
    """

    mthds: MthdsConfig
    methods: MethodsConfig
    pipe_run: PipeRunConfig
    pipe_func: PipeFuncConfig
    pipeline_execution: PipelineExecutionConfig
    scan: ScanConfig
    builder: BuilderConfig


class PipelexConfig(ConfigRoot):
    runtime: RuntimeConfig
    inference: InferenceConfig
    interpreter: InterpreterConfig
    kit: KitConfig
