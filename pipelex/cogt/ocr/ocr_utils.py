from typing import List


def merge_markdown_pages(markdown_pages: List[str], separator: str = "\n") -> str:
    """
    Merge a list of markdown pages into a single markdown string.
    """
    return separator.join(markdown_pages)
