# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pydantic import BaseModel

from pipelex.core.stuff_content import StuffContent


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
