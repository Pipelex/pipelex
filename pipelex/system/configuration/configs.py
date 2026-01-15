import shortuuid
from pydantic import Field, field_validator

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cogt.config_cogt import Cogt
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.graph.graph_config import GraphConfig
from pipelex.language.plx_config import PlxConfig
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.tools.aws.aws_config import AwsConfig
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.storage.storage_config import StorageConfig
from pipelex.types import Self, StrEnum


class ConfigPaths:
    DEFAULT_CONFIG_DIR_PATH = "./.pipelex"
    INFERENCE_DIR_NAME = "inference"
    INFERENCE_DIR_PATH = f"{DEFAULT_CONFIG_DIR_PATH}/{INFERENCE_DIR_NAME}"
    BACKENDS_FILE_NAME = "backends.toml"
    BACKENDS_FILE_PATH = f"{INFERENCE_DIR_PATH}/{BACKENDS_FILE_NAME}"
    BACKENDS_DIR_NAME = "backends"
    BACKENDS_DIR_PATH = f"{INFERENCE_DIR_PATH}/{BACKENDS_DIR_NAME}"
    ROUTING_PROFILES_FILE_NAME = "routing_profiles.toml"
    ROUTING_PROFILES_FILE_PATH = f"{INFERENCE_DIR_PATH}/{ROUTING_PROFILES_FILE_NAME}"
    MODEL_DECKS_DIR_NAME = "deck"
    MODEL_DECKS_DIR_PATH = f"{INFERENCE_DIR_PATH}/{MODEL_DECKS_DIR_NAME}"
    BASE_DECK_FILE_NAME = "base_deck.toml"
    BASE_DECK_FILE_PATH = f"{MODEL_DECKS_DIR_PATH}/{BASE_DECK_FILE_NAME}"
    OVERRIDES_DECK_FILE_NAME = "overrides.toml"
    OVERRIDES_DECK_FILE_PATH = f"{MODEL_DECKS_DIR_PATH}/{OVERRIDES_DECK_FILE_NAME}"


class ValidationErrorReaction(StrEnum):
    RAISE = "raise"
    LOG = "log"
    IGNORE = "ignore"


class PipeRunConfig(ConfigModel):
    pipe_stack_limit: int


class DryRunConfig(ConfigModel):
    apply_to_jinja2_rendering: bool
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


class StructureConfig(ConfigModel):
    is_default_text_then_structure: bool


class PromptingConfig(ConfigModel):
    default_prompting_style: TemplatingStyle
    prompting_styles: dict[str, TemplatingStyle]

    def get_prompting_style(self, prompting_target: PromptingTarget | None = None) -> TemplatingStyle | None:
        if prompting_target:
            return self.prompting_styles.get(prompting_target, self.default_prompting_style)
        return None


class FeatureConfig(ConfigModel):
    is_reporting_enabled: bool


class ReportingConfig(ConfigModel):
    is_log_costs_to_console: bool
    is_generate_cost_report_file_enabled: bool
    cost_report_dir_path: str
    cost_report_base_name: str
    cost_report_extension: str
    cost_report_unit_scale: float


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
    graph_config: GraphConfig

    def with_graph_config_overrides(
        self,
        generate_graph: bool | None = None,
        force_include_full_data: bool | None = None,
        mock_inputs: bool | None = None,
    ) -> Self:
        """Create a copy of this config with optional overrides.

        Args:
            generate_graph: If not None, overrides is_generate_graph.
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
    feature_config: FeatureConfig
    log_config: LogConfig
    aws_config: AwsConfig

    structure_config: StructureConfig
    prompting_config: PromptingConfig
    plx_config: PlxConfig

    dry_run_config: DryRunConfig
    pipe_run_config: PipeRunConfig
    pipeline_execution_config: PipelineExecutionConfig
    reporting_config: ReportingConfig
    observer_config: ObserverConfig
    scan_config: ScanConfig
    builder_config: BuilderConfig


class MigrationConfig(ConfigModel):
    migration_maps: dict[str, dict[str, str]]

    def text_in_renaming_keys(self, category: str, text: str) -> list[tuple[str, str]]:
        renaming_map = self.migration_maps.get(category)
        if not renaming_map:
            return []
        return [(key, value) for key, value in renaming_map.items() if text in key]

    def text_in_renaming_values(self, category: str, text: str) -> list[tuple[str, str]]:
        renaming_map = self.migration_maps.get(category)
        if not renaming_map:
            return []
        return [(key, value) for key, value in renaming_map.items() if text in value]


class PipelexConfig(ConfigRoot):
    session_id: str = shortuuid.uuid()
    cogt: Cogt
    pipelex: Pipelex
    migration: MigrationConfig
