"""Unit tests for stdin_resolver: resolve_stdin_inputs() and parse_cli_inputs()."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.run.stdin_resolver import parse_cli_inputs, resolve_stdin_inputs

if TYPE_CHECKING:
    from pathlib import Path


class TestStdinResolver:
    """Tests for resolve_stdin_inputs() and parse_cli_inputs()."""

    # -------------------------------------------------------------------------
    # resolve_stdin_inputs() tests
    # -------------------------------------------------------------------------

    def test_flat_inputs_passthrough(self) -> None:
        """Flat dict without working_memory is returned as-is."""
        data: dict[str, Any] = {"text": "hello", "count": 3}
        result = resolve_stdin_inputs(data)
        assert result == {"text": "hello", "count": 3}

    def test_envelope_detection_single_stuff(self) -> None:
        """Envelope with a single named stuff extracts {concept, content} entry."""
        data: dict[str, Any] = {
            "working_memory": {
                "root": {
                    "contract_text": {
                        "concept": "Text",
                        "content": {"body": "Lorem ipsum"},
                    },
                },
                "aliases": {},
            },
        }
        result = resolve_stdin_inputs(data)
        assert result == {
            "contract_text": {
                "concept": "Text",
                "content": {"body": "Lorem ipsum"},
            },
        }

    def test_envelope_detection_multiple_stuffs(self) -> None:
        """Envelope with multiple named stuffs extracts all of them."""
        data: dict[str, Any] = {
            "working_memory": {
                "root": {
                    "contract_text": {
                        "concept": "Text",
                        "content": {"body": "Lorem ipsum"},
                    },
                    "extracted_terms": {
                        "concept": "TermList",
                        "content": {"terms": ["a", "b"]},
                    },
                },
                "aliases": {},
            },
        }
        result = resolve_stdin_inputs(data)
        assert "contract_text" in result
        assert "extracted_terms" in result
        assert result["contract_text"]["concept"] == "Text"
        assert result["extracted_terms"]["concept"] == "TermList"

    def test_alias_skip(self) -> None:
        """main_stuff alias entry is skipped, real named stuffs are preserved."""
        data: dict[str, Any] = {
            "working_memory": {
                "root": {
                    "main_stuff": {
                        "concept": "Text",
                        "content": {"body": "alias target"},
                    },
                    "extracted_terms": {
                        "concept": "TermList",
                        "content": {"terms": ["x"]},
                    },
                },
                "aliases": {"main_stuff": "extracted_terms"},
            },
        }
        result = resolve_stdin_inputs(data)
        assert "main_stuff" not in result
        assert "extracted_terms" in result

    def test_real_main_stuff_included(self) -> None:
        """main_stuff is included when it is NOT in aliases (a real entry)."""
        data: dict[str, Any] = {
            "working_memory": {
                "root": {
                    "main_stuff": {
                        "concept": "Text",
                        "content": {"body": "real main stuff"},
                    },
                },
                "aliases": {},
            },
        }
        result = resolve_stdin_inputs(data)
        assert "main_stuff" in result
        assert result["main_stuff"]["concept"] == "Text"

    def test_malformed_envelope_working_memory_not_dict(self) -> None:
        """Non-dict working_memory triggers agent_error (typer.Exit)."""
        data: dict[str, Any] = {"working_memory": "bad"}
        with pytest.raises(typer.Exit) as exc_info:
            resolve_stdin_inputs(data)
        assert exc_info.value.exit_code == 1

    def test_empty_root(self) -> None:
        """Empty root returns empty dict."""
        data: dict[str, Any] = {
            "working_memory": {
                "root": {},
            },
        }
        result = resolve_stdin_inputs(data)
        assert result == {}

    def test_non_dict_root(self) -> None:
        """Non-dict root triggers agent_error (typer.Exit)."""
        data: dict[str, Any] = {
            "working_memory": {
                "root": "bad",
            },
        }
        with pytest.raises(typer.Exit) as exc_info:
            resolve_stdin_inputs(data)
        assert exc_info.value.exit_code == 1

    def test_concept_as_string(self) -> None:
        """Concept given as a plain string is extracted directly."""
        data: dict[str, Any] = {
            "working_memory": {
                "root": {
                    "item": {
                        "concept": "Text",
                        "content": {"value": 1},
                    },
                },
                "aliases": {},
            },
        }
        result = resolve_stdin_inputs(data)
        assert result["item"]["concept"] == "Text"

    def test_concept_as_dict(self) -> None:
        """Concept given as a dict with 'code' key extracts the code value."""
        data: dict[str, Any] = {
            "working_memory": {
                "root": {
                    "item": {
                        "concept": {"code": "Text", "module": "core"},
                        "content": {"value": 1},
                    },
                },
                "aliases": {},
            },
        }
        result = resolve_stdin_inputs(data)
        assert result["item"]["concept"] == "Text"

    def test_stuff_missing_concept_skipped(self) -> None:
        """Stuff entries missing concept or content are silently skipped."""
        data: dict[str, Any] = {
            "working_memory": {
                "root": {
                    "good": {
                        "concept": "Text",
                        "content": {"body": "ok"},
                    },
                    "bad_no_concept": {
                        "content": {"body": "missing concept"},
                    },
                    "bad_no_content": {
                        "concept": "Text",
                    },
                },
                "aliases": {},
            },
        }
        result = resolve_stdin_inputs(data)
        assert "good" in result
        assert "bad_no_concept" not in result
        assert "bad_no_content" not in result

    # -------------------------------------------------------------------------
    # parse_cli_inputs() tests
    # -------------------------------------------------------------------------

    def test_inputs_inline_json(self) -> None:
        """--inputs with inline JSON string is parsed correctly."""
        result = parse_cli_inputs(inputs_arg='{"text": "hello"}')
        assert result == {"text": "hello"}

    def test_inputs_file_path(self, tmp_path: Any) -> None:
        """--inputs with a file path loads JSON from the file."""
        json_file = tmp_path / "inputs.json"
        json_file.write_text('{"key": "value"}')
        result = parse_cli_inputs(inputs_arg=str(json_file))
        assert result == {"key": "value"}

    def test_inputs_tilde_path_is_expanded(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """A quoted / `=`-form `~/inputs.json` (tilde not shell-expanded) resolves to the home dir.

        The loader expands `~` itself so `--inputs "~/inputs.json"` opens the real file instead of
        failing with a not-found error on a literal `~` path — matching the `run method` path.
        """
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "inputs.json").write_text('{"tilde": "expanded"}')
        result = parse_cli_inputs(inputs_arg="~/inputs.json", stdin_fallback=False)
        assert result == {"tilde": "expanded"}

    def test_inputs_wins_over_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When --inputs is provided, stdin is ignored."""
        monkeypatch.setattr("sys.stdin", io.StringIO('{"from_stdin": true}'))
        result = parse_cli_inputs(inputs_arg='{"from_arg": true}')
        assert result == {"from_arg": True}

    def test_stdin_fallback_not_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When inputs_arg is None and stdin is not a TTY, reads from stdin."""
        stdin_data = json.dumps({"text": "from stdin"})
        mock_stdin = io.StringIO(stdin_data)
        mock_stdin.isatty = lambda: False  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)
        result = parse_cli_inputs(inputs_arg=None)
        assert result == {"text": "from stdin"}

    def test_stdin_tty_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When stdin is a TTY, returns None (no read attempted)."""
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)
        result = parse_cli_inputs(inputs_arg=None)
        assert result is None

    def test_stdin_fallback_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When stdin_fallback=False, returns None even if stdin has data."""
        mock_stdin = io.StringIO('{"text": "data"}')
        mock_stdin.isatty = lambda: False  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)
        result = parse_cli_inputs(inputs_arg=None, stdin_fallback=False)
        assert result is None

    def test_stdin_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty stdin returns None."""
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: False  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)
        result = parse_cli_inputs(inputs_arg=None)
        assert result is None

    def test_stdin_invalid_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid JSON on stdin triggers agent_error (typer.Exit)."""
        mock_stdin = io.StringIO("not valid json {{{")
        mock_stdin.isatty = lambda: False  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)
        with pytest.raises(typer.Exit) as exc_info:
            parse_cli_inputs(inputs_arg=None)
        assert exc_info.value.exit_code == 1

    def test_stdin_envelope_resolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stdin with working_memory envelope is resolved through resolve_stdin_inputs."""
        envelope = {
            "working_memory": {
                "root": {
                    "contract_text": {
                        "concept": "Text",
                        "content": {"body": "piped data"},
                    },
                },
                "aliases": {},
            },
        }
        mock_stdin = io.StringIO(json.dumps(envelope))
        mock_stdin.isatty = lambda: False  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)
        result = parse_cli_inputs(inputs_arg=None)
        assert result is not None
        assert "contract_text" in result
        assert result["contract_text"]["concept"] == "Text"

    def test_inputs_inline_invalid_json(self) -> None:
        """Invalid inline JSON in --inputs triggers agent_error."""
        with pytest.raises(typer.Exit) as exc_info:
            parse_cli_inputs(inputs_arg="{bad json")
        assert exc_info.value.exit_code == 1

    def test_inputs_file_not_found(self) -> None:
        """Non-existent file path in --inputs triggers agent_error."""
        with pytest.raises(typer.Exit) as exc_info:
            parse_cli_inputs(inputs_arg="/nonexistent/path/to/file.json")
        assert exc_info.value.exit_code == 1

    # -------------------------------------------------------------------------
    # TOML inputs file tests (.toml suffix routes through the TOML parser)
    # -------------------------------------------------------------------------

    def test_inputs_toml_file_path(self, tmp_path: Path) -> None:
        """--inputs with a .toml file path loads TOML, multi-line strings preserved."""
        toml_file = tmp_path / "inputs.toml"
        toml_file.write_text('[contract_text]\nconcept = "Text"\ncontent = """\nFirst line.\nSecond line.\n"""\n', encoding="utf-8")

        result = parse_cli_inputs(inputs_arg=str(toml_file))

        assert result == {"contract_text": {"concept": "Text", "content": "First line.\nSecond line.\n"}}

    def test_inputs_toml_syntax_error_envelope(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Invalid TOML in a .toml inputs file emits a TomlError envelope with input domain."""
        set_agent_cli_error_format(CliOutputFormat.JSON)
        toml_file = tmp_path / "inputs.toml"
        toml_file.write_text("topic = \n", encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            parse_cli_inputs(inputs_arg=str(toml_file))

        assert exc_info.value.exit_code == 1
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "TomlError"
        assert envelope["error_domain"] == "input"
        assert "hint" in envelope

    def test_inputs_toml_time_only_error_envelope(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A bare TOML time-of-day input emits the time-only-not-supported envelope with the include-a-date hint."""
        set_agent_cli_error_format(CliOutputFormat.JSON)
        toml_file = tmp_path / "inputs.toml"
        toml_file.write_text("opening = 09:00:00\n", encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            parse_cli_inputs(inputs_arg=str(toml_file))

        assert exc_info.value.exit_code == 1
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "InputsTimeOnlyNotSupportedError"
        assert envelope["error_domain"] == "input"
        assert "opening" in envelope["message"]
        assert "no date to attach to" in envelope["hint"]

    def test_inputs_json_syntax_error_envelope(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Invalid JSON in a .json inputs file emits a JSONDecodeError envelope (not a raw traceback)."""
        set_agent_cli_error_format(CliOutputFormat.JSON)
        json_file = tmp_path / "inputs.json"
        json_file.write_text("{not valid json", encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            parse_cli_inputs(inputs_arg=str(json_file))

        assert exc_info.value.exit_code == 1
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "JSONDecodeError"

    # -------------------------------------------------------------------------
    # auto_inputs_dir precedence tests
    # -------------------------------------------------------------------------

    def test_stdin_beats_auto_detected_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        """When stdin has data and auto_inputs_dir is set, stdin wins."""
        auto_file = tmp_path / "inputs.json"
        auto_file.write_text('{"from_auto": true}')

        stdin_data = json.dumps({"from_stdin": True})
        mock_stdin = io.StringIO(stdin_data)
        mock_stdin.isatty = lambda: False  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        result = parse_cli_inputs(inputs_arg=None, auto_inputs_dir=tmp_path)
        assert result == {"from_stdin": True}

    def test_explicit_inputs_beats_stdin_and_auto(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        """When inputs_arg, stdin, and auto_inputs_dir are all set, inputs_arg wins."""
        auto_file = tmp_path / "inputs.json"
        auto_file.write_text('{"from_auto": true}')

        stdin_data = json.dumps({"from_stdin": True})
        mock_stdin = io.StringIO(stdin_data)
        mock_stdin.isatty = lambda: False  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        result = parse_cli_inputs(
            inputs_arg='{"from_arg": true}',
            auto_inputs_dir=tmp_path,
        )
        assert result == {"from_arg": True}

    def test_empty_stdin_falls_back_to_auto_inputs_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        """When stdin is non-TTY but empty and auto_inputs_dir is set, the auto-detected file is used."""
        auto_file = tmp_path / "inputs.json"
        auto_file.write_text('{"from_auto": true}')

        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: False  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        result = parse_cli_inputs(inputs_arg=None, auto_inputs_dir=tmp_path)
        assert result == {"from_auto": True}

    def test_auto_detected_path_used_when_no_stdin(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        """When stdin is a TTY and auto_inputs_dir is set, the auto-detected file is used."""
        auto_file = tmp_path / "inputs.json"
        auto_file.write_text('{"from_auto": true}')

        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        result = parse_cli_inputs(inputs_arg=None, auto_inputs_dir=tmp_path)
        assert result == {"from_auto": True}

    def test_stdin_beats_ambiguous_auto_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        """Piped stdin outranks auto-detect, so an ambiguous dir (both files) does NOT raise."""
        (tmp_path / "inputs.json").write_text('{"from_auto": true}')
        (tmp_path / "inputs.toml").write_text("from_auto = true\n")

        stdin_data = json.dumps({"from_stdin": True})
        mock_stdin = io.StringIO(stdin_data)
        mock_stdin.isatty = lambda: False  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        result = parse_cli_inputs(inputs_arg=None, auto_inputs_dir=tmp_path)
        assert result == {"from_stdin": True}

    def test_ambiguous_auto_dir_raises_when_no_stdin(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """With no stdin and both default files present, auto-detect is the active source and emits the ambiguity envelope."""
        set_agent_cli_error_format(CliOutputFormat.JSON)
        (tmp_path / "inputs.json").write_text('{"from_auto": true}')
        (tmp_path / "inputs.toml").write_text("from_auto = true\n")

        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

        with pytest.raises(typer.Exit) as exc_info:
            parse_cli_inputs(inputs_arg=None, auto_inputs_dir=tmp_path)

        assert exc_info.value.exit_code == 1
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "AmbiguousInputsFilesError"
        assert envelope["error_domain"] == "input"
        assert "--inputs" in envelope["hint"]
