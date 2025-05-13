# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import base64
import json
import zlib


def encode_pako_encore_from_bytes(state_bytes: bytes) -> str:
    compressed = zlib.compress(state_bytes, level=9)
    serialized_string = base64.urlsafe_b64encode(compressed).decode("utf-8")
    return f"pako:{serialized_string}"


def encode_pako_from_string(state: str) -> str:
    state_bytes = state.encode("utf-8")
    return encode_pako_encore_from_bytes(state_bytes)


def make_mermaid_url(mermaid_code: str) -> str:
    as_dict = {
        "code": mermaid_code,
        "mermaid": {
            "theme": "default",
        },
    }
    encoded = encode_pako_from_string(json.dumps(as_dict))
    url = f"https://mermaid.live/edit#{encoded}"
    return url


def clean_str_for_mermaid_node_title(text: str) -> str:
    """
    Cleans a string to be safely used as a Mermaid node title by replacing quotes
    with similar Unicode characters that won't interfere with Mermaid syntax.

    Args:
        text: The string to clean

    Returns:
        The cleaned string with quotes replaced
    """
    # Replace single and double quotes with similar Unicode characters
    text = text.replace('"', "″")  # Replace with prime symbol
    text = text.replace("'", "′")  # Replace with curly quote
    return text
