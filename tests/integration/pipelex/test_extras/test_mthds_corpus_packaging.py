"""The corpus ships in the wheel — asserted against a wheel that is actually built.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "Distribution".

Wheel consumers reach the corpus through ``importlib.resources``, so a corpus that stopped being
packaged would be invisible in this repo and would break every consumer at once, on the release.
Precedent said hatchling would carry the data files — ``pipelex.toml`` and ``kit/**/*.toml``
already ship — but precedent is not a gate, so this builds the real wheel and looks inside it.

The expected set is derived from the corpus tree rather than listed here: a new entry, a new file
kind, or a new namespace is covered the moment it lands, with nothing to remember.

Marked ``codex_disabled``: building a wheel resolves the PEP 517 backend through uv's default
index, which the air-gapped Codex sandbox cannot reach. The alternatives both cost more than the
marker — ``--offline`` would make the gate depend on a warm uv cache in every environment that
*does* run it, and skipping on a build failure would turn the one packaging gate we have into a
silent pass. It runs in GitHub Actions, which is where a packaging regression has to be caught.
"""

import shutil
import subprocess  # noqa: S404 — builds the real wheel; inspecting a hand-rolled file list would prove nothing
import zipfile
from pathlib import Path

import pytest

import pipelex
from pipelex.test_extras.mthds_corpus.resources import corpus_root

_REPO_ROOT = Path(pipelex.__file__).resolve().parent.parent
_UNSHIPPED_GENERATOR = "pipelex/cli/dev_cli/commands/generate_corpus_vocabulary_cmd.py"


@pytest.mark.codex_disabled
class TestMthdsCorpusPackaging:
    def test_the_corpus_ships_and_its_generator_does_not(self, tmp_path: Path) -> None:
        """Both halves of the split, against one built wheel: the generated data ships, the generator stays out."""
        uv_path = shutil.which("uv")
        # Not a skip: uv is how this repo is installed, so its absence is a broken environment, and a
        # packaging gate that quietly passes when it could not build anything is worse than no gate.
        assert uv_path is not None, "uv is not on PATH, so the wheel cannot be built and the packaging gate cannot run"

        build = subprocess.run(  # noqa: S603
            [uv_path, "build", "--wheel", "--out-dir", str(tmp_path)],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        assert build.returncode == 0, f"uv build failed.\nstdout={build.stdout!r}\nstderr={build.stderr!r}"
        wheels = list(tmp_path.glob("*.whl"))
        assert len(wheels) == 1, f"expected exactly one built wheel, got {[wheel.name for wheel in wheels]}"

        with zipfile.ZipFile(wheels[0]) as wheel:
            packaged = set(wheel.namelist())

        expected: set[str] = set()
        # Resolved on both sides of the relative_to: on a checkout reached through a symlink the two
        # would disagree and this test would die on a path error instead of reporting its verdict.
        for corpus_file in sorted(corpus_root().resolve().rglob("*")):
            if corpus_file.is_file() and "__pycache__" not in corpus_file.parts:
                expected.add(corpus_file.relative_to(_REPO_ROOT).as_posix())
        assert expected, "the corpus tree is empty on disk, so this test would otherwise pass vacuously"

        missing = sorted(expected - packaged)
        assert not missing, f"corpus files absent from the built wheel: {', '.join(missing)}"

        assert (_REPO_ROOT / _UNSHIPPED_GENERATOR).is_file(), "the generator moved; this test is pinning a path that no longer exists"
        assert _UNSHIPPED_GENERATOR not in packaged, "the vocabulary generator must stay unshipped dev tooling"
