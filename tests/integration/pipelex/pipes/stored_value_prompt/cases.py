from typing import Any, ClassVar

READ_SCOPE = "org_abc"
STORAGE_SCOPE = "org_abc/mt_1/run_9"

# Long enough that a filter acting on the reference instead of the text could not produce the same prompt, with
# lowercase letters for `upper` to act on.
STORED_TEXT = "the first page of a long document, extracted from a scan.\n" * 30

STORED_TEXT_KEY = f"{STORAGE_SCOPE}/generated/0123abcd/pages.txt"
STORED_TEXT_URL = f"pipelex-storage://{STORED_TEXT_KEY}"


class StoredValuePromptCases:
    """The referenced form of the stored text, as a dict of its fields."""

    TEXT_REFERENCE: ClassVar[dict[str, Any]] = {
        "url": STORED_TEXT_URL,
        "size": len(STORED_TEXT.encode("utf-8")),
        "mime_type": "text/plain",
        "preview": STORED_TEXT[:40],
    }
