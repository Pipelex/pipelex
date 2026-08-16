"""`report_validation_error` — the translation, and the migration that may explain it.

A configuration validation error says a key is wrong. It cannot say *why*, because it is raised
against the merged configuration and carries no provenance: it does not know which of the files
that were merged put the key there, nor whether the key was perfectly correct last week. The
answer to that second question is in the ledger, and this module is where the two meet.

Three properties are what the tests below exist to hold:

- **The scan runs only when a surface is named.** A `.mthds` bundle, a backend file and a model
  deck all reach this helper too, and none of them has a ledger — offering them a `pipelex migrate`
  remedy would send a user to a command with nothing to do.
- **The scan needs nothing but the filesystem.** It runs on a machine whose configuration just
  refused to load, which is a machine with no hub and no config. That is the same bootstrap
  property the `migrate` commands hold, and it is asserted here rather than assumed, because this
  helper used to read the hub and crash when there was not one.
- **Nothing that goes wrong inside the scan becomes the failure the user sees.** They have an
  error in front of them that names what to fix; ours must not replace it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, ValidationError

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexConfigError
from pipelex.core.validation import MIGRATE_COMMAND, raise_config_setup_error, report_validation_error
from pipelex.migration import run as migration_run_module
from pipelex.migration.exceptions import MigrationLedgerError
from pipelex.migration.goldens import pre_history_document_path
from pipelex.migration.ledger import packaged_migration_dir
from pipelex.runtime_hub import RuntimeHub
from pipelex.system.configuration.config_loader import CONFIG_REFUSED, pydantic_error_behind
from pipelex.system.configuration.config_surface import PIPELEX_CONFIG_SURFACE_ID, TELEMETRY_CONFIG_SURFACE_ID
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.system.exceptions import ConfigValidationError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

#: The shipped `telemetry-config@2` entry is about a real flat document the package carries, so a
#: stale machine can be built out of our own files rather than out of an invented schema change.
TELEMETRY_ENTRY_ID = "telemetry-config@2"


class _ConfigShape(BaseModel):
    required_field: str


def _make_validation_error() -> ValidationError:
    try:
        _ConfigShape.model_validate({})
    except ValidationError as exc:
        return exc
    pytest.fail("Expected _ConfigShape.model_validate to raise ValidationError")


def _old_shape_telemetry_document() -> str:
    path = pre_history_document_path(migration_dir=packaged_migration_dir(), surface_id=TELEMETRY_CONFIG_SURFACE_ID, schema_version=2)
    return path.read_text(encoding="utf-8")


@pytest.fixture
def machine(tmp_path: Path, mocker: MockerFixture) -> Path:
    """A global configuration directory this test owns, in place of the one on the machine."""
    fake_home = tmp_path / "home"
    global_dir = fake_home / ".pipelex"
    global_dir.mkdir(parents=True)
    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)
    mocker.patch.object(Path, "home", return_value=fake_home)
    mocker.patch.object(Path, "cwd", return_value=project_root)
    return global_dir


class TestTheScanRunsOnlyWhenASurfaceIsNamed:
    def test_no_surface_means_no_block(self, machine: Path) -> None:
        """The `.mthds` half of this helper's callers, and every other non-surface reader."""
        machine.joinpath("telemetry.toml").write_text(_old_shape_telemetry_document(), encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error())

        assert report.migration is None
        assert "required_field" in report.message
        assert MIGRATE_COMMAND not in report.message

    def test_no_surface_means_the_walk_never_happens(self, mocker: MockerFixture) -> None:
        """Not merely an empty answer — the filesystem is not walked at all.

        Without this, a `_pending_migration` that always ran and merely returned nothing useful
        for a `.mthds` error would pass the test above while costing every bundle-validation
        failure a directory walk and a ledger replay.
        """
        scan = mocker.patch.object(migration_run_module, "scan_config_surface")

        report_validation_error(validation_error=_make_validation_error())

        scan.assert_not_called()


