from enum import StrEnum
from typing import Annotated, Literal, Self

import shortuuid
from pydantic import Field, field_validator, model_validator

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cogt.config_cogt import Cogt
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.graph.graph_config import GraphConfig
from pipelex.language.mthds_config import MthdsConfig
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.configuration.config_root import ConfigRoot
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


class PipeFuncConfig(ConfigModel):
    # When true, this process treats PipeFunc as sandbox-hosted: it carries the customer's PipeFunc
    # code without ever importing or executing it. Library loading captures the customer .py source
    # as text (onto the crate) instead of registering it in the func_registry, and the PipeFunc
    # validators skip the func_registry lookup + return-type checks — the real function is registered
    # and validated inside the sandbox, not here. Local/direct execution leaves this false, which is
    # byte-identical to the pre-existing behavior. This is a hosted-deploy flag, not a client
    # preference, so it is intentionally absent from the .pipelex/ override file.
    is_sandbox_hosted: bool


class DryRunConfig(ConfigModel):
    text_gen_truncate_length: int
    nb_list_items: int
    nb_extract_pages: int
    image_urls: list[str]
    allowed_to_fail_pipes: list[str] = Field(default_factory=list)

    @field_validator("image_urls", mode="before")
    @classmethod
    def validate_image_urls(cls, value: list[str]) -> list[str]:
        if not value:
            msg = "dry_run_config.image_urls must be a non-empty list"
            raise PipelexConfigError(msg)
        return value


class PromptingConfig(ConfigModel):
    default_prompting_style: TemplatingStyle
    prompting_styles: dict[str, TemplatingStyle]

    def get_prompting_style(self, prompting_target: PromptingTarget | None = None) -> TemplatingStyle | None:
        if prompting_target:
            return self.prompting_styles.get(prompting_target, self.default_prompting_style)
        return None


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
    graph_config: GraphConfig

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
            force_include_full_data: If not None, overrides all graph_config.data_inclusion flags
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
            new_data_inclusion = self.graph_config.data_inclusion.model_copy(
                update={
                    "stuff_json_content": force_include_full_data,
                    "stuff_text_content": force_include_full_data,
                    "stuff_html_content": force_include_full_data,
                    "error_stack_traces": force_include_full_data,
                }
            )
            updates["graph_config"] = self.graph_config.model_copy(update={"data_inclusion": new_data_inclusion})

        if updates:
            return self.model_copy(update=updates)
        return self


class Pipelex(ConfigModel):
    storage_config: StorageConfig
    secrets_config: SecretsProviderConfig
    log_config: LogConfig
    aws_config: AwsConfig

    prompting_config: PromptingConfig
    mthds_config: MthdsConfig

    dry_run_config: DryRunConfig
    pipe_run_config: PipeRunConfig
    pipe_func_config: PipeFuncConfig
    pipeline_execution_config: PipelineExecutionConfig
    reporting_config: ReportingConfig
    tracing_config: TracingConfig
    observer_config: ObserverConfig
    scan_config: ScanConfig
    builder_config: BuilderConfig
    kit_config: KitConfig


class MigrationConfig(ConfigModel):
    migration_maps: dict[str, dict[str, str]]

    def text_in_renaming_keys(self, text: str, *, category: str) -> list[tuple[str, str]]:
        renaming_map = self.migration_maps.get(category)
        if not renaming_map:
            return []
        return [(key, value) for key, value in renaming_map.items() if text in key]

    def text_in_renaming_values(self, text: str, *, category: str) -> list[tuple[str, str]]:
        renaming_map = self.migration_maps.get(category)
        if not renaming_map:
            return []
        return [(key, value) for key, value in renaming_map.items() if text in value]


class PluginsConfig(ConfigModel):
    # Names of discovered plugins to skip at startup (a denylist; discovery is the
    # source of truth for presence). Denylisting a plugin core requires
    # unconditionally is a startup error. There is intentionally no allowlist.
    disabled: list[str]

    # Boot *this process* under the orchestrator plugin of this name. A boot-orchestrator
    # plugin (e.g. the Temporal plugin) claims the process-global hub slots in its
    # ``register`` iff ``plugins.boot_orchestrator == <its own name>``; any other value
    # (or ``None``) leaves execution in-process. Core names no orchestrator — the gate is
    # a plain name match, set programmatically (CLI ``--orchestrator`` / ``Pipelex.setup``),
    # not from ``pipelex.toml``. Optional, so it stays absent from the TOML defaults.
    boot_orchestrator: str | None = None


class PipelexConfig(ConfigRoot):
    session_id: str = shortuuid.uuid()
    cogt: Cogt
    pipelex: Pipelex
    plugins: PluginsConfig
    migration: MigrationConfig
