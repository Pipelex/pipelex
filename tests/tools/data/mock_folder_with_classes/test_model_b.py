# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pipelex.core.stuff_content import StructuredContent, StuffContent


class Class2(StuffContent):
    name: str
    color: str
    speed: int


class Class4(StructuredContent):
    name: str
    color: str
    speed: int