class TestWhatTheScanFinds:
    def test_a_stale_file_becomes_a_block_naming_what_would_be_carried_forward(self, machine: Path) -> None:
        machine.joinpath("telemetry.toml").write_text(_old_shape_telemetry_document(), encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        assert report.migration is not None
        assert report.migration.remedy == MIGRATE_COMMAND
        assert not report.migration.needs_attention, "a file the ledger carries forward whole needs nobody"
        assert [step.entry_id for plan in report.migration.plans for step in plan.steps] == [TELEMETRY_ENTRY_ID]

    def test_the_message_keeps_the_translation_and_gains_the_remedy(self, machine: Path) -> None:
        """Both halves, in one string: the analysis is what names the actual error."""
        machine.joinpath("telemetry.toml").write_text(_old_shape_telemetry_document(), encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        assert "required_field" in report.message
        assert "telemetry.toml" in report.message
        assert MIGRATE_COMMAND in report.message

    def test_a_path_no_entry_explains_needs_a_person(self, machine: Path) -> None:
        """The downgrade diagnosis reaching the error surface — a typo, or a newer pipelex.

        `pipelex-config` ships an entry-free ledger, so nothing here is carried forward and the
        whole finding is the unknown key. That is the shape a stale-looking machine most often
        has, and it is the one where the remedy is *not* the command.
        """
        machine.joinpath("pipelex.toml").write_text("not_a_real_setting = true\n", encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=PIPELEX_CONFIG_SURFACE_ID)

        assert report.migration is not None
        assert report.migration.needs_attention
        assert [found.path for plan in report.migration.plans for found in plan.unexplained] == ["not_a_real_setting"]
        assert "not_a_real_setting" in report.message

    def test_a_current_machine_gets_no_block_at_all(self, machine: Path) -> None:
        """Presence is the contract, so a healthy machine must produce absence."""
        machine.joinpath("telemetry.toml").write_text('[custom_posthog]\nmode = "off"\n', encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        assert report.migration is None
        assert MIGRATE_COMMAND not in report.message

    def test_only_the_surface_that_refused_is_scanned(self, machine: Path) -> None:
        """A stale `telemetry.toml` is not an answer to a `pipelex.toml` that would not load."""
        machine.joinpath("telemetry.toml").write_text(_old_shape_telemetry_document(), encoding="utf-8")
        machine.joinpath("pipelex.toml").write_text("[pipelex]\n", encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=PIPELEX_CONFIG_SURFACE_ID)

        assert report.migration is None

    def test_another_surfaces_base_file_is_not_swept_up_by_this_ones_glob(self, machine: Path) -> None:
        """Scoping narrows the answer; it must not narrow the registry that decides ownership.

        `pipelex_service.toml` is `pipelex-service-config`'s base file *and* a match for
        `pipelex-config`'s tier glob `pipelex_*.toml`, and the registry resolves that by letting an
        exact base file claim before any glob — **across all surfaces**. Scoping the scan by
        building a registry that holds only the surface asked about removes the other claimant from
        that arbitration, and the glob then wins: the file is replayed under the wrong ledger and
        diagnosed against the wrong model, so its perfectly ordinary settings come back reported as
        paths this build knows nothing about. Measured, not imagined — that is what it did.
        """
        machine.joinpath("pipelex.toml").write_text("not_a_real_setting = true\n", encoding="utf-8")
        machine.joinpath("pipelex_service.toml").write_text("[agreement]\nterms_accepted = true\n", encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=PIPELEX_CONFIG_SURFACE_ID)

        assert report.migration is not None
        assert [plan.file_path.name for plan in report.migration.plans] == ["pipelex.toml"]


class TestTheScanIsScopedToTheDirectoriesThatWereLoaded:
    """A caller that loaded one directory must be diagnosed against that directory.

    `doctor --global` and an embedder's `config_dir=` bypass the global/project layering and read
    one directory. Answering their refusal with a scan of the default walk would name a file the
    reader never loaded — and stay silent about the one they did.
    """

    def test_a_stale_file_in_a_directory_that_was_not_loaded_is_not_the_answer(self, machine: Path, tmp_path: Path) -> None:
        project_dir = tmp_path / "project" / ".pipelex"
        project_dir.mkdir()
        project_dir.joinpath("pipelex.toml").write_text("not_a_real_setting = true\n", encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=PIPELEX_CONFIG_SURFACE_ID, config_dirs=[machine])

        assert report.migration is None

    def test_a_directory_outside_the_walk_is_diagnosed_when_it_is_the_one_loaded(self, machine: Path, tmp_path: Path) -> None:
        machine.joinpath("pipelex.toml").write_text("another_unknown_setting = true\n", encoding="utf-8")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        elsewhere.joinpath("pipelex.toml").write_text("not_a_real_setting = true\n", encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=PIPELEX_CONFIG_SURFACE_ID, config_dirs=[elsewhere])

        assert report.migration is not None
        assert [plan.file_path for plan in report.migration.plans] == [elsewhere / "pipelex.toml"]

    def test_the_raised_error_is_scoped_the_same_way(self, machine: Path, tmp_path: Path) -> None:
        project_dir = tmp_path / "project" / ".pipelex"
        project_dir.mkdir()
        project_dir.joinpath("pipelex.toml").write_text("not_a_real_setting = true\n", encoding="utf-8")

        with pytest.raises(PipelexConfigError) as caught:
            raise_config_setup_error(config_error=_make_validation_error(), surface_id=PIPELEX_CONFIG_SURFACE_ID, config_dirs=[machine])

        assert caught.value.migration is None


class TestTheScanNeedsNothingButTheFilesystem:
    def test_it_runs_with_no_hub_installed(self, machine: Path, mocker: MockerFixture) -> None:
        """The bootstrap property, on the one path that reaches it.

        This helper is called from inside `RuntimeBoot.__init__` and from the doctor's own
        bootstrap, both before any configuration exists — and it used to read the hub, which is
        how it once crashed with `LogConfig is not set` on exactly this path.
        """
        mocker.patch.object(RuntimeHub, "_instance", None)
        machine.joinpath("telemetry.toml").write_text(_old_shape_telemetry_document(), encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        assert report.migration is not None
        assert "required_field" in report.message


class TestAFailureInsideTheScanIsNotTheFailureTheUserSees:
    def test_a_ledger_that_will_not_load_leaves_the_translation_standing(self, mocker: MockerFixture) -> None:
        """A packaging bug of ours must not cost the user the message that names their own error.

        It stays loud where it should be: `make check-ledger`, and `pipelex migrate` itself.
        """
        mocker.patch.object(migration_run_module, "scan_config_surface", side_effect=MigrationLedgerError("the ledger is not there"))

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=PIPELEX_CONFIG_SURFACE_ID)

        assert report.migration is None
        assert "required_field" in report.message
        assert "the ledger is not there" not in report.message

    def test_an_applier_bug_still_surfaces(self, mocker: MockerFixture) -> None:
        """The catch is narrow on purpose: only what a field machine can legitimately produce.

        A bug in our own code is not that, and swallowing it here would hide it behind every
        configuration error anyone ever hits.
        """
        mocker.patch.object(migration_run_module, "scan_config_surface", side_effect=RuntimeError("an applier bug"))

        with pytest.raises(RuntimeError, match="an applier bug"):
            report_validation_error(validation_error=_make_validation_error(), surface_id=PIPELEX_CONFIG_SURFACE_ID)


class TestTheErrorCarriesBothTheDomainAndTheBlock:
    """The charter's own pair: `error_domain` stays `config`, and the block rides beside it."""

    def test_the_raised_error_reports_the_config_domain_and_the_migration(self, machine: Path) -> None:
        machine.joinpath("telemetry.toml").write_text(_old_shape_telemetry_document(), encoding="utf-8")
        refusal = ConfigValidationError("the configuration was refused")
        refusal.__cause__ = _make_validation_error()

        with pytest.raises(PipelexConfigError) as raised:
            raise_config_setup_error(config_error=refusal, surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        error_report = raised.value.to_error_report()
        assert error_report.error_domain == ErrorDomain.CONFIG, "a new domain would route the agent hooks to BLOCK"
        assert error_report.migration is not None
        assert error_report.migration.remedy == MIGRATE_COMMAND

    @pytest.mark.usefixtures("machine")
    def test_the_report_the_error_produces_is_json_serializable(self, machine: Path) -> None:
        """`ErrorReport.to_dict()` is a serialization surface, and the block carries real `Path`s.

        The webhook delivery path hands that dict straight to `json.dumps`, which cannot serialize
        a `PosixPath`. Not reachable from a pipeline run today — nothing raises this error inside
        one — but `to_dict` is documented as *the* serialization surface, so a field that quietly
        makes it unserializable is a trap left for whoever wires the next consumer.
        """
        machine.joinpath("telemetry.toml").write_text(_old_shape_telemetry_document(), encoding="utf-8")
        refusal = ConfigValidationError("the configuration was refused")
        refusal.__cause__ = _make_validation_error()

        with pytest.raises(PipelexConfigError) as raised:
            raise_config_setup_error(config_error=refusal, surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        payload = raised.value.to_error_report().to_dict()
        assert json.dumps(payload), "the block must survive a plain json.dumps"
        assert ErrorReport.from_dict(payload).migration is not None, "and it must come back through the round-trip"

    @pytest.mark.usefixtures("machine")
    def test_a_healthy_machine_raises_the_same_error_without_a_block(self) -> None:
        """Absence is what a consumer branches on, so it has to be reachable."""
        refusal = ConfigValidationError("the configuration was refused")
        refusal.__cause__ = _make_validation_error()

        with pytest.raises(PipelexConfigError) as raised:
            raise_config_setup_error(config_error=refusal, surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        assert raised.value.to_error_report().migration is None

    def test_a_refusal_carrying_no_pydantic_error_is_re_raised_as_itself(self) -> None:
        """There is nothing to translate, and its own message is already the whole account."""
        refusal = ConfigValidationError("the configuration directory is not readable")

        with pytest.raises(ConfigValidationError, match="not readable"):
            raise_config_setup_error(config_error=refusal, surface_id=PIPELEX_CONFIG_SURFACE_ID)


class TestTheRefusalTheMainConfigurationActuallyRaises:
    """The fact that made the boot's own `except` arm dead code for as long as it existed."""

    def test_it_is_not_pydantics_own_error(self) -> None:
        with pytest.raises(CONFIG_REFUSED) as raised:
            PipelexConfig.model_validate({"not_a_real_setting": True})

        assert not isinstance(raised.value, ValidationError), (
            "`ConfigRoot.__init__` translates pydantic's error, so an `except ValidationError` around "
            "`setup_config` never fires — which is exactly what it used to do"
        )
        assert pydantic_error_behind(config_error=raised.value) is not None


class TestNoValueFromAUsersFileIsEverRendered:
    """The contract's mechanical rule, on the third of its three channels.

    The `migrate` commands' output and their structured plan are covered end to end; this is the
    `migration` block on a configuration validation error. The planted value is carried by a
    `move_key` the shipped entry performs, so the scan demonstrably *handled* it — a rule that
    held only because the value was quietly dropped would be no rule at all.
    """

    PLANTED_SECRET = "phc_L1VE_s3cret_project_key_that_must_never_be_rendered"

    def test_neither_the_message_nor_the_block_carries_a_planted_secret(self, machine: Path) -> None:
        document = _old_shape_telemetry_document().replace("phc_example_project_api_key", self.PLANTED_SECRET)
        assert self.PLANTED_SECRET in document, "the golden no longer carries the api key this test substitutes into"
        machine.joinpath("telemetry.toml").write_text(document, encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        assert report.migration is not None
        assert [step.entry_id for plan in report.migration.plans for step in plan.steps] == [TELEMETRY_ENTRY_ID], (
            "the entry that moves the planted key has to have fired, or this proves nothing"
        )
        assert self.PLANTED_SECRET not in report.message
        assert self.PLANTED_SECRET not in json.dumps(report.migration.model_dump(mode="json"))


class TestARemedyIsNamedOnlyWhereItWouldWrite:
    """`would_write` — the field that separates *there is something to say* from *this repairs it*.

    A block's presence means the migration engine had something to report about these files. It
    does not mean the remedy would rewrite them: a file whose only finding is a path no entry
    explains, or an entry blocked before any of its operations landed, produces a block with
    nothing to apply. Naming the command there sends a reader to a run that writes nothing and
    leaves the error exactly where it was — which is the failure this field exists to prevent.
    """

    def test_a_file_the_ledger_carries_forward_would_be_written(self, machine: Path) -> None:
        machine.joinpath("telemetry.toml").write_text(_old_shape_telemetry_document(), encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        assert report.migration is not None
        assert report.migration.would_write is True
        assert f"Run `{MIGRATE_COMMAND}` to bring these files up to date." in report.message

    def test_a_file_with_nothing_to_apply_is_sent_to_the_dry_run_instead(self, machine: Path) -> None:
        """The specimen the old wording got wrong: `pipelex-config` ships an entry-free ledger, so an
        unknown root key is the whole finding and there is not one operation behind it.
        """
        machine.joinpath("pipelex.toml").write_text("not_a_real_setting = true\n", encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=PIPELEX_CONFIG_SURFACE_ID)

        assert report.migration is not None
        assert report.migration.would_write is False
        assert f"Run `{MIGRATE_COMMAND}` to bring these files up to date." not in report.message
        assert f"{MIGRATE_COMMAND} --dry-run" in report.message
        assert "by hand" in report.message

    def test_a_block_that_would_write_nothing_and_needs_nobody_is_unreachable(self, machine: Path) -> None:
        """The invariant that lets a reader treat the two flags as an exhaustive pair.

        A plan is in the block only when it is not clean, and a plan that is not clean carries at
        least one of a step, an applied operation under a blocked entry, a blocked entry, a path no
        entry explains, or a file that could not be read — the first two make `would_write` true and
        the rest make `needs_attention` true. Both specimens are checked, since between them they
        cover both sides of the pair.
        """
        machine.joinpath("telemetry.toml").write_text(f"{_old_shape_telemetry_document()}\nnot_a_real_setting = true\n", encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        assert report.migration is not None
        assert report.migration.would_write, "the flat body is carried forward"
        assert report.migration.needs_attention, "and the unknown key beside it is nobody's but a person's"

    def test_a_file_that_is_both_old_and_wrong_is_not_promised_a_full_repair(self, machine: Path) -> None:
        """The mixed case: the command would write, and something would still be there afterwards.

        `would_write` picks the opening and closing sentences, and this specimen is on its true side —
        but the closing sentence used to promise that the run brings the files up to date, over a
        file whose unknown key it will not touch. The paragraph has just listed what the command
        cannot do; its last sentence must not take that back.
        """
        machine.joinpath("telemetry.toml").write_text(f"{_old_shape_telemetry_document()}\nnot_a_real_setting = true\n", encoding="utf-8")

        report = report_validation_error(validation_error=_make_validation_error(), surface_id=TELEMETRY_CONFIG_SURFACE_ID)

        assert report.migration is not None
        assert report.migration.would_write is True
        assert "'not_a_real_setting', which this build knows nothing about" in report.message
        assert f"Run `{MIGRATE_COMMAND}` to bring these files up to date." not in report.message
        assert f"Run `{MIGRATE_COMMAND}` to carry forward what it can" in report.message
        assert "yours to fix" in report.message
