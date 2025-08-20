from pydantic import BaseModel

from pipelex.core.stuffs.stuff_content import StuffContent


class ClassA(BaseModel):
    name: str
    color: str
    speed: int
    content: StuffContent


class ClassB:
    name: str
    color: str
    speed: int
    content: StuffContent

    def __init__(self, name: str, color: str, speed: int, content: StuffContent):
        self.name = name
        self.color = color
        self.speed = speed
        self.content = content


class Class1(StuffContent):
    name: str
    color: str
    speed: int
