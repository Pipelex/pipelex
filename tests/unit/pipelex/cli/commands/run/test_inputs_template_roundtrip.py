"""Round-trip test: a --format toml generated template loads back through the shared inputs-file loader.

The same template dict is serialized both ways (the JSON path `pipelex build inputs`
writes, and the new TOML path), then both files are loaded through
``load_inputs_dict_from_path`` — the loader the ``run`` surfaces use. The two loads
must resolve to the same dict as the original template, so a generated ``inputs.toml``
is guaranteed to feed ``pipelex run --inputs`` exactly like its ``inputs.json`` twin.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pipelex.cli.commands.run._inputs_file_loader import (
    load_inputs_dict_from_path,  # pyright: ignore[reportPrivateUsage]
)
from pipelex.pipe_machinery.rendering.input_renderer import serialize_inputs_template_to_toml

if TYPE_CHECKING:
    from pathlib import Path


class TestInputsTemplateRoundTrip:
    def test_toml_template_loads_identically_to_json_template(self, tmp_path: Path) -> None:
        """The TOML serialization of a template loads back equal to the template and to its JSON twin."""
        template = {
            "document": {
                "concept": "demo.Document",
                "content": {
                    "url": "https://example.invalid/doc",
                    "summary": "line one\nline two",
                    "page_count": 0,
                    "score": 0.0,
                    "is_signed": False,
                    "tags": ["tags_item"],
                    "metadata": {"metadata_key": "metadata_value"},
                },
            },
            "people": {
                "concept": "demo.Person",
                "content": [{"name": "name_value", "age": 0}],
            },
        }

        toml_file = tmp_path / "inputs.toml"
        toml_file.write_text(serialize_inputs_template_to_toml(template), encoding="utf-8")
        json_file = tmp_path / "inputs.json"
        json_file.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")

        toml_loaded = load_inputs_dict_from_path(toml_file)
        json_loaded = load_inputs_dict_from_path(json_file)

        assert toml_loaded == template
        assert toml_loaded == json_loaded
