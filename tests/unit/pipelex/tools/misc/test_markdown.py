from typing import Any

from pydantic import BaseModel

from pipelex.tools.misc.markdown_utils import convert_to_markdown


class Article(BaseModel):
    title: str
    author: str
    tags: list[str]
    content: str
    metadata: dict[str, Any]


def test_convert_md():
    obj = Article(
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

    json_data = obj.model_dump()
    json_data_md = convert_to_markdown(json_data)
    print(json_data_md)

    # Convert that dictionary to Markdown
    obj_md = convert_to_markdown(obj)
    print(obj_md)
