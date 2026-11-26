from typing import Any, ClassVar

READ_SCOPE = "org_abc"

STORED_TEXT = "The first page of a long document.\nIt goes on for pages, with accents: é, ü, and 日本語."
STORED_HTML = "<h1>A long page</h1><p>Fetched from the web, with accents: é.</p>"
STORED_JSON_OBJ: dict[str, Any] = {"title": "A large JSON document", "items": [1, 2, 3], "nested": {"accent": "é"}}

TEXT_KEY = "org_abc/mt_1/run_9/generated/0123abcd/text.txt"
MARKDOWN_KEY = "org_abc/mt_1/run_9/generated/4567abcd/text.md"
HTML_KEY = "org_abc/mt_1/run_9/generated/89abcdef/page.html"
JSON_KEY = "org_abc/mt_1/run_9/generated/fedcba98/data.json"
FOREIGN_KEY = "org_other/mt_1/run_9/generated/0123abcd/text.txt"

TEXT_URL = f"pipelex-storage://{TEXT_KEY}"
MARKDOWN_URL = f"pipelex-storage://{MARKDOWN_KEY}"
HTML_URL = f"pipelex-storage://{HTML_KEY}"
JSON_URL = f"pipelex-storage://{JSON_KEY}"
FOREIGN_URL = f"pipelex-storage://{FOREIGN_KEY}"


class StoredValueCases:
    """The referenced form of each class, as a dict of its fields, with the value its storage holds."""

    TEXT_REFERENCE: ClassVar[dict[str, Any]] = {
        "url": TEXT_URL,
        "size": len(STORED_TEXT.encode("utf-8")),
        "mime_type": "text/plain",
        "preview": STORED_TEXT[:20],
    }
    MARKDOWN_REFERENCE: ClassVar[dict[str, Any]] = {
        "url": MARKDOWN_URL,
        "size": len(STORED_TEXT.encode("utf-8")),
        "mime_type": "text/markdown",
        "preview": STORED_TEXT[:20],
    }
    HTML_REFERENCE: ClassVar[dict[str, Any]] = {
        "url": HTML_URL,
        "size": len(STORED_HTML.encode("utf-8")),
        "mime_type": "text/html",
        "preview": STORED_HTML[:20],
    }
    JSON_REFERENCE: ClassVar[dict[str, Any]] = {
        "url": JSON_URL,
        "size": 77,
        "mime_type": "application/json",
        "preview": '{"title": "A large',
    }
