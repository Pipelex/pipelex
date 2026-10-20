"""The `postman-bundle` skill sends a method as `files`: every file of its tree, inline, and none of the retired fields.

`build_postman_query.py` is the skill's standalone script, not a package module, so it is loaded from its path. Each
body is built as the script's preview (`--dry-run`) prints it, never pushed to Postman nor sent over the network; the
runner's own routes then read the printed body in process, so a body the skill builds is one the runner accepts.
"""

import base64
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router

_MEMBER_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _MEMBER_ROOT / ".claude" / "skills" / "postman-bundle" / "scripts" / "build_postman_query.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_postman_query", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


postman_script = _load_script()

_GREET_MTHDS = """\
domain = "greeting"
main_pipe = "greet"

[pipe.greet]
type = "PipeCompose"
description = "Greet"
inputs = { text = "Text" }
output = "Text"
template = "Hello $text"
"""

# A sibling bundle of another domain declaring a pipe of the same bare code as the main bundle's `main_pipe`.
_OTHER_MTHDS = """\
domain = "other"

[pipe.greet]
type = "PipeCompose"
description = "Greet otherwise"
inputs = { text = "Text" }
output = "Text"
template = "Farewell $text"
"""

_CARD_HTML = "<p>Hello, {{ text }}</p>\n"
_ICON = b"\x89PNG\r\n\x1a\n not text"
_MANIFEST = """\
[package]
name = "greeting"
address = "github.com/acme/greeting"
version = "0.1.0"
description = "A package whose root is above the bundle's directory."
"""
_README = "# Greeting\n"
_INPUTS = {"text": "world"}
_INPUTS_TOML = 'text = "world"\n'
_EXAMPLE_INPUTS = '{"text": "an example for people to read"}\n'
_CALLBACK_URL = "https://example.com/hook"

# The tree of `bundle_dir`: its text inline, its binary file in Base64, and nothing the membership rule keeps out, a
# run's inputs file at any depth included, while example inputs under another name are an ordinary member.
_EXPECTED_FILES: dict[str, Any] = {
    "assets/icon.png": {"base64": base64.b64encode(_ICON).decode("ascii")},
    "bundle.mthds": _GREET_MTHDS,
    "examples/greeting-inputs.json": _EXAMPLE_INPUTS,
    "other.mthds": _OTHER_MTHDS,
    "templates/card.html": _CARD_HTML,
}

_REQUEST_BODY_MARKER = "--- request body ("


@pytest.fixture(name="bundle_dir")
def bundle_dir_fixture(tmp_path: Path) -> Path:
    """A method's directory: two bundles, a template, a binary file and the run's inputs, beside files the membership rule keeps out."""
    bundle_dir = tmp_path / "greeting"
    for subdirectory in ("templates", "assets", "examples", "drafts", "__pycache__"):
        (bundle_dir / subdirectory).mkdir(parents=True)
    (bundle_dir / "bundle.mthds").write_text(_GREET_MTHDS, encoding="utf-8")
    (bundle_dir / "other.mthds").write_text(_OTHER_MTHDS, encoding="utf-8")
    (bundle_dir / "inputs.json").write_text(json.dumps(_INPUTS), encoding="utf-8")
    (bundle_dir / "examples" / "inputs.toml").write_text(_INPUTS_TOML, encoding="utf-8")
    (bundle_dir / "examples" / "greeting-inputs.json").write_text(_EXAMPLE_INPUTS, encoding="utf-8")
    (bundle_dir / "templates" / "card.html").write_text(_CARD_HTML, encoding="utf-8")
    (bundle_dir / "assets" / "icon.png").write_bytes(_ICON)
    (bundle_dir / ".gitignore").write_text("drafts/\n", encoding="utf-8")
    (bundle_dir / "drafts" / "old.mthds").write_text(_GREET_MTHDS, encoding="utf-8")
    (bundle_dir / ".secret").write_text("kept out by its dot\n", encoding="utf-8")
    (bundle_dir / "__pycache__" / "cache.pyc").write_bytes(b"\x00")
    return bundle_dir


def _previewed_body_text(capsys: pytest.CaptureFixture[str], *args: str) -> str:
    """The JSON text of the one request body the script's preview prints for these arguments."""
    postman_script.main([*args, "--dry-run"])
    printed = capsys.readouterr().out
    assert printed.count(_REQUEST_BODY_MARKER) == 1, printed
    _, _, after_marker = printed.partition(_REQUEST_BODY_MARKER)
    _, _, body_text = after_marker.partition("\n")
    return body_text


