from typing import Any

from pydantic import BaseModel

from pipelex.tools.misc.markdown_utils import convert_to_markdown


class Article(BaseModel):
    title: str
    author: str
    tags: list[str]
    content: str
    metadata: dict[str, Any]


ARTICLE = Article(
    title="My Awesome Article",
    author="John Doe",
    tags=["python", "markdown", "conversion"],
    content="This is the first paragraph of the article.\n\nHere is another paragraph.",
    metadata={
        "published": True,
        "views": 150,
        "related_articles": [{"title": "Another Article", "author": "Jane Doe"}, {"title": "Yet Another Article", "author": "Alice"}],
    },
)

# One heading per key, one level deeper per nesting; a one-line value sits on its heading's line,
# a multi-line value or a list goes below it, and a list item's continuation lines are indented.
EXPECTED_ARTICLE_MARKDOWN = """# title: My Awesome Article

# author: John Doe

# tags

- python
- markdown
- conversion

# content

This is the first paragraph of the article.

Here is another paragraph.

# metadata

## published: True

## views: 150

## related_articles

- ### title: Another Article
  ### author: Jane Doe
- ### title: Yet Another Article
  ### author: Alice"""


class TestConvertToMarkdown:
    def test_a_dict_renders_its_keys_as_headings_and_its_lists_as_bullets(self):
        assert convert_to_markdown(ARTICLE.model_dump()) == EXPECTED_ARTICLE_MARKDOWN

    def test_a_model_renders_like_its_dump(self):
        assert convert_to_markdown(ARTICLE) == EXPECTED_ARTICLE_MARKDOWN
