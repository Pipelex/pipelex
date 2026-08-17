"""When the backend loader's retry declines, the error still says *old* rather than only *wrong*.

The fourth surface reaches a user through two paths, and until this test only one of them knew it
was a surface. `InferenceBackendLibrary.load` replays the ledger in memory and boots with a warning
when that works — but when it does not, the refusal travels out of `ModelManager.setup` and
`RuntimeBoot` turns it into a message of its own instead of going through the shared
`raise_config_setup_error`. That message named no surface, so the scan never ran, and a machine whose
backend file was *both* stale and carrying something we cannot explain was told only about the second
half — while the very same staleness in `pipelex.toml` produced the migration block.

Four things under test, and the first one is the one a hand-built exception cannot check:

- **The boot catches the class the loader actually raises.** Every refusal below is produced by
  running the real `InferenceBackendLibrary.load` over a planted directory, and the first assertion
  on each is that `BACKEND_LIBRARY_REFUSED` covers it. A fixture that constructed the exception
  itself passed while the clause named a sibling class that is raised nowhere, and the whole feature
  was unreachable underneath it. The library index file is covered too: a bad value in
  `backends.toml` used to leave the loader as pydantic's own error, which no clause named.
- **The refusal's own account survives.** The loader says *which model, which backend, which file*
  before it quotes the pydantic analysis, and a directory holds a dozen files with the same field
  names — so a message reduced to `max_tokens: Input should be a valid integer` sends the reader to
  grep. Whatever the message builder adds, it adds *around* the loader's sentence.
- **A surface's failure carries its migration block.** The contract's rule is that every configuration
  surface's loader reports through the migration scan; this is the fourth surface honouring it. Both
  refusal shapes are covered, because only one of them carries a pydantic error: an unknown key in
  `[defaults]` is `extra_forbidden` on every model of the file, while an unknown key on one model
  table is rejected by name and arrives with no `__cause__` at all.
- **And then nothing offers to start over.** The tail that sends a user to `pipelex init config` — a
  command described in the same breath as resetting files to their defaults — must not be printed
  beside a block that just promised `pipelex migrate` keeps their values. The model deck, which has no
  ledger and gets no block, keeps that tail exactly as it was.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.runtime_boot import BACKEND_LIBRARY_REFUSED, BootComponent, RuntimeBoot
from pipelex.system.configuration.config_loader import BACKENDS_DIR_NAME, CONFIG_DIR_NAME, INFERENCE_DIR_NAME
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

RETIRED_KEY = "prompting_target"
"""What `#1104` removed, and what the ledger entry explains."""

UNEXPLAINED_KEY = "not_a_setting_we_ever_had"
"""What nothing explains, and what keeps the retry from succeeding. Carries no hyphen on purpose: a
header-shaped key would be a legal per-model key rather than a refusal."""

REGENERATE_TAIL = "pipelex init config"

MIGRATION_PROSE = "migrat"
"""The stem shared by every sentence the migration block adds — `migration history`, `pipelex migrate`,
`--dry-run` — and by nothing the loader says on its own."""

BACKENDS_TOML = """
[openai]
enabled = true
api_key = "sk-not-a-real-key"
"""

BACKENDS_TOML_WITH_A_BAD_VALUE = """
[openai]
enabled = true
api_key = "sk-not-a-real-key"
endpoint = 42
"""
"""The library index file refusing on a *known* field: `endpoint` is a string. This is not a
per-model file and belongs to no surface, so the message it earns is the plain one."""


class TestAStaleBackendFileTheLedgerCannotFullyExplain:
    @pytest.fixture
    def machine(self, tmp_path: Path, mocker: MockerFixture) -> Path:
        """A global configuration directory holding a fresh copy of the kit's backend files.

        The home is faked so that the scan walks this directory rather than the developer's own — it
        is `config_manager.existing_config_dirs` on both ends, the one derivation.
        """
        fake_home = tmp_path / "home"
        global_dir = fake_home / CONFIG_DIR_NAME
        inference_dir = global_dir / INFERENCE_DIR_NAME
        inference_dir.mkdir(parents=True)
        shutil.copytree(Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME, inference_dir / BACKENDS_DIR_NAME)
        (inference_dir / "backends.toml").write_text(BACKENDS_TOML, encoding="utf-8")

        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)

        return global_dir

    def _plant(self, *, path: Path, anchor: str, keys: str) -> None:
        text = path.read_text(encoding="utf-8")
        if anchor not in text:
            msg = f"'{path.name}' no longer has a {anchor.strip()} table to plant into — the fixture is testing nothing."
            raise AssertionError(msg)
        path.write_text(text.replace(anchor, f"{anchor}{keys}", 1), encoding="utf-8")

    def _refusal_from_the_real_loader(self, *, machine: Path) -> Exception:
        """Whatever `InferenceBackendLibrary.load` raises over this directory, unwrapped by nobody.

        The point of going through the loader rather than building the exception: the class it raises
        is exactly what the boot's `except` clause has to name, and that is the link that was broken.
        """
        library = InferenceBackendLibrary.make_empty()
        with pytest.raises(BACKEND_LIBRARY_REFUSED) as refused:
            library.load(
                secrets_provider=EnvSecretsProvider(),
                backends_library_path=str(machine / INFERENCE_DIR_NAME / "backends.toml"),
                backends_dir_path=str(machine / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME),
                gateway_config=None,
                lenient=False,
            )
        return refused.value

    @pytest.fixture
    def stale_and_unexplained_in_defaults(self, machine: Path) -> tuple[Path, Exception]:
        """`[defaults]` carries both keys: every model of the file fails with a pydantic error."""
        stale_file = machine / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME / "openai.toml"
        self._plant(path=stale_file, anchor="[defaults]\n", keys=f'{RETIRED_KEY} = "openai"\n{UNEXPLAINED_KEY} = 1\n')
        return stale_file, self._refusal_from_the_real_loader(machine=machine)

    @pytest.fixture
    def both_keys_on_one_model_table(self, machine: Path) -> tuple[Path, Exception]:
        """The shape with **no** pydantic error at all: keys rejected by name rather than by the model.

        Both on the *same* table, and both halves of that matter. On a model table rather than in
        `[defaults]`, so nothing is merged into another model and no `extra_forbidden` fires — the
        refusal is `split_model_spec_keys`' own, and it arrives with no `__cause__`. On one table
        rather than two, so the refusal names the key the user has to fix: split across two models,
        the first table to fail is the *stale* one, the retry then repairs it and the second table
        refuses, and what is re-raised is the first error — which names only the key a migration
        would have removed.
        """
        stale_file = machine / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME / "openai.toml"
        self._plant(path=stale_file, anchor="[gpt-4o]\n", keys=f'{RETIRED_KEY} = "openai"\n{UNEXPLAINED_KEY} = 1\n')
        return stale_file, self._refusal_from_the_real_loader(machine=machine)

    def test_the_refusal_the_loader_raises_is_one_the_boot_handles(self, stale_and_unexplained_in_defaults: tuple[Path, Exception]) -> None:
        """The link that was missing: `pytest.raises(BACKEND_LIBRARY_REFUSED)` above is the assertion.

        Kept as a test of its own rather than left implicit in the fixture, because it is the claim
        the other cases all rest on — reach the message builder with an exception the boot never
        catches and every assertion below is about code no user runs.
        """
        _, refusal = stale_and_unexplained_in_defaults

        assert isinstance(refusal, BACKEND_LIBRARY_REFUSED)

    @pytest.mark.parametrize(
        "fixture_name",
        ["stale_and_unexplained_in_defaults", "both_keys_on_one_model_table"],
    )
    def test_the_message_names_the_stale_file_and_the_migration_that_explains_it(self, request: pytest.FixtureRequest, fixture_name: str) -> None:
        """Both refusal shapes, because only one of them carries a pydantic error to translate."""
        stale_file, refusal = request.getfixturevalue(fixture_name)

        message = RuntimeBoot._get_validation_error_msg(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            component=BootComponent.INFERENCE_BACKEND_LIBRARY,
            validation_exc=refusal,
        )

        assert UNEXPLAINED_KEY in message, "the user's own key is still what the error is about"
        assert str(stale_file) in message
        assert "Drop prompting_target from every backend definition" in message
        assert "pipelex migrate" in message

    @pytest.mark.parametrize(
        "fixture_name",
        ["stale_and_unexplained_in_defaults", "both_keys_on_one_model_table"],
    )
    def test_it_stops_offering_to_start_over_once_it_has_offered_to_migrate(self, request: pytest.FixtureRequest, fixture_name: str) -> None:
        """Two remedies, one of which discards the file, is worse advice than either alone."""
        _, refusal = request.getfixturevalue(fixture_name)

        message = RuntimeBoot._get_validation_error_msg(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            component=BootComponent.INFERENCE_BACKEND_LIBRARY,
            validation_exc=refusal,
        )

        assert "pipelex migrate" in message, "the tail is dropped because a block was found, not because none was looked for"
        assert REGENERATE_TAIL not in message

    def test_a_component_with_no_ledger_is_unchanged(self, stale_and_unexplained_in_defaults: tuple[Path, Exception]) -> None:
        """The model deck shares this message and is not a surface: no scan, no block, same tail as before."""
        _, refusal = stale_and_unexplained_in_defaults

        message = RuntimeBoot._get_validation_error_msg(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            component=BootComponent.MODEL_DECK,
            validation_exc=refusal,
        )

        assert REGENERATE_TAIL in message
        assert MIGRATION_PROSE not in message

    def test_a_bad_value_on_a_known_field_keeps_the_plain_message_and_the_loaders_own_account(self, machine: Path) -> None:
        """No scan result, no block — naming the surface must not invent one. And nothing is lost on the way.

        A **wrong value on a field the schema still has** is the refusal that leaves the scan with
        nothing to report: every path of the file resolves, so the diagnosis finds none unexplained
        and no entry applies. An unknown *key* would not do here, and that is worth knowing rather
        than working around — it is an unexplained path, so it earns a block of its own with
        `would_write` false, pointing at `migrate --dry-run` instead of at a rewrite. This case is the
        one where the message must be exactly what it was before the surface existed.

        It is also the case that showed the loader's sentence being thrown away: this refusal carries
        a pydantic error, and a builder that translated *that* and dropped the rest reduced the whole
        message to `max_tokens: Input should be a valid integer` — no model, no backend, no file, in a
        directory of a dozen files that all have a `max_tokens`. The pydantic analysis stays, and the
        loader's *where* stays around it.
        """
        stale_file = machine / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME / "openai.toml"
        self._plant(path=stale_file, anchor="[gpt-4o]\n", keys='max_tokens = "lots"\n')
        refusal = self._refusal_from_the_real_loader(machine=machine)

        message = RuntimeBoot._get_validation_error_msg(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            component=BootComponent.INFERENCE_BACKEND_LIBRARY,
            validation_exc=refusal,
        )

        assert "max_tokens" in message
        assert "'gpt-4o'" in message, "the model whose table holds the bad value"
        assert "'openai'" in message, "the backend"
        assert str(stale_file) in message, "the file, which the pydantic analysis alone never names"
        assert MIGRATION_PROSE not in message
        assert REGENERATE_TAIL in message

    def test_a_bad_value_in_the_library_index_is_a_refusal_the_boot_handles(self, machine: Path) -> None:
        """`backends.toml` is the other file the loader reads, and it refused in a class nobody named.

        A wrong value on a backend's own table — `endpoint = 42` — failed `InferenceBackendBlueprint`
        and left `load` as pydantic's bare `ValidationError`, so it reached the user as a traceback
        naming neither the backend nor the file. `pytest.raises(BACKEND_LIBRARY_REFUSED)` in the
        helper is again the assertion that matters; the rest is that the message says where.
        """
        (machine / INFERENCE_DIR_NAME / "backends.toml").write_text(BACKENDS_TOML_WITH_A_BAD_VALUE, encoding="utf-8")
        refusal = self._refusal_from_the_real_loader(machine=machine)

        message = RuntimeBoot._get_validation_error_msg(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            component=BootComponent.INFERENCE_BACKEND_LIBRARY,
            validation_exc=refusal,
        )

        assert "endpoint" in message
        assert "'openai'" in message, "the backend whose table holds the bad value"
        assert str(machine / INFERENCE_DIR_NAME / "backends.toml") in message
        assert MIGRATION_PROSE not in message, "the index file belongs to no surface, and the per-model files are pristine"
        assert REGENERATE_TAIL in message

    def test_an_unexplained_key_alone_earns_a_block_that_points_at_the_dry_run(self, machine: Path) -> None:
        """The other side of the case above, and the second thing F2's fix buys.

        A file that is wrong without being old still has something the migration channel can say: the
        path nothing explains. The block is there, `would_write` is false, and the prose sends the
        reader to `migrate --dry-run` rather than promising a rewrite — so the start-over tail goes,
        because the reader has been given a diagnosis to read first.
        """
        stale_file = machine / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME / "openai.toml"
        self._plant(path=stale_file, anchor="[defaults]\n", keys=f"{UNEXPLAINED_KEY} = 1\n")
        refusal = self._refusal_from_the_real_loader(machine=machine)

        message = RuntimeBoot._get_validation_error_msg(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            component=BootComponent.INFERENCE_BACKEND_LIBRARY,
            validation_exc=refusal,
        )

        assert UNEXPLAINED_KEY in message
        assert str(stale_file) in message
        assert "pipelex migrate --dry-run" in message
        assert "Drop prompting_target" not in message, "no entry applies, so nothing may claim one carried anything forward"