def _build_client(mocker: MockerFixture) -> TestClient:
    mocker.patch(
        "pipelex_api.routes.pipelex.pipeline.get_api_config",
        return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False),
    )
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestPostmanBundleScript:
    def test_the_files_are_every_file_of_the_method_tree_inline(self, bundle_dir: Path) -> None:
        """Text travels as text, other bytes in Base64; a dotfile, a `.gitignore`d file, a cache or a run's inputs file never travels."""
        files = postman_script.build_files_map(postman_script.list_bundle_tree(bundle_dir))

        assert files == _EXPECTED_FILES

    def test_a_bundle_named_alone_sends_its_one_file_tree(self, bundle_dir: Path) -> None:
        files = postman_script.build_files_map(postman_script.list_bundle_tree(bundle_dir / "bundle.mthds"))

        assert files == {"bundle.mthds": _GREET_MTHDS}

    def test_a_manifest_above_the_bundle_roots_the_tree(self, tmp_path: Path) -> None:
        """The files are keyed by their paths from the tree's root, the directory of the nearest `METHODS.toml`."""
        package_root = tmp_path / "package"
        method_dir = package_root / "methods" / "greeting"
        method_dir.mkdir(parents=True)
        (package_root / "METHODS.toml").write_text(_MANIFEST, encoding="utf-8")
        (package_root / "README.md").write_text(_README, encoding="utf-8")
        (method_dir / "bundle.mthds").write_text(_GREET_MTHDS, encoding="utf-8")

        files = postman_script.build_files_map(postman_script.list_bundle_tree(method_dir))

        assert files == {"METHODS.toml": _MANIFEST, "README.md": _README, "methods/greeting/bundle.mthds": _GREET_MTHDS}

    @pytest.mark.parametrize(
        ("endpoint_args", "expected_fields"),
        [
            (["--endpoint", "execute"], {"pipe_code": "greeting.greet", "inputs": _INPUTS}),
            (
                ["--endpoint", "start", "--callback-url", _CALLBACK_URL],
                {"pipe_code": "greeting.greet", "inputs": _INPUTS, "callback_urls": [_CALLBACK_URL]},
            ),
            (["--endpoint", "validate", "--render", "markdown"], {"allow_signatures": False, "render": ["markdown"]}),
            (["--endpoint", "resolve"], {}),
            (["--endpoint", "codegen", "--target", "ts-zod"], {"kind": "types", "target": "ts-zod"}),
        ],
    )
    def test_every_body_carries_the_files_and_no_retired_field(
        self,
        capsys: pytest.CaptureFixture[str],
        bundle_dir: Path,
        endpoint_args: list[str],
        expected_fields: dict[str, Any],
    ) -> None:
        """No `mthds_contents`, `mthds_sources`, `bundle_b64` or `resources`, and the whole method last, after what a reader edits.

        The sibling `inputs.json` the script reads as the run's inputs, and the `inputs.toml` deeper in the tree, are in no
        endpoint's `files`, whether or not the `mthds` lister keeps them out itself.
        """
        body = json.loads(_previewed_body_text(capsys, str(bundle_dir), *endpoint_args))

        assert body == {**expected_fields, "files": _EXPECTED_FILES}
        assert "inputs.json" not in body["files"]
        assert "examples/inputs.toml" not in body["files"]
        assert list(body)[-1] == "files"

    @pytest.mark.parametrize(
        ("pipe_args", "expected_pipe_code"),
        [
            ([], "greeting.greet"),
            (["--pipe", "greet"], "greet"),
            (["--pipe", "other.greet"], "other.greet"),
        ],
    )
    def test_the_inferred_pipe_code_is_qualified_and_an_explicit_one_is_sent_as_given(
        self,
        capsys: pytest.CaptureFixture[str],
        bundle_dir: Path,
        pipe_args: list[str],
        expected_pipe_code: str,
    ) -> None:
        """The tree carries `other.greet` beside `greeting.greet`, so the main bundle's `main_pipe` travels qualified by its domain."""
        body = json.loads(_previewed_body_text(capsys, str(bundle_dir), "--endpoint", "execute", *pipe_args))

        assert body["pipe_code"] == expected_pipe_code

    def test_the_runner_runs_the_execute_body(self, capsys: pytest.CaptureFixture[str], mocker: MockerFixture, bundle_dir: Path) -> None:
        """The sibling `inputs.json` is found, and the runner runs the main bundle's pipe, not its sibling's namesake."""
        body_text = _previewed_body_text(capsys, str(bundle_dir), "--endpoint", "execute")
        assert json.loads(body_text)["inputs"] == _INPUTS

        response = _build_client(mocker).post("/v1/execute", content=body_text, headers={"Content-Type": "application/json"})

        assert response.status_code == 200, response.text
        run_result = response.json()
        assert run_result["state"] == "COMPLETED"
        assert "Hello world" in json.dumps(run_result["pipe_output"]["working_memory"])

    @pytest.mark.parametrize(
        ("endpoint_args", "route"),
        [
            (["--endpoint", "validate"], "/v1/validate"),
            (["--endpoint", "resolve"], "/v1/resolve"),
            (["--endpoint", "codegen", "--target", "python-pydantic"], "/v1/codegen"),
        ],
    )
    def test_the_runner_reads_the_free_bodies_as_a_valid_method(
        self,
        capsys: pytest.CaptureFixture[str],
        mocker: MockerFixture,
        bundle_dir: Path,
        endpoint_args: list[str],
        route: str,
    ) -> None:
        body_text = _previewed_body_text(capsys, str(bundle_dir), *endpoint_args)

        response = _build_client(mocker).post(route, content=body_text, headers={"Content-Type": "application/json"})

        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True, response.text

    def test_a_main_bundle_the_membership_rule_keeps_out_is_refused(self, capsys: pytest.CaptureFixture[str], bundle_dir: Path) -> None:
        """A pipe_code taken from a bundle the runner would never receive is never sent."""
        (bundle_dir / ".gitignore").write_text("drafts/\nbundle.mthds\n", encoding="utf-8")

        with pytest.raises(SystemExit) as exit_info:
            postman_script.main([str(bundle_dir), "--endpoint", "execute", "--dry-run"])

        assert exit_info.value.code == 1
        assert "the membership rule keeps" in capsys.readouterr().err
