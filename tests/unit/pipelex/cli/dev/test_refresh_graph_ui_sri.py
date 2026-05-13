"""Unit tests for the `pipelex-dev refresh-graph-ui-sri` command."""

import base64
import hashlib
import io
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cli.dev_cli.commands.refresh_graph_ui_sri_cmd import refresh_graph_ui_sri_cmd
from pipelex.cli.exceptions import PipelexCLIError


class TestRefreshGraphUiSri:
    _MTHDS_UI_JS_BYTES = b"// fake graph-viewer.js bundle"
    _MTHDS_UI_CSS_BYTES = b"/* fake graph-viewer.css */"
    _ELKJS_BYTES = b"// fake elk.bundled.js"

    @staticmethod
    def _expected_sri(payload: bytes) -> str:
        return "sha384-" + base64.b64encode(hashlib.sha384(payload).digest()).decode("ascii")

    def _install_fake_urlopen(self, mocker: MockerFixture) -> None:
        payloads: dict[str, bytes] = {
            "https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@1.2.3/dist/standalone/graph-viewer.js": self._MTHDS_UI_JS_BYTES,
            "https://cdn.jsdelivr.net/npm/@pipelex/mthds-ui@1.2.3/dist/standalone/graph-viewer.css": self._MTHDS_UI_CSS_BYTES,
            "https://cdn.jsdelivr.net/npm/elkjs@9.9.9/lib/elk.bundled.js": self._ELKJS_BYTES,
        }

        def fake_urlopen(url: str, timeout: float = 30.0):  # noqa: ARG001
            return io.BytesIO(payloads[url])

        mocker.patch("pipelex.cli.dev_cli.commands.refresh_graph_ui_sri_cmd.urlopen", side_effect=fake_urlopen)

    def test_writes_new_versions_and_integrities(self, tmp_path: Path, mocker: MockerFixture) -> None:
        self._install_fake_urlopen(mocker)
        target = tmp_path / "standalone_assets.py"

        refresh_graph_ui_sri_cmd(
            mthds_ui_version="1.2.3",
            elkjs_version="9.9.9",
            output_path=target,
            quiet=True,
        )

        content = target.read_text(encoding="utf-8")

        assert 'MTHDS_UI_VERSION = "1.2.3"' in content
        assert 'ELKJS_VERSION = "9.9.9"' in content

        expected_js_sri = self._expected_sri(self._MTHDS_UI_JS_BYTES)
        expected_css_sri = self._expected_sri(self._MTHDS_UI_CSS_BYTES)
        expected_elk_sri = self._expected_sri(self._ELKJS_BYTES)

        assert f'integrity="{expected_js_sri}"' in content
        assert f'integrity="{expected_css_sri}"' in content
        assert f'integrity="{expected_elk_sri}"' in content

    def test_written_module_is_importable_and_matches_constants(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The regenerated module file must be valid Python and round-trip through import."""
        self._install_fake_urlopen(mocker)
        target = tmp_path / "regenerated_standalone_assets.py"

        refresh_graph_ui_sri_cmd(
            mthds_ui_version="1.2.3",
            elkjs_version="9.9.9",
            output_path=target,
            quiet=True,
        )

        namespace: dict[str, object] = {}
        exec(compile(target.read_text(encoding="utf-8"), str(target), "exec"), namespace)

        assert namespace["MTHDS_UI_VERSION"] == "1.2.3"
        assert namespace["ELKJS_VERSION"] == "9.9.9"

        mthds_ui_js = namespace["MTHDS_UI_JS"]
        mthds_ui_css = namespace["MTHDS_UI_CSS"]
        elkjs = namespace["ELKJS"]

        assert mthds_ui_js.integrity == self._expected_sri(self._MTHDS_UI_JS_BYTES)  # type: ignore[attr-defined]
        assert mthds_ui_css.integrity == self._expected_sri(self._MTHDS_UI_CSS_BYTES)  # type: ignore[attr-defined]
        assert elkjs.integrity == self._expected_sri(self._ELKJS_BYTES)  # type: ignore[attr-defined]

        assert "1.2.3" in mthds_ui_js.url  # type: ignore[attr-defined]
        assert "9.9.9" in elkjs.url  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "bad_version",
        [
            '1.0.0"; import os; os.system("rm -rf ~")  #',
            "1.0.0/../../../etc/passwd",
            "1.0.0\nimport os",
            "latest",
            "v1.0.0",
            "1.0",
            "1.0.0 ",
            "",
        ],
    )
    def test_rejects_malformed_versions(self, tmp_path: Path, mocker: MockerFixture, bad_version: str) -> None:
        """Strings that aren't strict SemVer must be rejected — guards against code injection into the regenerated module."""
        self._install_fake_urlopen(mocker)
        target = tmp_path / "standalone_assets.py"

        with pytest.raises(PipelexCLIError):
            refresh_graph_ui_sri_cmd(
                mthds_ui_version=bad_version,
                elkjs_version="9.9.9",
                output_path=target,
                quiet=True,
            )

        assert not target.exists(), "Output file must not be touched when validation fails"
