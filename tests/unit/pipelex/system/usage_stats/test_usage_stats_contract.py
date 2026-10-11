from pathlib import Path
from typing import Any

from pipelex.system.usage_stats.usage_stats_contract import (
    CI_VARIABLES,
    CONTAINER_CGROUP_WORDS,
    CONTAINER_MARKER_FILES,
    CONTAINER_MARKER_VARIABLES,
    FALSY_VALUES,
    MODEL_HANDLE_PATTERN,
    NOTICE_DETAILS_URL,
    NOTICE_DISABLE_COMMAND,
    NOTICE_VERSION,
    PERSON_PROFILE_PROPERTY,
    PIPELEX_AGENT_COMMANDS,
    PIPELEX_COMMANDS,
    RELEASE_VERSION_PATTERN,
    SCHEMA_VERSION,
    TOOL_NAME,
    TOOL_SWITCH_NO_EFFECT_VALUES,
    TOOL_SWITCH_OFF_VALUES,
    UsageStatsArch,
    UsageStatsCodegenArtifact,
    UsageStatsCodegenOutcome,
    UsageStatsCodegenTarget,
    UsageStatsEnvVar,
    UsageStatsErrorDomain,
    UsageStatsEventName,
    UsageStatsHost,
    UsageStatsIntegration,
    UsageStatsMethodSource,
    UsageStatsOffBy,
    UsageStatsOs,
    UsageStatsOutcome,
    UsageStatsProvider,
    UsageStatsSurface,
    UsageStatsValidationOutcome,
    render_notice,
)
from pipelex.system.usage_stats.usage_stats_core import (
    BATCH_PATH,
    BUDGET_BACKGROUND_POST_DELAY_MS,
    BUDGET_CLI_IN_PROCESS_MS,
    BUDGET_DETACHED_SENDER_MS,
    BUDGET_PYTHON_EXIT_FLUSH_MS,
    BUDGET_SHUTDOWN_FLUSH_MS,
    CAPTURE_HOST,
    DISABLED_FILE_NAME,
    ID_FILE_NAME,
    INSTALLATION_ID_PATTERN,
    INTERNAL_FILE_NAME,
    LEGACY_DISABLE_ON_VALUES,
    LEGACY_KEY,
    LEGACY_MIGRATED_FILE_NAME,
    NOTICE_FILE_PREFIX,
    PROJECT_TOKEN,
    SPOOL_DIR_NAME,
    SPOOL_MAX_AGE_DAYS,
    SPOOL_MAX_FILES_PER_TOOL,
    SPOOL_STALE_CLAIM_MINUTES,
    SPOOL_STALE_TEMP_MINUTES,
    SPOOL_TOOLS,
    STATE_DIR_PARTS,
)
from pipelex.system.usage_stats.usage_stats_switches import PACKAGED_CONFIG_PATH, packaged_default_says_off
from tests.helpers.usage_stats_schema import declared_properties, load_usage_stats_schema


def _values(*, event: str, name: str) -> list[str]:
    return list(declared_properties(event_name=event)[name]["values"])


def _values_by(*, event: str, name: str, selector: str) -> list[str]:
    return list(declared_properties(event_name=event)[name]["values_by"]["values"][selector])


class TestUsageStatsContract:
    def test_destination_is_the_schemas(self) -> None:
        destination = load_usage_stats_schema()["destination"]
        assert destination["capture_host"] == CAPTURE_HOST
        assert destination["batch_path"] == BATCH_PATH
        assert destination["project_token"] == PROJECT_TOKEN
        assert load_usage_stats_schema()["schema_version"] == SCHEMA_VERSION
        assert load_usage_stats_schema()["person_profile_property"] == PERSON_PROFILE_PROPERTY

    def test_notice_is_the_schemas_text_for_pipelex(self) -> None:
        notice = load_usage_stats_schema()["notice"]
        assert notice["version"] == NOTICE_VERSION
        assert notice["details_url"] == NOTICE_DETAILS_URL
        assert notice["disable_commands"][TOOL_NAME] == NOTICE_DISABLE_COMMAND
        expected = str(notice["text"]).replace("{disable_command}", NOTICE_DISABLE_COMMAND).replace("{details_url}", NOTICE_DETAILS_URL)
        assert render_notice() == expected

    def test_environment_variables_are_the_schemas(self) -> None:
        environment = load_usage_stats_schema()["environment"]
        assert environment["do_not_track"] == UsageStatsEnvVar.DO_NOT_TRACK
        assert environment["tool_switch"] == UsageStatsEnvVar.TOOL_SWITCH
        assert environment["debug"] == UsageStatsEnvVar.DEBUG
        assert environment["endpoint_override"] == UsageStatsEnvVar.ENDPOINT_OVERRIDE
        assert environment["host"] == UsageStatsEnvVar.HOST

    def test_switch_values_are_the_schemas(self) -> None:
        switch_values = load_usage_stats_schema()["switch_values"]
        assert set(switch_values["falsy"]) == FALSY_VALUES
        assert set(switch_values["tool_switch_off"]) == TOOL_SWITCH_OFF_VALUES
        assert set(switch_values["tool_switch_no_effect"]) == TOOL_SWITCH_NO_EFFECT_VALUES
        assert set(switch_values["mthds_disable_on"]) == LEGACY_DISABLE_ON_VALUES

    def test_off_by_tokens_are_pipelexs_switches_in_order(self) -> None:
        switches: list[dict[str, Any]] = load_usage_stats_schema()["switches"]
        pipelex_tokens = [switch["token"] for switch in switches if TOOL_NAME in switch["tools"]]
        assert [token.value for token in UsageStatsOffBy] == pipelex_tokens

    def test_state_names_are_the_schemas(self) -> None:
        state = load_usage_stats_schema()["state"]
        assert str(Path("~", *STATE_DIR_PARTS)) == state["directory"]
        assert state["id"] == ID_FILE_NAME
        assert state["disabled"] == DISABLED_FILE_NAME
        assert state["legacy_migrated"] == LEGACY_MIGRATED_FILE_NAME
        assert state["notice_prefix"] == NOTICE_FILE_PREFIX
        assert state["internal"] == INTERNAL_FILE_NAME
        assert state["spool"] == SPOOL_DIR_NAME
        assert state["legacy_key"] == LEGACY_KEY

    def test_spool_limits_and_budgets_are_the_schemas(self) -> None:
        schema = load_usage_stats_schema()
        spool = schema["spool"]
        assert spool["max_files_per_tool"] == SPOOL_MAX_FILES_PER_TOOL
        assert spool["max_age_days"] == SPOOL_MAX_AGE_DAYS
        assert spool["stale_claim_minutes"] == SPOOL_STALE_CLAIM_MINUTES
        assert spool["stale_temp_minutes"] == SPOOL_STALE_TEMP_MINUTES
        budgets = schema["budgets_ms"]
        assert budgets["cli_in_process"] == BUDGET_CLI_IN_PROCESS_MS
        assert budgets["python_exit_flush"] == BUDGET_PYTHON_EXIT_FLUSH_MS
        assert budgets["shutdown_flush"] == BUDGET_SHUTDOWN_FLUSH_MS
        assert budgets["detached_sender"] == BUDGET_DETACHED_SENDER_MS
        assert budgets["background_post_delay"] == BUDGET_BACKGROUND_POST_DELAY_MS
        assert list(SPOOL_TOOLS) == declared_properties(event_name="run_completed")["tool"]["values"]

    def test_ci_and_container_markers_are_the_schemas(self) -> None:
        schema = load_usage_stats_schema()
        assert list(CI_VARIABLES) == schema["ci_variables"]
        markers = schema["container_markers"]
        assert list(CONTAINER_MARKER_FILES) == markers["files"]
        assert list(CONTAINER_MARKER_VARIABLES) == markers["environment"]
        assert list(CONTAINER_CGROUP_WORDS) == markers["cgroup_words"]

    def test_patterns_are_the_schemas(self) -> None:
        patterns = load_usage_stats_schema()["patterns"]
        assert patterns["release_version"]["regex"] == RELEASE_VERSION_PATTERN
        assert patterns["installation_id"]["regex"] == INSTALLATION_ID_PATTERN
        assert patterns["model_handle"]["regex"] == MODEL_HANDLE_PATTERN

    def test_enums_are_the_schemas_values(self) -> None:
        assert {event.value for event in UsageStatsEventName} <= set(load_usage_stats_schema()["events"])
        assert [surface.value for surface in UsageStatsSurface] == _values_by(event="run_completed", name="surface", selector=TOOL_NAME)
        assert [integration.value for integration in UsageStatsIntegration] == _values(event="run_completed", name="integration")
        assert [host.value for host in UsageStatsHost] == _values(event="run_completed", name="host")
        assert [os_family.value for os_family in UsageStatsOs] == _values(event="run_completed", name="os")
        assert [arch.value for arch in UsageStatsArch] == _values(event="run_completed", name="arch")
        assert [outcome.value for outcome in UsageStatsOutcome] == _values(event="run_completed", name="outcome")
        assert [domain.value for domain in UsageStatsErrorDomain] == _values(event="run_completed", name="error_domain")
        assert [source.value for source in UsageStatsMethodSource] == _values(event="run_completed", name="method_source")
        assert [outcome.value for outcome in UsageStatsValidationOutcome] == _values(event="method_validated", name="outcome")
        assert [outcome.value for outcome in UsageStatsCodegenOutcome] == _values(event="code_generated", name="outcome")
        assert [artifact.value for artifact in UsageStatsCodegenArtifact] == _values(event="code_generated", name="artifact")
        assert [target.value for target in UsageStatsCodegenTarget] == _values(event="code_generated", name="target")
        assert [provider.value for provider in UsageStatsProvider] == _values(event="model_used", name="provider")

    def test_command_lists_are_the_schemas(self) -> None:
        assert set(PIPELEX_COMMANDS) == set(_values_by(event="command_completed", name="command", selector=UsageStatsSurface.PIPELEX))
        assert set(PIPELEX_AGENT_COMMANDS) == set(_values_by(event="command_completed", name="command", selector=UsageStatsSurface.PIPELEX_AGENT))

    def test_manifold_is_reported_as_its_shipped_backend_name(self) -> None:
        assert UsageStatsProvider.PIPELEX_MANIFOLD == "pipelex_manifold"
        assert UsageStatsProvider.PIPELEX_MANIFOLD.serves_every_shipped_table
        assert not UsageStatsProvider.OPENAI.serves_every_shipped_table

    def test_packaged_configuration_ships_statistics_on(self) -> None:
        assert PACKAGED_CONFIG_PATH.is_file()
        assert not packaged_default_says_off()
